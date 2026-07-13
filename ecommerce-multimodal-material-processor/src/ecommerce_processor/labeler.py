"""
素材标签打标器 - 视觉AI多Provider打标引擎

支持多种AI Provider，统一OpenAI-compatible接口，
提供断点续传、指数退避重试等企业级特性。
"""
import json
import re
import asyncio
import base64
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from loguru import logger

import httpx
from tqdm import tqdm

from .config import settings, resolve_video_url, build_video_part


class QuotaExhaustedError(Exception):
    """Provider配额耗尽异常"""
    pass


class PayloadTooLargeError(Exception):
    """请求体过大异常（HTTP 413）——不可重试。

    minicpm_base64 会把整段视频 base64 内联，叠加多图后可能超过端点请求体上限。
    这类错误重试同样的请求必然再次失败，因此标记为不可重试，直接失败，
    避免空烧 max_retries 次指数退避（此前实测会白等 10+20+40+80+160s 并浪费额度）。
    正确的解法是启用 settings.auto_compress_oversize 让请求在发出前自动压缩到达标。
    """
    pass


# 8 个标准类目（与打标 prompt 一一对应）
STD_LABELS = [
    "明星穿搭", "穿搭精选(核心)", "穿搭精选(次要)",
    "单品展示(上脚)", "创意静物", "静物展示", "性能测试", "其他",
]


def normalize_label(raw) -> str:
    """把模型返回的自由文本标签归一化到 8 个标准类目。

    模型常返回带序号/描述后缀的文本，如
    "4. 单品展示(剔除出穿搭)-上脚"、"穿搭精选(核心)-穿搭种草 - 全身图"。
    这里剥离噪声并映射到标准类目，保证下游统计/导出可正确聚合。
    """
    if not raw or not isinstance(raw, str):
        return "其他"
    s = raw.strip()
    # 去掉 "4. " / "7、" 这类序号前缀
    s = re.sub(r"^\s*\d+[\.、]\s*", "", s)
    if "明星穿搭" in s:
        return "明星穿搭"
    if "穿搭" in s:
        if "次要" in s or "半身" in s:
            return "穿搭精选(次要)"
        return "穿搭精选(核心)"
    if "单品展示" in s or "上脚" in s:
        return "单品展示(上脚)"
    if "创意静物" in s:
        return "创意静物"
    if "静物展示" in s:
        return "静物展示"
    if "性能测试" in s:
        return "性能测试"
    return "其他"


def _repair_and_parse_json(text: str):
    """尽力从模型输出里解析出 JSON。

    处理常见"带了括号但格式非法"的情况：
    1. 去掉 ```json 代码块围栏
    2. 截取首个 { 到最后一个 }
    3. 修复常见格式问题（中文引号、尾逗号、控制字符、中文冒号）
    4. 仍失败则用正则从散文中抽取 label / confidence
    返回 (parsed_dict, ok:bool)
    """
    if not text or not isinstance(text, str):
        return None, False
    raw = text.strip()
    # 1) 去掉 ```json ... ``` 围栏
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1).strip()
    # 2) 截取首个 { 到最后一个 }
    if "{" in raw and "}" in raw:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        raw = raw[start:end]
    # 3) 修复常见格式问题
    fixed = raw
    fixed = fixed.replace("“", "\"").replace("”", "\"").replace("‘", "'").replace("’", "'")
    fixed = fixed.replace("：", ":")  # 中文冒号
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)  # 尾逗号
    fixed = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", fixed)  # 控制字符
    try:
        return json.loads(fixed), True
    except json.JSONDecodeError:
        pass
    # 4) 正则兜底抽取字段
    try:
        label_m = re.search(r'["\']?label["\']?\s*[:：]\s*["\']([^"\']+)["\']', text)
        conf_m = re.search(r'["\']?confidence["\']?\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)', text)
        reason_m = re.search(r'["\']?reasoning["\']?\s*[:：]\s*["\'](.*?)["\']', text, re.DOTALL)
        label = label_m.group(1).strip() if label_m else None
        conf = float(conf_m.group(1)) if conf_m else None
        reason = reason_m.group(1).strip() if reason_m else ""
        if label:
            return {
                "label": label,
                "confidence": conf if conf is not None else 0.5,
                "reasoning": reason,
            }, True
    except Exception:
        pass
    return None, False


