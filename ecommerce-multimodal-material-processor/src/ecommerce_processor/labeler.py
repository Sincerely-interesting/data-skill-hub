"""
素材标签打标器 - 视觉AI多Provider打标引擎
"""
import json
import asyncio
import base64
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from loguru import logger

import httpx
from tqdm import tqdm

from .config import settings


class QuotaExhaustedError(Exception):
    """Provider配额耗尽异常"""
    pass


class MaterialLabeler:
    """
    素材标签打标器
    
    支持多种Provider，统一OpenAI-compatible接口，
    提供断点续传、指数退避重试等企业级特性。
    """

    # Provider配置映射
    PROVIDER_CONFIGS = {
        "custom_minmax": {
            "api_key_env": "CUSTOM_MINMAX_API_KEY",
            "base_url": "custom",  # 使用自定义URL
            "model": "auto"  # 从settings.llm_model读取,
        },
        "minmax": {
            "api_key_env": "MINMAX_API_KEY",
            "base_url": "https://api.minimax.chat/v1",
            "model": "MiniMax-M2.7",
        },
        "minmax_mcp": {
            "api_key_env": "MINMAX_API_KEY",
            "base_url": "mcp",  # MCP协议特殊处理
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
            "base_url": "auto",  # 使用配置中的URL
            "model": "minicpm-v-4",
        },
        "gemini": {
            "api_key_env": "GEMINI_API_KEY",
            "base_url": "auto",  # 通过YesCode代理或直连
            "model": "gemini-2.5-flash",
        },
    }

    def __init__(
        self,
        provider: str = "gemini",
        materials_dir: Path = Path("downloaded_materials"),
        cache_file: Optional[Path] = None,
        batch_size: int = None,
        batch_delay: float = None,
    ):
        """
        初始化打标器
        
        Args:
            provider: Provider名称（见PROVIDER_CONFIGS）
            materials_dir: 素材目录路径
            cache_file: 缓存文件路径（默认 labeling_cache.json）
            batch_size: 每批处理数量（默认从settings读取）
            batch_delay: 批次间延迟秒数（默认从settings读取）
        """
        self.provider = provider.lower()
        if provider not in self.PROVIDER_CONFIGS:
            raise ValueError(
                f"不支持的Provider: {provider}。可用: {list(self.PROVIDER_CONFIGS.keys())}"
            )

        self.materials_dir = Path(materials_dir)
        self.batch_size = batch_size or settings.default_batch_size
        self.batch_delay = batch_delay or settings.default_batch_delay
        
        # 缓存文件
        self.cache_file = Path(cache_file) if cache_file else settings.cache_dir / "labeling_cache.json"
        
        # 加载Provider配置
        self._load_provider_config()
        
        # 加载已有缓存
        self._cache: Dict[str, Any] = {}
        self._load_cache()

    def _load_provider_config(self) -> None:
        """加载当前Provider的配置"""
        config = self.PROVIDER_CONFIGS[self.provider]
        
        # 获取API Key
        api_key_env = config["api_key_env"]
        env_name = api_key_env.replace("_API_KEY", "")
        api_key = getattr(settings, f"{env_name}_api_key".lower(), None)
        
        if not api_key:
            raise ValueError(f"未配置 {api_key_env}！请在 .env 中设置")
        
        self.api_key = api_key
        self.model = config["model"]
        
        # 获取Base URL
        base_url = config["base_url"]
        if base_url == "custom":
            self.base_url = settings.custom_minmax_url
        elif base_url == "auto":
            if self.provider == "minicpm":
                self.base_url = settings.minicpm_base_url
            elif self.provider == "gemini":
                # 优先使用YesCode代理，否则使用Gemini直连
                self.base_url = (
                    f"https://yescode.ai/v1" if settings.yescode_api_key 
                    else "https://generativelanguage.googleapis.com/v1beta/openai"
                )
                self.api_key = settings.yescode_api_key or settings.gemini_api_key
            else:
                raise ValueError(f"Provider {self.provider} 的 base_url 配置错误")
        elif base_url == "mcp":
            self.base_url = None  # MCP协议特殊处理
            
            # 初始化MCP客户端（独立实现）
            from .mcp_client import MiniMaxMCPClient
            
            self._mcp_client = MiniMaxMCPClient(
                api_key=self.api_key,
                model=self.model,
                use_mcp=True,
                max_retries=settings.max_retries,
                retry_delay=settings.retry_base_delay,
                timeout=120,  # MCP可能需要更长时间
            )
            
            logger.info(
                f"📡 Provider配置: {self.provider} | "
                f"模型: {self.model} | "
                f"Base URL: MCP协议 (MiniMax understand_image tool)"
            )
        else:
            self.base_url = base_url

            logger.info(
                f"📡 Provider配置: {self.provider} | "
                f"模型: {self.model} | "
                f"Base URL: {self.base_url}"
            )

    def _load_cache(self) -> None:
        """加载已有缓存"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                logger.info(f"📦 加载缓存: {len(self._cache)} 条记录")
            except Exception as e:
                logger.warning(f"⚠️  缓存文件损坏，将重新创建: {e}")
                self._cache = {}
        else:
            self._cache = {}

    def _save_cache(self) -> None:
        """保存缓存到文件（原子写入）"""
        try:
            import tempfile
            
            # 写入临时文件
            fd, tmp_path = tempfile.mkstemp(
                dir=self.cache_file.parent,
                suffix=".tmp"
            )
            try:
                with open(fd, "w", encoding="utf-8") as f:
                    json.dump(self._cache, f, ensure_ascii=False, indent=2)
                
                # 原子重命名
                Path(tmp_path).rename(self.cache_file)
            except Exception:
                # 清理临时文件
                try:
                    Path(tmp_path).unlink()
                except:
                    pass
                raise
                
            logger.debug(f"💾 缓存已保存: {self.cache_file} ({len(self._cache)} 条)")
        except Exception as e:
            logger.error(f"❌ 缓存保存失败: {e}")

    async def _call_api_with_retry(
        self,
        messages: List[Dict],
        images: Optional[List[Path]] = None,
    ) -> str:
        """
        调用视觉API（带指数退避重试）
        
        支持两种模式：
        1. 标准模式：直接调用OpenAI兼容的视觉API
        2. MCP模式：通过MiniMax MCP协议调用understand_image工具
        
        Args:
            messages: 对话消息列表
            images: 图片路径列表（可选）
            
        Returns:
            str: API响应内容
            
        Raises:
            QuotaExhaustedError: 配额耗尽
            Exception: 其他API错误
        """
        # MCP模式特殊处理
        if hasattr(self, '_mcp_client') and self._mcp_client is not None:
            return await self._call_api_via_mcp(messages, images)
        
        # 标准API调用模式
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # 构建消息（包含图片）
        content_parts = []
        for msg in messages:
            if isinstance(msg.get("content"), list):
                content_parts.extend(msg["content"])
            else:
                content_parts.append({"type": "text", "text": msg["content"]})
        
        # 添加图片（base64编码）
        if images:
            for img_path in images[:10]:  # 限制最多10张图
                try:
                    image_data = base64.standard_b64encode(img_path.read_bytes()).decode("utf-8")
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                    })
                except Exception as e:
                    logger.warning(f"⚠️  图片读取失败 {img_path}: {e}")
        
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content_parts}],
            "max_tokens": settings.llm_max_tokens,
            "temperature": settings.llm_temperature,  # 从配置读取
        }

        last_error = None
        for attempt in range(1, settings.max_retries + 1):
            try:
                delay = settings.retry_base_delay * (2 ** (attempt - 1))
                if attempt > 1:
                    logger.info(f"⏳ 第{attempt}次重试，等待 {delay}s...")
                    await asyncio.sleep(delay)

                async with httpx.AsyncClient(timeout=settings.llm_timeout_ms/1000.0) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        return result["choices"][0]["message"]["content"]
                    
                    elif response.status_code == 429:
                        # Rate limit or quota exhausted
                        error_detail = response.json().get("error", {})
                        error_msg = error_detail.get("message", "Rate limit exceeded")
                        
                        if "quota" in error_msg.lower() or "exhausted" in error_msg.lower():
                            raise QuotaExhaustedError(error_msg)
                        
                        logger.warning(f"⚠️  API限流 (HTTP 429): {error_msg}")
                        continue
                    
                    else:
                        error_msg = f"API错误 HTTP {response.status_code}: {response.text}"
                        logger.error(f"❌ {error_msg}")
                        last_error = Exception(error_msg)
                        
            except QuotaExhaustedError:
                raise
            except httpx.TimeoutException:
                last_error = Exception("API请求超时")
                logger.warning(f"⚠️  第{attempt}次超时")
            except Exception as e:
                last_error = e
                logger.warning(f"⚠️  第{attempt}次失败: {e}")

        # 所有重试失败
        raise last_error or Exception("未知API错误")
    
    async def _call_api_via_mcp(
        self,
        messages: List[Dict],
        images: Optional[List[Path]] = None,
    ) -> str:
        """
        通过MCP协议调用视觉API
        
        使用MiniMaxMCPClient进行图片分析，
        支持自动降级为直连模式。
        
        Args:
            messages: 对话消息列表（提取最后一条作为prompt）
            images: 图片路径列表
            
        Returns:
            str: API响应内容
            
        Raises:
            Exception: MCP调用失败
        """
        if not self._mcp_client:
            raise RuntimeError("MCP客户端未初始化")
        
        # 提取prompt（使用messages的最后一条用户消息）
        prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    # 提取文本部分
                    text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                    prompt = " ".join(text_parts)
                elif isinstance(content, str):
                    prompt = content
                break
        
        if not prompt:
            prompt = "请分析这张图片的内容"
        
        # 如果没有提供图片，尝试从messages中提取
        if not images:
            for msg in messages:
                content = msg.get("content", [])
                if isinstance(content, list):
                    for part in content:
                        if part.get("type") == "image_url":
                            # 从data URL中无法直接获取文件路径，跳过
                            pass
        
        # 如果有图片，使用MCP客户端分析第一张图片
        if images and len(images) > 0:
            logger.info(f"🔌 使用MCP模式分析图片: {images[0].name}")
            
            result, mode = await self._mcp_client.analyze_image(
                image_path=images[0],
                prompt=prompt,
                prefer_mcp=True,
            )
            
            if result:
                logger.success(f"✅ MCP分析完成 (模式: {mode})")
                return result
            else:
                raise Exception(f"MCP分析失败 (模式: {mode})")
        
        else:
            # 没有图片，使用纯文本模式（MCP主要用于多模态）
            logger.warning("⚠️  MCP模式未收到图片，将使用标准文本模式")
            
            # 降级为简单的文本请求
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": settings.llm_max_tokens,
                "temperature": 0.3,
            }
            
            async with httpx.AsyncClient(timeout=settings.llm_timeout_ms/1000.0) as client:
                response = await client.post(
                    "https://api.minimaxi.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
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
        
        # 检查是否已缓存
        if material_id in self._cache:
            logger.debug(f"⏭️  已缓存，跳过: {material_id}")
            return self._cache[material_id]

        # 收集图片和视频
        images = []
        videos = []
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
            images.extend(folder_path.glob(ext))
        for ext in ["*.mp4", "*.mov", ".avi"]:
            videos.extend(folder_path.glob(ext))

        if not images and not videos:
            logger.warning(f"⚠️  空文件夹: {material_id}")
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

        # 处理视频素材：抽帧转换为图片序列
        frame_images = []
        if videos:
            try:
                from .video_utils import VideoProcessor
                
                with VideoProcessor(
                    default_fps=1.0,
                    default_max_frames=45,
                    default_target_count=10,
                    keep_frames=False,  # 处理后自动清理临时文件
                ) as processor:
                    
                    # 限制处理视频数量（避免过多视频导致API调用成本过高）
                    for video in videos[:3]:
                        sampled_frames, video_info = processor.process_video(video)
                        frame_images.extend(sampled_frames)
                        
                        logger.debug(
                            f"🎬 视频抽帧: {video.name} → "
                            f"{len(sampled_frames)}帧 ({video_info['duration']}s)"
                        )
                
                if frame_images:
                    logger.info(f"   📹 视频抽帧完成: {len(videos)}个视频 → {len(frame_images)}帧")
                
            except Exception as e:
                logger.warning(f"⚠️  视频抽帧失败，将跳过视频素材: {e}")

        # 合并所有可用的图片（原始图片 + 抽帧图片）
        all_images = list(images) + frame_images

        try:
            # 构建打标prompt
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

            # 调用API
            response_text = await self._call_api_with_retry(
                messages=[{"role": "user", "content": prompt}],
                images=all_images[:5],  # 最多发送5张图片（包含视频抽帧）
            )

            # 解析响应
            try:
                # 尝试提取JSON
                if "{" in response_text and "}" in response_text:
                    start = response_text.index("{")
                    end = response_text.rindex("}") + 1
                    parsed = json.loads(response_text[start:end])
                else:
                    parsed = {"label": "其他", "confidence": 0.0, "reasoning": response_text}

                result = {
                    "material_id": material_id,
                    "label": parsed.get("label", "其他"),
                    "confidence": float(parsed.get("confidence", 0.0)),
                    "reasoning": parsed.get("reasoning", ""),
                    "provider": self.provider,
                    "model": self.model,
                    "timestamp": datetime.now().isoformat(),
                }

            except json.JSONDecodeError:
                result = {
                    "material_id": material_id,
                    "label": "其他",
                    "confidence": 0.0,
                    "error": "JSON解析失败",
                    "raw_response": response_text[:500],
                    "timestamp": datetime.now().isoformat(),
                }

            # 保存到缓存
            self._cache[material_id] = result
            self._save_cache()

            return result

        except QuotaExhaustedError as e:
            logger.error(f"💥 Provider配额耗尽: {e}")
            logger.info(f"⏳ 将在 {settings.quota_wait_hours} 小时后自动恢复...")
            
            # 记录配额耗尽状态
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
            logger.error(f"❌ 处理失败 {material_id}: {e}")
            result = {
                "material_id": material_id,
                "label": "处理失败",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
            self._cache[material_id] = result
            self._save_cache()
            return result

    async def process_all(
        self,
        sample: int = None,
        progress_callback=None,
    ) -> Dict:
        """
        处理所有素材文件夹
        
        Args:
            sample: 采样数量（None=全量）
            progress_callback: 进度回调函数 callback(current, total, result)
            
        Returns:
            Dict: 统计信息
        """
        # 发现所有素材文件夹
        folders = [
            f for f in self.materials_dir.iterdir() 
            if f.is_dir() and not f.name.startswith(".")
        ]
        
        if sample:
            folders = folders[:sample]
        
        total = len(folders)
        logger.info(f"\n{'='*60}")
        logger.info(f"🏷️ 开始打标处理")
        logger.info(f"   Provider: {self.provider}")
        logger.info(f"   素材总数: {total}")
        logger.info(f"   已缓存: {sum(1 for f in folders if f.name in self._cache)}")
        logger.info(f"   待处理: {total - sum(1 for f in folders if f.name in self._cache)}")
        logger.info(f"{'='*60}\n")

        # 统计
        stats = {
            "total": total,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "labels": {},
            "errors": [],
        }

        # 创建进度条
        pbar = tqdm(folders, desc="Processing", unit="folder")

        for i, folder in enumerate(pbar):
            try:
                result = await self.label_single_folder(folder)
                
                if folder.name in self._cache and "error" not in result:
                    if result.get("label") == "待处理":
                        continue
                    
                if "error" in result and result["error"] not in ["空文件夹", "已缓存"]:
                    stats["failed"] += 1
                    stats["errors"].append(result)
                elif result.get("label") == "其他":
                    stats["skipped"] += 1
                else:
                    stats["success"] += 1

                # 标签统计
                label = result.get("label", "未知")
                stats["labels"][label] = stats["labels"].get(label, 0) + 1

                # 进度回调
                if progress_callback:
                    progress_callback(i + 1, total, result)

            except QuotaExhaustedError:
                logger.error("\n\n💥 配额耗尽，中断处理！")
                break
            except Exception as e:
                logger.error(f"❌ 未捕获异常 {folder.name}: {e}")
                stats["failed"] += 1

        # 输出统计摘要
        self._print_stats(stats)
        
        return stats

    def _print_stats(self, stats: Dict) -> None:
        """打印统计摘要"""
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 打标完成统计")
        logger.info(f"{'='*60}")
        logger.info(f"总素材数: {stats['total']}")
        logger.info(f"成功: {stats['success']} ({stats['success']/max(stats['total'],1)*100:.1f}%)")
        logger.info(f"失败: {stats['failed']}")
        logger.info(f"跳过(缓存): {stats['skipped']}")
        
        logger.info(f"\n标签分布:")
        for label, count in sorted(stats["labels"].items(), key=lambda x: x[1], reverse=True):
            pct = count / max(stats['total'] - stats['failed'], 1) * 100
            bar = "█" * int(pct / 5)
            logger.info(f"  {label:<30} {count:>5} ({pct:>5.1f}%) {bar}")

        # 质量检查告警
        other_ratio = stats["labels"].get("其他", 0) / max(stats['total'] - stats['failed'], 1)
        if other_ratio > settings.quality_other_label_threshold:
            logger.warning(f"\n⚠️  质量告警: '其他'标签占比 {other_ratio*100:.1f}% > 阈值 {settings.quality_other_label_threshold*100}%")
            logger.warning("建议检查标签判定基准或切换Provider重新打标")

        if stats["errors"]:
            logger.error(f"\n❌ 错误详情:")
            for err in stats["errors"][:10]:  # 只显示前10个
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
        )
        
        await labeler.process_all(sample=args.sample)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="素材标签打标")
    parser.add_argument("--materials-dir", default="downloaded_materials", help="素材目录")
    parser.add_argument("--batch-size", type=int, default=None, help="每批数量")
    parser.add_argument("--batch-delay", type=float, default=None, help="批次延迟(秒)")
    parser.add_argument("--provider", default="gemini", choices=list(MaterialLabeler.PROVIDER_CONFIGS.keys()))
    parser.add_argument("--sample", type=int, default=None, help="采样数量")
    
    args = parser.parse_args()
    
    asyncio.run(MaterialLabeler.run_cli(args))
