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

from .config import settings


class MaterialArchiver:
    """
    素材归档报告生成器
    
    支持多种Provider，生成结构化的Markdown分镜头报告。
    """

    # 归档模板（Markdown格式）
    REPORT_TEMPLATE = """# 素材归档报告 - {material_id}

## 基本信息
- **素材ID**: {material_id}
- **素材类型**: {media_type}
- **处理时间**: {timestamp}
- **Provider**: {provider}
- **模型**: {model}

## 标签信息
- **主标签**: {label}
- **置信度**: {confidence:.2%}
- **判定理由**: {reasoning}

## 场景分析
{scenes_content}

## 综合标签
{tags_content}

---
*报告生成时间: {timestamp} | Provider: {provider}*
"""

    def __init__(
        self,
        provider: str = "minicpm",
        materials_dir: Path = None,
        output_dir: Path = None,
        cache_file: Path = None,
        media_type: str = "all",
        sample: int = None,
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
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 加载Provider配置
        self._load_provider_config()
        
        # 加载打标缓存
        self._cache: Dict[str, Any] = {}
        self._load_cache()

    def _load_provider_config(self) -> None:
        """加载Provider配置（复用Labeler的配置逻辑）"""
        from .labeler import MaterialLabeler
        
        configs = MaterialLabeler.PROVIDER_CONFIGS.get(self.provider)
        if not configs:
            raise ValueError(f"不支持的归档Provider: {self.provider}")

        api_key_env = configs["api_key_env"]
        env_name = api_key_env.replace("_API_KEY", "")
        api_key = getattr(settings, f"{env_name}_api_key".lower(), None)
        
        if not api_key:
            raise ValueError(f"未配置 {api_key_env}！")
        
        self.api_key = api_key
        self.model = configs["model"]
        
        base_url = configs["base_url"]
        if base_url == "auto":
            if self.provider == "minicpm":
                self.base_url = settings.minicpm_base_url
            else:
                raise ValueError(f"Provider {self.provider} URL配置错误")
        elif base_url == "mcp":
            self.base_url = None
        else:
            self.base_url = base_url

        logger.info(
            f"📡 归档Provider配置: {self.provider} | "
            f"模型: {self.model}"
        )

    def _load_cache(self) -> None:
        """加载打标缓存"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
                logger.info(f"📦 加载打标缓存: {len(self._cache)} 条记录")
            except Exception as e:
                logger.warning(f"⚠️  缓存文件损坏: {e}")
                self._cache = {}
        else:
            logger.warning("⚠️  未找到打标缓存文件，将仅基于文件内容归档")

    async def _call_api_for_archive(
        self,
        prompt: str,
        images: Optional[List[Path]] = None,
    ) -> str:
        """
        调用API生成归档内容
        
        Args:
            prompt: 归档prompt
            images: 图片列表
            
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
                    logger.warning(f"⚠️  图片读取失败: {e}")

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content_parts}],
            "max_tokens": 4096,  # 归档需要更长输出
            "temperature": 0.4,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:  # 归档可能较慢
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
            logger.debug(f"⏭️  已归档，跳过: {material_id}")
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
            logger.warning(f"⚠️  空文件夹: {material_id}")
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

        # 处理视频素材：抽帧转换为图片序列（归档可接受更多图片）
        frame_images = []
        if videos:
            try:
                from .video_utils import VideoProcessor
                
                with VideoProcessor(
                    default_fps=1.0,
                    default_max_frames=30,  # 归档时可接受更多帧
                    default_target_count=15, # 归档需要更详细的帧
                    keep_frames=False,
                ) as processor:
                    
                    for video in videos[:2]:  # 归档时最多处理2个视频
                        sampled_frames, video_info = processor.process_video(video)
                        frame_images.extend(sampled_frames)
                        
                        logger.debug(
                            f"🎬 视频抽帧(归档): {video.name} → "
                            f"{len(sampled_frames)}帧 ({video_info['duration']}s)"
                        )
                
                if frame_images:
                    logger.info(f"   📹 归档视频抽帧完成: {len(videos)}个视频 → {len(frame_images)}帧")
                
            except Exception as e:
                logger.warning(f"⚠️  归档视频抽帧失败，将仅使用原始图片: {e}")

        # 合并所有可用的图片（原始图片 + 抽帧图片）
        all_images = list(images) + frame_images

        try:
            # 构建归档prompt（根据是否有视频调整提示）
            media_type_hint = "视频素材（已抽帧为图片序列）" if videos else "图片素材"
            archive_prompt = f"""请为以下电商素材生成分镜头归档报告。

素材ID: {material_id}
标签: {label}
置信度: {confidence:.2%}
判定理由: {reasoning}
媒体类型: {media_type_hint}

请按以下格式输出Markdown报告：

## 场景1: [场景描述]
- **故事线**: [简述场景叙事]
- **运镜方式**: [固定/推拉摇移等]
- **动作描述**: [主体动作]

## 场景2: ...

## 综合标签
[列出3-5个综合标签，用逗号分隔]
"""

            # 调用API生成归档（归档可接受更多图片，最多20张）
            archive_text = await self._call_api_for_archive(
                prompt=archive_prompt,
                images=all_images[:20],
            )

            # 组装完整报告
            report_content = self.REPORT_TEMPLATE.format(
                material_id=material_id,
                media_type="视频" if videos else "图片",
                timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                provider=self.provider,
                model=self.model,
                label=label,
                confidence=confidence,
                reasoning=reasoning or "无",
                scenes_content=archive_text,
                tags_content="",  # 从archive_text中提取
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
            
            logger.success(f"✅ 归档完成: {material_id} → {report_path.name}")
            return result

        except Exception as e:
            logger.error(f"❌ 归档失败 {material_id}: {e}")
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
        logger.info(f"📦 开始归档处理")
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
                logger.error(f"❌ 未捕获异常 {folder.name}: {e}")
                stats["failed"] += 1

        # 输出统计
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 归档完成统计")
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
        )
        
        await archiver.process_all()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="素材归档报告生成")
    parser.add_argument("--materials-dir", default=None, help="素材目录")
    parser.add_argument("--output-dir", default=None, help="输出目录")
    parser.add_argument("--provider", default="minicpm")
    parser.add_argument("--media-type", choices=["image", "video", "all"], default="all")
    parser.add_argument("--sample", type=int, default=None, help="采样数量")
    
    args = parser.parse_args()
    
    asyncio.run(MaterialArchiver.run_cli(args))