def validate_file_path(file_path: Path) -> Path:
    """
    验证并规范化文件路径（防止路径遍历攻击）

    Args:
        file_path: 用户输入的文件路径

    Returns:
        Path: 规范化后的绝对路径

    Raises:
        FileNotFoundError: 文件不存在时
        ValueError: 路径不合法时
    """
    if not file_path:
        raise ValueError("文件路径不能为空")

    try:
        safe_path = file_path.resolve(strict=True)
    except Exception as e:
        raise FileNotFoundError(f"文件不存在或无法访问: {file_path}") from e

    return safe_path


def validate_media_files(
    files: List[Optional[Path]],
    max_size_mb: float,
    allowed_types_str: str,
    media_type: str,
    settings
) -> List[Path]:
    """
    验证媒体文件列表（类型、大小、存在性）

    Args:
        files: 文件路径列表
        max_size_mb: 最大允许大小(MB)
        allowed_types_str: 允许的扩展名(逗号分隔)
        media_type: 媒体类型名称(用于日志)
        settings: 配置对象

    Returns:
        List[Path]: 通过验证的文件列表
    """
    if not files:
        return []

    allowed_types = set(allowed_types_str.lower().split(","))
    validated = []
    max_size_bytes = max_size_mb * 1024 * 1024

    for file_path in files:
        if not file_path:
            continue

        try:
            safe_path = validate_file_path(Path(file_path))

            ext = safe_path.suffix.lower()
            if ext not in allowed_types:
                logger.warning(
                    f"  不支持的{media_type}格式: {safe_path.name} "
                    f"(允许: {allowed_types_str})"
                )
                continue

            file_size = safe_path.stat().st_size
            if file_size > max_size_bytes:
                logger.warning(
                    f"  {media_type}文件过大: {safe_path.name} "
                    f"({file_size/1024/1024:.1f}MB > {max_size_mb:.0f}MB)"
                )
                continue

            validated.append(safe_path)
            logger.debug(f" {media_type}验证通过: {safe_path.name}")

        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"  {media_type}验证失败: {e}")
        except Exception as e:
            logger.error(f" {media_type}验证异常: {e}")

    return validated


