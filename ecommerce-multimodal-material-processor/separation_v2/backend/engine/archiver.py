"""
素材归档报告生成器 - 分镜头脚本归档
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

from .config import settings, resolve_video_url, resolve_template_path, build_video_part


class MaterialArchiver:
    """
    素材归档报告生成器
    
    支持多种Provider，生成结构化的Markdown分镜头报告。
    """

    # 报告溯源头/尾：模型按模板输出的 markdown 直接作为报告主体，
    # 仅前后追加最小溯源信息，避免对模型输出二次包裹导致结构重复。
    PROVENANCE_HEADER = """---
素材ID: {material_id}
素材类型: {media_type}
归档时间: {timestamp}
Provider: {provider} | 模型: {model}
---

"""

    PROVENANCE_FOOTER = """

---
*本报告由 AI 按配置模板自动归档生成 · Provider: {provider} · 模型: {model} · 时间: {timestamp}*
"""

    def __init__(
        self,
        provider: str = "custom_minmax",
        materials_dir: Path = None,
        output_dir: Path = None,
        cache_file: Path = None,
        media_type: str = "all",
        sample: int = None,
        template: str = None,
    ):
        """
        初始化归档器
        
        Args:
            provider: Provider名称
            materials_dir: 素材目录（默认使用打标缓存）
            output_dir: 输出目录（默认 material_archives/）
            cache_file: 打标缓存文件
            media_type: 媒体类型 (image/video/all)
            sample: 采样数量
        """
        self.provider = provider.lower()
        self.materials_dir = Path(materials_dir) if materials_dir else settings.cache_dir / "downloaded_materials"
        self.output_dir = Path(output_dir) if output_dir else settings.archive_output_dir
        self.cache_file = Path(cache_file) if cache_file else settings.cache_dir / "labeling_cache.json"
        self.media_type = media_type
        self.sample = sample
        # 归档模板：显式传入优先，否则读配置文件（archive_template）
        self.template = (template or settings.archive_template or "storyboard").strip().lower()
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载Provider配置
        self._load_provider_config()
        
        # 加载打标缓存
        self._cache: Dict[str, Any] = {}
        self._load_cache()

    def _load_provider_config(self) -> None:
        """加载 Provider 配置（归档需看图，使用 VLM 配置，与文本 LLM 完全独立）"""
        from .labeler import MaterialLabeler

        configs = MaterialLabeler.PROVIDER_CONFIGS.get(self.provider)
        if not configs:
            raise ValueError(f"不支持的归档Provider: {self.provider}")

        api_key_env = configs["api_key_env"]
        env_name = api_key_env.replace("_API_KEY", "").lower()
        api_key = getattr(settings, f"{env_name}_api_key", None)
        # VLM 独立密钥优先
        if settings.vlm_api_key:
            api_key = settings.vlm_api_key

        if not api_key:
            raise ValueError(f"未配置 {api_key_env}！")

        self.api_key = api_key
        # custom_minmax 等 provider 的 model 在 PROVIDER_CONFIGS 中为 None，
        # 兜底使用 settings.vlm_model
        self.model = configs["model"] or settings.vlm_model

        base_url = configs["base_url"]
        if base_url == "auto":
            if self.provider == "minicpm":
                resolved = settings.minicpm_base_url
            else:
                raise ValueError(f"Provider {self.provider} URL配置错误")
        elif base_url == "mcp":
            resolved = None
        else:
            resolved = base_url

        # VLM 独立地址优先（与文本 LLM 分离）
        self.base_url = settings.vlm_base_url or resolved

        logger.info(
            f" 归档Provider配置: {self.provider} | "
            f"模型: {self.model} | "
            f"Base URL: {self.base_url}"
        )

    def _load_cache(self) -> None:
        """加载打标缓存"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                logger.info(f" 加载打标缓存: {len(self._cache)} 条记录")
            except Exception as e:
                logger.warning(f"  缓存文件损坏: {e}")
                self._cache = {}
        else:
            logger.warning("  未找到打标缓存文件，将仅基于文件内容归档")

    async def _call_api_for_archive(
        self,
        prompt: str,
        images: Optional[List[Path]] = None,
        videos: Optional[List[Path]] = None,
    ) -> str:
        """
        调用API生成归档内容

        Args:
            prompt: 归档prompt
            images: 图片列表
            videos: 视频列表（直接以 video_url URL 传入，绝不转 base64）

        Returns:
            str: 生成的归档文本
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        content_parts = [{"type": "text", "text": prompt}]

        # 添加图片
        if images:
            for img_path in images[:20]:  # 归档可接受更多图片
                try:
                    image_data = base64.standard_b64encode(img_path.read_bytes()).decode("utf-8")
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}
                    })
                except Exception as e:
                    logger.warning(f"  图片读取失败: {e}")

        # 添加视频（直接以 URL 引用传给 VLM，绝不转 base64，且不抽帧）
        if videos:
            material_id = Path(videos[0]).parent.name
            for video_path in videos[:getattr(settings, "max_videos", 3)]:
                try:
                    video_url = resolve_video_url(video_path, material_id)
                    # 字段形态由 config.build_video_part 按 video_payload_format 决定
                    content_parts.append(build_video_part(video_url))
                except Exception as e:
                    logger.warning(f"  视频URL解析失败: {e}")

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content_parts}],
            "max_tokens": settings.vlm_max_tokens,
            "temperature": settings.vlm_temperature,
        }

        async with httpx.AsyncClient(timeout=settings.vlm_timeout_ms / 1000.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )

            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]
            else:
                raise Exception(f"API错误 HTTP {response.status_code}: {response.text}")

    def _load_archive_template(self) -> str:
        """读取配置选定的归档模板全文（由 self.template 决定读哪一个）。

        模板用于让模型 *参照格式* 把视频还原为分镜头脚本原文（storyboard）
        或做全维内容理解分析（full_dimension）。
        读取失败则回退为空字符串（调用方退化为内置精简提示词）。
        """
        try:
            tp = resolve_template_path(self.template)
            text = tp.read_text(encoding="utf-8")
            logger.info(f"  已载入归档模板[{self.template}]: {tp.name}（{len(text)} 字符）")
            return text
        except Exception as e:
            logger.warning(f"  归档模板[{self.template}]读取失败（{e}），将退化为内置精简提示词")
            return ""

    def _build_archive_prompt(
        self,
        material_id: str,
        label: str,
        confidence: float,
        reasoning: str,
        template_text: str,
        media_type_hint: str,
        template_name: str = None,
    ) -> str:
        """构建归档提示词：文本提示词 + 参照模板 + 还原视频原文。

        对接方式对齐 Gemma 视觉视频能力（google-genai 文档）：
        以 *文本提示词 + 本地视频资源路径* 一并送给模型，模型直接理解视频 ——
        本仓库通过“URL 引用”（config.resolve_video_url 产出纯 URL，不 base64、不抽帧）
        配合 config.build_video_part 按 video_payload_format 拼装视频部件实现该语义
        （openai_compatible / gemma_hf / gemini 三种形态），不抽帧、不转 base64。

        Args:
            template_text: 模板全文；为空时退化为内置精简分镜头提示词。
            template_name: 模板类型（storyboard / full_dimension），用于自适应提示词目标措辞。
        """
        if template_text:
            # 依据模板类型调整“目标”措辞：
            #   storyboard      → 还原成视频原文（分镜头脚本）
            #   full_dimension → 全维内容理解分析
            if (template_name or self.template) == "full_dimension":
                goal = ("请按下方模板对提供的视频做**全维内容理解分析**，"
                        "覆盖商品/画面/叙事/营销等维度，输出结构化分析 Markdown。")
            else:
                goal = ("请严格**参照下方模板**，把提供的视频**还原成视频原文"
                        "（原始分镜头脚本）** —— 即尽量还原视频原本的"
                        "叙事结构、画面、运镜、人物动作、台词/旁白/字幕、"
                        "时长节奏与灯光布光等要素。\n"
                        "不要做泛泛的内容总结，要\"还原\"：像把这条视频逆向拆解为可直接复用的分镜头脚本。")
            return f"""你是一名专业的电商视频内容分析专家。{goal}