class MaterialLabeler:
    """
    素材标签打标器

    支持多种Provider，统一OpenAI-compatible接口，
    提供断点续传、指数退避重试等企业级特性。
    """

    PROVIDER_CONFIGS = {
        "custom_minmax": {
            "api_key_env": "CUSTOM_MINMAX_API_KEY",
            "base_url": "custom",
            "model": None,
        },
        "minmax": {
            "api_key_env": "MINMAX_API_KEY",
            "base_url": "https://api.minimax.chat/v1",
            "model": "MiniMax-M2.7",
        },
        "minmax_mcp": {
            "api_key_env": "MINMAX_API_KEY",
            "base_url": "mcp",
            "model": "MiniMax-M2.7",
        },
        "kimi": {
            "api_key_env": "KIMI_API_KEY",
            "base_url": "https://api.moonshot.cn/v1",
            "model": "kimi-k2.6",
        },
        "kimi_coding": {
            "api_key_env": "KIMI_API_KEY",
            "base_url": "https://api.moonshot.cn/v1",
            "model": "kimi-k2.6-coding",
        },
        "paddle": {
            "api_key_env": "PADDLE_API_KEY",
            "base_url": "https://aip.baidubce.com/rf/1/creator/paddlepaddle/",
            "model": "qwen2.5-vl-32b-instruct",
        },
        "minicpm": {
            "api_key_env": "MINICPM_API_KEY",
            "base_url": "auto",
            "model": "minicpm-v-4",
        },
        "gemini": {
            "api_key_env": "GEMINI_API_KEY",
            "base_url": "auto",
            "model": "gemini-2.5-flash",
        },
    }

    def __init__(
        self,
        provider: str = "gemini",
        model: str = None,
        materials_dir: Path = Path("downloaded_materials"),
        cache_file: Optional[Path] = None,
        batch_size: int = None,
        batch_delay: float = None,
        force: bool = False,
    ):
        """
        初始化打标器

        Args:
            provider: Provider名称（见PROVIDER_CONFIGS）
            model: 模型名称，默认从settings.vlm_model读取
            materials_dir: 素材目录路径
            cache_file: 缓存文件路径（默认 labeling_cache.json）
            batch_size: 每批处理数量（默认从settings读取）
            batch_delay: 批次间延迟秒数（默认从settings读取）
        """
        self.provider = provider.lower()
        # 视觉打标应使用 VLM 模型（默认 minicpm-v-4.6），
        # 而非 llm_model（可能是纯文本模型，看不见图）
        self.model = model or settings.vlm_model

        if provider not in self.PROVIDER_CONFIGS:
            raise ValueError(
                f"不支持的Provider: {provider}。可用: {list(self.PROVIDER_CONFIGS.keys())}"
            )

        self.materials_dir = Path(materials_dir)
        self.batch_size = batch_size or settings.default_batch_size
        self.batch_delay = batch_delay or settings.default_batch_delay
        self.force = force
        self.cache_file = Path(cache_file) if cache_file else settings.cache_dir / "labeling_cache.json"

        self._load_provider_config()

        self._cache: Dict[str, Any] = {}
        self._load_cache()

    def _load_provider_config(self) -> None:
        """加载当前 Provider 的配置

        视觉打标走 VLM 配置（settings.vlm_*），与文本 LLM 配置（settings.llm_*）完全独立。
        vlm_base_url / vlm_api_key 若设置则优先，否则回退到 provider 表（custom_minmax_url 等）。
        """
        config = self.PROVIDER_CONFIGS[self.provider]

        # 1) API Key：VLM 独立密钥优先，否则取 provider 对应密钥
        api_key_env = config["api_key_env"]
        env_name = api_key_env.replace("_API_KEY", "").lower()
        api_key = getattr(settings, f"{env_name}_api_key", None)
        if settings.vlm_api_key:
            api_key = settings.vlm_api_key
        if not api_key:
            raise ValueError(f"未配置 {api_key_env}！请在 .env 中设置")
        self.api_key = api_key

        # 2) 模型：provider 表优先（如 minicpm 的 minicpm-v-4），否则用 vlm_model
        self.model = config["model"] or settings.vlm_model

        # 3) Base URL：先按 provider 表解析，再用 vlm_base_url 覆盖
        base_url = config["base_url"]
        if base_url == "custom":
            resolved = settings.custom_minmax_url
        elif base_url == "auto":
            if self.provider == "minicpm":
                resolved = settings.minicpm_base_url
            elif self.provider == "gemini":
                resolved = (
                    "https://yescode.ai/v1" if settings.yescode_api_key
                    else "https://generativelanguage.googleapis.com/v1beta/openai"
                )
                self.api_key = settings.yescode_api_key or settings.gemini_api_key
            else:
                raise ValueError(f"Provider {self.provider} 的 base_url 配置错误")
        elif base_url == "mcp":
            from .mcp_client import MiniMaxMCPClient

            self._mcp_client = MiniMaxMCPClient(
                api_key=self.api_key,
                model=self.model,
                use_mcp=True,
                max_retries=settings.max_retries,
                retry_delay=settings.retry_base_delay,
                timeout=120,
            )

            logger.info(
                f" Provider配置: {self.provider} | "
                f"模型: {self.model} | "
                f"Base URL: MCP协议 (MiniMax understand_image tool)"
            )
            return
        else:
            resolved = base_url

        # VLM 独立地址优先（实现 VLM/LLM 分离配置）
        self.base_url = settings.vlm_base_url or resolved

        logger.info(
            f" Provider配置: {self.provider} | "
            f"模型: {self.model} | "
            f"Base URL: {self.base_url}"
        )

    def _load_cache(self) -> None:
        """加载已有缓存"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                logger.info(f" 加载缓存: {len(self._cache)} 条记录")
            except Exception as e:
                logger.warning(f"  缓存文件损坏，将重新创建: {e}")
                self._cache = {}
        else:
            self._cache = {}

    def _save_cache(self) -> None:
        """保存缓存到文件（原子写入）"""
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=self.cache_file.parent,
                suffix=".tmp"
            )
            try:
                with open(fd, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f, ensure_ascii=False, indent=2)
                os.replace(str(tmp_path), str(self.cache_file))
            except Exception:
                try:
                    Path(tmp_path).unlink()
                except Exception:
                    pass
                raise

            logger.debug(f" 缓存已保存: {self.cache_file} ({len(self._cache)} 条)")
        except Exception as e:
            logger.error(f" 缓存保存失败: {e}")

    async def _call_api_with_retry(
        self,
        messages: List[Dict],
        images: Optional[List[Path]] = None,
        videos: Optional[List[Path]] = None,
    ) -> str:
        """
        调用视觉API（带指数退避重试）

        Args:
            messages: 对话消息列表
            images: 图片路径列表（可选）
            videos: 视频路径列表（可选）

        Returns:
            str: API响应内容

        Raises:
            QuotaExhaustedError: 配额耗尽
            Exception: 其他API错误
        """
        if hasattr(self, '_mcp_client') and self._mcp_client is not None:
            return await self._call_api_via_mcp(messages, images)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        content_parts = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                content_parts.extend(msg["content"])
            else:
                content_parts.append({"type": "text", "text": msg["content"]})

        if images:
            # 是否在 base64 前对图片降分辨率重压（缓解请求体过大 / 413）
            auto_compress = getattr(settings, "auto_compress_oversize", True)
            for img_path in images[:getattr(settings, 'max_images', 10)]:
                try:
                    if auto_compress:
                        from .video_utils import compress_image_to_bytes
                        img_bytes = compress_image_to_bytes(
                            img_path,
                            max_side=getattr(settings, "image_max_size", 1024) or 1024,
                            quality=getattr(settings, "image_quality", 80) or 80,
                        )
                    else:
                        img_bytes = img_path.read_bytes()
                    image_data = base64.standard_b64encode(img_bytes).decode("utf-8")
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                    })
                except Exception as e:
                    logger.warning(f"  图片读取失败 {img_path}: {e}")

        if videos and getattr(settings, 'video_direct_mode', True):
            material_id = videos[0].parent.name
            for video_path in videos[:getattr(settings, 'max_videos', 3)]:
                try:
                    # 视频直接传输（不抽帧）：具体字段形态由 config.build_video_part
                    # 按 video_payload_format 决定——openai_compatible / gemma_hf / gemini
                    # 为远程 URL 引用（端点自行 fetch）；minicpm_base64 为整段视频
                    # base64 内联（面壁/MiniCPM-vLLM 约定，仍是整段而非抽帧）。
                    # 若开启 auto_compress_oversize，base64 前会对超预算视频整段重编码
                    # 压到 max_request_mb 内（仍不抽帧），以规避端点请求体上限(413)。
                    video_url = resolve_video_url(video_path, material_id)
                    content_parts.append(build_video_part(video_url))
                    logger.info(f"已添加视频（{settings.video_payload_format} 形态，不抽帧）: {video_url}")
                except Exception as e:
                    logger.warning(f"视频URL解析失败 {video_path}: {e}")

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content_parts}],
            "max_tokens": settings.vlm_max_tokens,
            "temperature": settings.vlm_temperature,
        }

        last_error = None
        for attempt in range(1, settings.max_retries + 1):
            try:
                delay = settings.retry_base_delay * (2 ** (attempt - 1))
                if attempt > 1:
                    logger.info(f"⏳ 第{attempt}次重试，等待 {delay}s...")
                    await asyncio.sleep(delay)

                async with httpx.AsyncClient(timeout=settings.vlm_timeout_ms/1000.0) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )

                    if response.status_code == 200:
                        result = response.json()
                        return result["choices"][0]["message"]["content"]

                    elif response.status_code == 429:
                        error_detail = response.json().get("error", {})
                        error_msg = error_detail.get("message", "Rate limit exceeded")

                        if "quota" in error_msg.lower() or "exhausted" in error_msg.lower():
                            raise QuotaExhaustedError(error_msg)

                        logger.warning(f"  API限流 (HTTP 429): {error_msg}")
                        continue

                    elif response.status_code == 413:
                        # 请求体过大：重试同样的 payload 必然再次 413，标记为不可重试直接失败，
                        # 避免空烧 max_retries 次指数退避。请开启 auto_compress_oversize 让请求前自动瘦身。
                        error_msg = (
                            f"请求体过大 (HTTP 413): {response.text[:200]}。"
                            f"已放弃重试；建议开启 AUTO_COMPRESS_OVERSIZE 或调低 MAX_REQUEST_MB。"
                        )
                        logger.error(f" {error_msg}")
                        raise PayloadTooLargeError(error_msg)

                    else:
                        error_msg = f"API错误 HTTP {response.status_code}: {response.text}"
                        logger.error(f" {error_msg}")
                        last_error = Exception(error_msg)

            except QuotaExhaustedError:
                raise
            except PayloadTooLargeError:
                raise
            except httpx.TimeoutException:
                last_error = Exception("API请求超时")
                logger.warning(f"  第{attempt}次超时")
            except Exception as e:
                last_error = e
                logger.warning(f"  第{attempt}次失败: {e}")

        raise last_error or Exception("未知API错误")

    async def _call_api_via_mcp(
        self,
        messages: List[Dict],
        images: Optional[List[Path]] = None,
    ) -> str:
        """
        通过MCP协议调用视觉API

        Args:
            messages: 对话消息列表
            images: 图片路径列表

        Returns:
            str: API响应内容
        """
        if not self._mcp_client:
            raise RuntimeError("MCP客户端未初始化")

        prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                    prompt = " ".join(text_parts)
                elif isinstance(content, str):
                    prompt = content
                break

        if not prompt:
            prompt = "请分析这张图片的内容"

        if images and len(images) > 0:
            logger.info(f" 使用MCP模式分析图片: {images[0].name}")

            result, mode = await self._mcp_client.analyze_image(
                image_path=images[0],
                prompt=prompt,
                prefer_mcp=True,
            )

            if result:
                logger.success(f" MCP分析完成 (模式: {mode})")
                return result
            else:
                raise Exception(f"MCP分析失败 (模式: {mode})")
        else:
            logger.warning("  MCP模式未收到图片，将使用标准文本模式")

            payload = {
                "model": settings.llm_model,
                "messages": messages,
                "max_tokens": settings.llm_max_tokens,
                "temperature": settings.llm_temperature,
            }

            async with httpx.AsyncClient(timeout=settings.llm_timeout_ms/1000.0) as client:
                response = await client.post(
                    f"{settings.llm_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.llm_api_key or self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    raise Exception(f"MCP文本模式错误 HTTP {response.status_code}: {response.text}")

    async def label_single_folder(self, folder_path: Path) -> Dict:
        """
        打标单个素材文件夹

        Args:
            folder_path: 素材文件夹路径

        Returns:
            Dict: 打标结果
        """
        material_id = folder_path.name

        if not self.force and material_id in self._cache:
            cached = self._cache[material_id]
            # 瞬态失败缓存项视为无效，重新处理（避免修复前残留的
            # "处理失败"/"JSON解析失败"被永久固化）
            if cached.get("label") == "处理失败" or cached.get("error") == "JSON解析失败":
                logger.debug(f" 缓存为瞬态失败，重新处理: {material_id}")
            else:
                logger.debug(f"⏭  已缓存，跳过: {material_id}")
                return cached

        images = []
        videos = []
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
            images.extend(folder_path.glob(ext))
        for ext in ["*.mp4", "*.mov", "*.avi"]:
            videos.extend(folder_path.glob(ext))

        if not images and not videos:
            logger.warning(f"  空文件夹: {material_id}")
            result = {
                "material_id": material_id,
                "label": "其他",
                "confidence": 0.0,
                "error": "空文件夹",
                "timestamp": datetime.now().isoformat(),
            }
            self._cache[material_id] = result
            self._save_cache()
            return result

        logger.debug(" 开始输入验证...")

        validated_images = validate_media_files(
            images or [],
            getattr(settings, 'max_image_size_mb', 50.0),
            getattr(settings, 'allowed_image_types', '.jpg,.jpeg,.png,.webp,.gif'),
            "图片",
            settings
        )
        if images:
            logger.info(f"    图片验证通过: {len(validated_images)}/{len(images)} 张")
        images = validated_images

        validated_videos = validate_media_files(
            videos or [],
            getattr(settings, 'max_video_size_mb', 500.0),
            getattr(settings, 'allowed_video_types', '.mp4,.mov,.avi,.mkv'),
            "视频",
            settings
        )
        if videos:
            logger.info(f"    视频验证通过: {len(validated_videos)}/{len(videos)} 个")
        videos = validated_videos

        video_files_for_api = []
        if videos and getattr(settings, 'video_direct_mode', True):
            logger.info(f"视频直接模式: 将{len(videos)}个视频文件直接传给AI模型")
            video_files_for_api = videos[:getattr(settings, 'max_videos', 3)]

        all_images = list(images) if images else []

        if not all_images and not video_files_for_api:
            logger.warning(f"  {material_id}: 无可用图像,跳过API调用")
            result = {
                "material_id": material_id,
                "label": "其他",
                "confidence": 0.0,
                "error": "无可用图像（图片读取失败）且视频直接传输不可用",
                "reasoning": "素材文件夹中无有效图片，且视频未提供或直接传输失败",
                "provider": None,
                "model": None,
                "timestamp": datetime.now().isoformat(),
            }
            self._cache[material_id] = result
            self._save_cache()
            return result

        try:
            prompt = """你是一个电商素材分类专家。请根据以下素材内容，判断其属于哪一类标签。

可选标签：
1. 明星穿搭 - 包含知名明星/公众人物
2. 穿搭精选(核心)-穿搭种草 - 全身图，头部+躯干+脚部均可见
3. 穿搭精选(次要)-穿搭种草 - 半身图，头部+躯干可见，脚部不可见
4. 单品展示(剔除出穿搭)-上脚 - 仅膝盖以下及脚部
5. 创意静物 - 无人物，艺术置景/AI渲染/风格化
6. 静物展示 - 无人物，纯底/平铺/无艺术处理
7. 性能测试 - 视频：连续运动帧+科技点讲解
8. 其他 - 不属于以上任何分类

请以JSON格式返回结果：
{
  "label": "标签名称",
  "confidence": 0.95,
  "reasoning": "判定理由"
}
"""

            response_text = await self._call_api_with_retry(
                messages=[{"role": "user", "content": prompt}],
                images=all_images[:5],
                videos=video_files_for_api,
            )

            parsed, ok = _repair_and_parse_json(response_text)
            if not ok:
                # 首次解析失败：用更严格的纯 JSON 指令重试一次
                strict_prompt = (
                    prompt
                    + "\n\n【重要】仅输出一行纯JSON，不要任何解释文字、"
                      "不要Markdown代码块、不要中文引号，直接使用英文双引号。"
                )
                try:
                    response_text2 = await self._call_api_with_retry(
                        messages=[{"role": "user", "content": strict_prompt}],
                        images=all_images[:5],
                        videos=video_files_for_api,
                    )
                    parsed, ok = _repair_and_parse_json(response_text2)
                except QuotaExhaustedError:
                    raise
                except Exception as retry_err:
                    logger.warning(f"  重试调用失败 {material_id}: {retry_err}")
                    ok = False

            if ok:
                result = {
                    "material_id": material_id,
                    "label": normalize_label(parsed.get("label", "其他")),
                    "confidence": float(parsed.get("confidence") or 0.0),
                    "reasoning": parsed.get("reasoning", ""),
                    "provider": self.provider,
                    "model": self.model,
                    "timestamp": datetime.now().isoformat(),
                }
                # 成功结果才写入缓存（便于断点续传）
                self._cache[material_id] = result
                self._save_cache()
                return result
            else:
                # 解析彻底失败：明确记 error，便于下游重试/统计，
                # 不再静默记为"其他"导致数据失真。
                # 不写入缓存，下次运行可重试。
                return {
                    "material_id": material_id,
                    "label": "其他",
                    "confidence": 0.0,
                    "error": "JSON解析失败",
                    "raw_response": (response_text or "")[:500],
                    "timestamp": datetime.now().isoformat(),
                }

        except PayloadTooLargeError as e:
            # 请求体过大：不可重试。不写入缓存，便于下次调低 MAX_REQUEST_MB / 开启压缩后重跑。
            logger.error(f" 请求体过大，跳过（不重试）{material_id}: {e}")
            return {
                "material_id": material_id,
                "label": "处理失败",
                "confidence": 0.0,
                "error": f"请求体过大(413): {str(e)[:200]}",
                "timestamp": datetime.now().isoformat(),
            }

        except QuotaExhaustedError as e:
            logger.error(f" Provider配额耗尽: {e}")
            logger.info(f"⏳ 将在 {settings.quota_wait_hours} 小时后自动恢复...")

            result = {
                "material_id": material_id,
                "label": "待处理",
                "error": f"配额耗尽: {str(e)}",
                "retry_after_hours": settings.quota_wait_hours,
                "timestamp": datetime.now().isoformat(),
            }
            self._cache[material_id] = result
            self._save_cache()
            raise

        except Exception as e:
            logger.error(f" 处理失败 {material_id}: {e}")
            # 瞬时失败（网络/超时/端点错误）不写入缓存，
            # 下次运行可重试，避免被永久固化为"处理失败"导致静默丢数据。
            return {
                "material_id": material_id,
                "label": "处理失败",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def process_all(
        self,
        sample: int = None,
        progress_callback=None,
        concurrency: int = None,
    ) -> Dict:
        """
        处理所有素材文件夹

        Args:
            sample: 采样数量（None=全量）
            progress_callback: 进度回调函数 callback(current, total, result)

        Returns:
            Dict: 统计信息
        """
        folders = [
            f for f in self.materials_dir.iterdir() 
            if f.is_dir() and not f.name.startswith(".")
        ]

        if sample:
            folders = folders[:sample]

        total = len(folders)
        # 运行开始前已在缓存中的 id（用于区分"缓存命中"与"本次新处理"）
        cached_ids = set(self._cache.keys())
        logger.info(f"\n{'='*60}")
        logger.info(f" 开始打标处理")
        logger.info(f"   Provider: {self.provider}")
        logger.info(f"   素材总数: {total}")
        logger.info(f"   已缓存: {sum(1 for f in folders if f.name in self._cache)}")
        logger.info(f"   待处理: {total - sum(1 for f in folders if f.name in self._cache)}")
        logger.info(f"{'='*60}\n")

        stats = {
            "total": total,
            "success": 0,
            "failed": 0,
            "cached": 0,
            "other": 0,
            "empty": 0,
            "labels": {},
            "errors": [],
        }

        pbar = tqdm(total=total, desc="Processing", unit="folder")
        quota_exhausted = asyncio.Event()

        async def _process_one(idx: int, folder: Path) -> None:
            """单个文件夹的并发处理单元（带配额中断信号）。"""
            if quota_exhausted.is_set():
                return
            async with sem:
                if quota_exhausted.is_set():
                    return
                try:
                    result = await self.label_single_folder(folder)
                except QuotaExhaustedError:
                    logger.error("\n\n 配额耗尽，中断处理！")
                    quota_exhausted.set()
                    pbar.update(1)
                    return
                except Exception as e:
                    logger.error(f" 未捕获异常 {folder.name}: {e}")
                    stats["failed"] += 1
                    pbar.update(1)
                    return

                # 统计更新（asyncio 单线程，同步块内更新互斥安全）
                if result is None:
                    stats["failed"] += 1
                    pbar.update(1)
                    return

                label = result.get("label", "未知")
                from_cache = folder.name in cached_ids

                if label == "待处理":
                    # 配额耗尽待处理：缓存命中，不计入成功/失败
                    if from_cache:
                        stats["cached"] += 1
                    stats["labels"][label] = stats["labels"].get(label, 0) + 1
                    pbar.update(1)
                    return

                if "error" in result:
                    if result.get("error") == "空文件夹":
                        stats["empty"] += 1
                    else:
                        stats["failed"] += 1
                        stats["errors"].append(result)
                elif label == "其他":
                    # "其他"是合法标签类目，单独计数，不与"缓存跳过"混淆
                    stats["other"] += 1
                else:
                    stats["success"] += 1

                if from_cache:
                    stats["cached"] += 1

                stats["labels"][label] = stats["labels"].get(label, 0) + 1

                if progress_callback:
                    progress_callback(idx + 1, total, result)

                pbar.update(1)

        # 有界并发：并发上限由 concurrency 参数或 settings.default_workers 决定
        sem = asyncio.Semaphore(concurrency or getattr(settings, "default_workers", 3))
        tasks = [asyncio.create_task(_process_one(i, f)) for i, f in enumerate(folders)]
        await asyncio.gather(*tasks)

        self._print_stats(stats)

        return stats

    def _print_stats(self, stats: Dict) -> None:
        """打印统计摘要"""
        logger.info(f"\n{'='*60}")
        logger.info(f" 打标完成统计")
        logger.info(f"{'='*60}")
        logger.info(f"总素材数: {stats['total']}")
        logger.info(f"成功: {stats['success']} ({stats['success']/max(stats['total'],1)*100:.1f}%)")
        logger.info(f"失败: {stats['failed']}")
        logger.info(f"其他标签: {stats['other']}")
        logger.info(f"空文件夹: {stats['empty']}")
        logger.info(f"缓存命中(未重新处理): {stats['cached']}")

        logger.info(f"\n标签分布:")
        for label, count in sorted(stats["labels"].items(), key=lambda x: x[1], reverse=True):
            pct = count / max(stats['total'] - stats['failed'], 1) * 100
            bar = "█" * int(pct / 5)
            logger.info(f"  {label:<30} {count:>5} ({pct:>5.1f}%) {bar}")

        other_ratio = stats["labels"].get("其他", 0) / max(stats['total'] - stats['failed'], 1)
        if other_ratio > settings.quality_other_label_threshold:
            logger.warning(f"\n  质量告警: '其他'标签占比 {other_ratio*100:.1f}% > 阈值 {settings.quality_other_label_threshold*100}%")
            logger.warning("建议检查标签判定基准或切换Provider重新打标")

        if stats["errors"]:
            logger.error(f"\n 错误详情:")
            for err in stats["errors"][:10]:
                logger.error(f"  - {err.get('material_id')}: {err.get('error', 'Unknown')}")

        logger.info(f"{'='*60}")

    @staticmethod
    async def run_cli(args):
        """CLI入口点"""
        from .config import settings

        labeler = MaterialLabeler(
            provider=args.provider,
            materials_dir=args.materials_dir,
            batch_size=args.batch_size,
            batch_delay=args.batch_delay,
            force=getattr(args, "force", False),
        )

        await labeler.process_all(sample=args.sample)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="素材标签打标")
    parser.add_argument("--materials-dir", default="downloaded_materials", help="素材目录")
    parser.add_argument("--batch-size", type=int, default=None, help="每批数量")
    parser.add_argument("--batch-delay", type=float, default=None, help="批次延迟(秒)")
    parser.add_argument("--provider", default="custom_minmax", choices=list(MaterialLabeler.PROVIDER_CONFIGS.keys()))
    parser.add_argument("--sample", type=int, default=None, help="采样数量")

    args = parser.parse_args()

    asyncio.run(MaterialLabeler.run_cli(args))