素材元信息：
- 素材ID: {material_id}
- 已知标签: {label}
- 置信度: {confidence:.2%}
- 判定理由: {reasoning}
- 媒体类型: {media_type_hint}

===== 参照模板（输出必须严格遵循其结构与字段） =====
{template_text}
===== 模板结束 =====

请直接输出完整的 Markdown 归档文件内容（严格按模板结构，无需额外解释）。"""
        # 退化兜底：未配置 / 未读取到模板时
        return f"""请为以下电商素材生成分镜头归档报告（Markdown）。

素材ID: {material_id}
标签: {label}
置信度: {confidence:.2%}
判定理由: {reasoning}
媒体类型: {media_type_hint}

请按以下格式输出：

## 场景1: [场景描述]
- **故事脚本**: [简述场景叙事]
- **运镜方式**: [固定/推拉摇移等]
- **动作描述**: [主体动作]

## 场景2: ...

## 综合标签
[列出3-5个综合标签，用逗号分隔]
"""

    async def archive_single_folder(self, folder_path: Path) -> Dict:
        """
        归档单个素材文件夹
        
        Args:
            folder_path: 素材文件夹路径
            
        Returns:
            Dict: 归档结果
        """
        material_id = folder_path.name
        
        # 检查是否已归档
        report_path = self.output_dir / f"{material_id}_report.md"
        if report_path.exists():
            logger.debug(f"⏭  已归档，跳过: {material_id}")
            return {
                "material_id": material_id,
                "status": "skipped",
                "report_path": str(report_path),
            }

        # 收集媒体文件
        images = []
        videos = []
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
            images.extend(folder_path.glob(ext))
        for ext in ["*.mp4", "*.mov", "*.avi"]:
            videos.extend(folder_path.glob(ext))

        if not images and not videos:
            logger.warning(f"  空文件夹: {material_id}")
            return {
                "material_id": material_id,
                "status": "empty",
                "error": "空文件夹",
            }

        # 获取打标信息
        label_info = self._cache.get(material_id, {})
        label = label_info.get("label", "未知")
        confidence = label_info.get("confidence", 0.0)
        reasoning = label_info.get("reasoning", "")

        # 处理视频素材（视频直接传输，绝对不抽帧）
        video_files_for_archive = []
        if videos:
            # 视频直接传输：把整个视频作为 video_url 直接传给模型，
            # 不依赖 ffmpeg 抽帧，也不转 base64。
            # video_url 必须是 provider 可访问的直接 URL（见 config.resolve_video_url）。
            logger.info(f"视频直接传输: 将 {len(videos)} 个视频直接传给模型生成归档（不抽帧）")
            video_files_for_archive = videos[:getattr(settings, "max_videos", 3)]

        # 合并所有可用的图片（仅原始图片；视频走直接传输，不抽帧）
        all_images = list(images)

        # 既无图片也无法提供视频输入时，跳过 API 调用（避免空跑）
        if not all_images and not video_files_for_archive:
            logger.warning(f"  {material_id}: 无可用视觉输入(图片读取失败且视频不可用)，跳过归档")
            return {
                "material_id": material_id,
                "status": "skipped",
                "error": "无可用视觉输入",
            }

        try:
            # 构建归档prompt：配置文件选定模板 + 还原视频原文指令
            # 视频以 video_url 本地 path(file://) 直接传入（不抽帧、不 base64），
            # 对齐 Gemma 视觉视频能力：文本提示词 + 本地资源路径 → AI 分析视频。
            media_type_hint = "视频素材（直接传输，本地路径）" if videos else "图片素材"
            template_text = self._load_archive_template()
            archive_prompt = self._build_archive_prompt(
                material_id, label, confidence, reasoning, template_text,
                media_type_hint, template_name=self.template,
            )

            # 调用API生成归档（归档可接受更多图片，最多20张；视频直传最多 max_videos 个）
            archive_text = await self._call_api_for_archive(
                prompt=archive_prompt,
                images=all_images[:20],
                videos=video_files_for_archive,
            )

            # 组装最终报告：模型按模板输出的 Markdown 直接作为主体，
            # 仅前后追加最小溯源信息（不再二次包裹，避免结构重复）。
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            report_content = (
                self.PROVENANCE_HEADER.format(
                    material_id=material_id,
                    media_type="视频" if videos else "图片",
                    timestamp=ts,
                    provider=self.provider,
                    model=self.model,
                )
                + archive_text
                + self.PROVENANCE_FOOTER.format(
                    provider=self.provider,
                    model=self.model,
                    timestamp=ts,
                )
            )

            # 写入报告文件
            report_path.write_text(report_content, encoding="utf-8")

            result = {
                "material_id": material_id,
                "status": "success",
                "report_path": str(report_path),
                "label": label,
                "provider": self.provider,
                "timestamp": datetime.now().isoformat(),
            }
            
            logger.success(f" 归档完成: {material_id} → {report_path.name}")
            return result

        except Exception as e:
            logger.error(f" 归档失败 {material_id}: {e}")
            return {
                "material_id": material_id,
                "status": "failed",
                "error": str(e),
            }

    async def process_all(self, progress_callback=None) -> Dict:
        """
        处理所有素材归档
        
        Returns:
            Dict: 统计信息
        """
        folders = [
            f for f in self.materials_dir.iterdir()
            if f.is_dir() and not f.name.startswith(".")
        ]

        if self.sample:
            folders = folders[:self.sample]

        total = len(folders)
        logger.info(f"\n{'='*60}")
        logger.info(f" 开始归档处理")
        logger.info(f"   Provider: {self.provider}")
        logger.info(f"   素材总数: {total}")
        logger.info(f"   输出目录: {self.output_dir}")
        logger.info(f"{'='*60}\n")

        stats = {
            "total": total,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "reports": [],
        }

        pbar = tqdm(folders, desc="Archiving", unit="folder")

        for i, folder in enumerate(pbar):
            try:
                result = await self.archive_single_folder(folder)
                
                if result["status"] == "success":
                    stats["success"] += 1
                    stats["reports"].append(result["report_path"])
                elif result["status"] == "skipped":
                    stats["skipped"] += 1
                else:
                    stats["failed"] += 1

                if progress_callback:
                    progress_callback(i + 1, total, result)

            except Exception as e:
                logger.error(f" 未捕获异常 {folder.name}: {e}")
                stats["failed"] += 1

        # 输出统计
        logger.info(f"\n{'='*60}")
        logger.info(f" 归档完成统计")
        logger.info(f"{'='*60}")
        logger.info(f"总素材数: {stats['total']}")
        logger.info(f"成功: {stats['success']}")
        logger.info(f"跳过(已存在): {stats['skipped']}")
        logger.info(f"失败: {stats['failed']}")
        logger.info(f"\n报告保存至: {self.output_dir}/")
        logger.info(f"{'='*60}")

        return stats

    @staticmethod
    async def run_cli(args):
        """CLI入口点"""
        archiver = MaterialArchiver(
            provider=args.provider,
            materials_dir=args.materials_dir,
            output_dir=args.output_dir,
            media_type=args.media_type,
            sample=args.sample,
            template=getattr(args, "archive_template", None),
        )
        
        await archiver.process_all()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="素材归档报告生成")
    parser.add_argument("--materials-dir", default=None, help="素材目录")
    parser.add_argument("--output-dir", default=None, help="输出目录")
    parser.add_argument("--provider", default="custom_minmax")
    parser.add_argument("--media-type", choices=["image", "video", "all"], default="all")
    parser.add_argument("--sample", type=int, default=None, help="采样数量")
    
    args = parser.parse_args()
    
    asyncio.run(MaterialArchiver.run_cli(args))