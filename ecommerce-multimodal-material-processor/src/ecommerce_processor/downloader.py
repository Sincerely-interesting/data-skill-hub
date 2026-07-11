"""
素材下载器 - 从Excel/CSV批量下载素材
"""
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import httpx
from tqdm import tqdm
from loguru import logger

from .config import settings


class MaterialDownloader:
    """
    素材下载器
    
    支持从Excel/CSV文件中提取URL并并发下载，
    提供断点续传、错误记录等企业级特性。
    """

    def __init__(
        self,
        excel_path: Path = None,
        output_dir: Path = Path("downloaded_materials"),
        workers: int = None,
        sample: int = None,
    ):
        """
        初始化下载器
        
        Args:
            excel_path: Excel/CSV文件路径
            output_dir: 输出目录（默认 downloaded_materials/）
            workers: 并发下载数量（默认从settings读取）
            sample: 采样数量
        """
        self.excel_path = Path(excel_path) if excel_path else None
        self.output_dir = Path(output_dir)
        self.workers = workers or settings.default_workers
        self.sample = sample
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 下载状态文件
        self.status_file = self.output_dir / "download_status.json"
        self._status: Dict[str, Any] = {}
        self._load_status()

    def _load_status(self) -> None:
        """加载下载状态（用于断点续传）"""
        if self.status_file.exists():
            try:
                with open(self.status_file, "r", encoding="utf-8") as f:
                    self._status = json.load(f)
                logger.info(f"📦 加载下载状态: {len(self._status)} 条记录")
            except Exception as e:
                logger.warning(f"⚠️  状态文件损坏，将重新开始: {e}")
                self._status = {}

    def _save_status(self) -> None:
        """保存下载状态"""
        try:
            with open(self.status_file, "w", encoding="utf-8") as f:
                json.dump(self._status, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ 状态保存失败: {e}")

    def read_excel_urls(self) -> List[Dict]:
        """
        从Excel/CSV读取URL列表
        
        Returns:
            List[Dict]: [{material_id: str, url: str}, ...]
        """
        if not self.excel_path or not self.excel_path.exists():
            raise FileNotFoundError(f"Excel文件不存在: {self.excel_path}")

        logger.info(f"📊 读取Excel/CSV: {self.excel_path}")

        # 根据扩展名选择读取方式
        suffix = self.excel_path.suffix.lower()
        if suffix in [".xlsx", ".xls"]:
            df = pd.read_excel(self.excel_path)
        elif suffix == ".csv":
            df = pd.read_csv(self.excel_path)
        else:
            raise ValueError(f"不支持的文件格式: {suffix}。仅支持 .xlsx/.xls/.csv")

        # 检查必需列
        required_cols = ["material_id", "url"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            # 尝试常见变体名
            col_mapping = {
                "material_id": ["id", "素材ID", "素材编号", "product_id"],
                "url": ["image_url", "video_url", "素材链接", "链接", "download_url"],
            }
            
            for req_col in missing_cols[:]:
                for alt_col in col_mapping.get(req_col, []):
                    if alt_col in df.columns:
                        df.rename(columns={alt_col: req_col}, inplace=True)
                        missing_cols.remove(req_col)
                        break
            
            if missing_cols:
                raise ValueError(
                    f"缺少必需列: {missing_cols}。当前列: {list(df.columns)}"
                )

        # 提取URL列表
        urls_list = df[["material_id", "url"]].to_dict("records")
        
        if self.sample:
            urls_list = urls_list[:self.sample]

        logger.info(f"   发现 {len(urls_list)} 条URL记录")
        return urls_list

    def download_single_url(self, record: Dict) -> Dict:
        """
        下载单个素材
        
        Args:
            record: {"material_id": str, "url": str}
            
        Returns:
            Dict: 下载结果
        """
        material_id = str(record["material_id"])
        url = record["url"]

        # 检查是否已下载
        material_dir = self.output_dir / material_id
        
        if material_dir.exists() and any(material_dir.iterdir()):
            logger.debug(f"⏭️  已存在，跳过: {material_id}")
            return {
                "material_id": material_id,
                "url": url,
                "status": "skipped",
                "path": str(material_dir),
            }

        # 检查是否之前失败过
        if self._status.get(material_id, {}).get("status") == "failed":
            fail_count = self._status[material_id].get("fail_count", 0)
            if fail_count >= 3:
                logger.warning(f"⚠️  多次失败，跳过: {material_id} (失败{fail_count}次)")
                return {
                    "material_id": material_id,
                    "url": url,
                    "status": "permanently_failed",
                    "error": f"多次失败({fail_count}次)",
                }

        try:
            # 创建素材目录
            material_dir.mkdir(parents=True, exist_ok=True)

            # 根据URL确定文件类型和扩展名
            url_lower = url.lower()
            if any(ext in url_lower for ext in [".mp4", ".mov", ".avi"]):
                ext = url[url_lower.rfind("."):]
                filename = f"content{ext}"
            elif any(img_ext in url_lower for img_ext in [".jpg", ".jpeg", ".png", ".webp"]):
                ext = url[url_lower.rfind("."):]
                filename = f"content{ext}"
            else:
                # 默认尝试图片格式
                filename = "content.jpg"

            file_path = material_dir / filename

            # 下载文件
            logger.debug(f"⬇️  下载: {material_id} → {filename}")
            
            with httpx.stream("GET", url, timeout=30.0, follow_redirects=True) as response:
                response.raise_for_status()
                
                with open(file_path, "wb") as f:
                    for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)

            file_size = file_path.stat().st_size / 1024  # KB

            result = {
                "material_id": material_id,
                "url": url,
                "status": "success",
                "path": str(file_path),
                "file_size_kb": round(file_size, 2),
                "timestamp": datetime.now().isoformat(),
            }

            # 更新状态
            self._status[material_id] = result
            self._save_status()

            return result

        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP错误 {e.response.status_code}: {url}"
            logger.warning(f"❌ {error_msg}")
            self._record_failure(material_id, url, error_msg)
            return {"material_id": material_id, "url": url, "status": "failed", "error": error_msg}

        except httpx.TimeoutException:
            error_msg = f"下载超时: {url}"
            logger.warning(f"❌ {error_msg}")
            self._record_failure(material_id, url, error_msg)
            return {"material_id": material_id, "url": url, "status": "failed", "error": error_msg}

        except Exception as e:
            error_msg = f"下载失败: {str(e)}"
            logger.error(f"❌ {material_id}: {error_msg}")
            self._record_failure(material_id, url, error_msg)
            return {"material_id": material_id, "url": url, "status": "failed", "error": error_msg}

    def _record_failure(self, material_id: str, url: str, error: str) -> None:
        """记录失败信息"""
        existing = self._status.get(material_id, {})
        fail_count = existing.get("fail_count", 0) + 1
        
        self._status[material_id] = {
            "material_id": material_id,
            "url": url,
            "status": "failed",
            "error": error,
            "fail_count": fail_count,
            "last_attempt": datetime.now().isoformat(),
        }
        self._save_status()

    def process_all(self) -> Dict:
        """
        处理所有URL下载
        
        Returns:
            Dict: 统计信息
        """
        # 读取URL列表
        urls_list = self.read_excel_urls()

        total = len(urls_list)
        logger.info(f"\n{'='*60}")
        logger.info(f"📥 开始素材下载")
        logger.info(f"   文件: {self.excel_path}")
        logger.info(f"   总数: {total}")
        logger.info(f"   并发: {self.workers}")
        logger.info(f"   输出: {self.output_dir}/")
        logger.info(f"{'='*60}\n")

        stats = {
            "total": total,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "errors": [],
        }

        # 使用线程池并发下载
        results = []
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = {
                executor.submit(self.download_single_url, record): record 
                for record in urls_list
            }

            pbar = tqdm(as_completed(futures), total=total, desc="Downloading", unit="file")
            
            for future in pbar:
                try:
                    result = future.result()
                    results.append(result)

                    status = result["status"]
                    if status == "success":
                        stats["success"] += 1
                    elif status == "skipped":
                        stats["skipped"] += 1
                    elif status == "failed":
                        stats["failed"] += 1
                        stats["errors"].append(result)
                    elif status == "permanently_failed":
                        stats["failed"] += 1

                except Exception as e:
                    logger.error(f"❌ 未捕获异常: {e}")
                    stats["failed"] += 1

        # 输出统计
        self._print_stats(stats)
        
        return stats

    def _print_stats(self, stats: Dict) -> None:
        """打印统计摘要"""
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 下载完成统计")
        logger.info(f"{'='*60}")
        logger.info(f"总URL数: {stats['total']}")
        logger.info(f"成功: {stats['success']} ({stats['success']/max(stats['total'],1)*100:.1f}%)")
        logger.info(f"跳过(已存在): {stats['skipped']}")
        logger.info(f"失败: {stats['failed']}")
        
        # 计算总大小（从stats中无法直接获取，需要从下载结果中统计）
        # 注意：total_size 需要在 process_all 中传递或重新计算
        logger.info(f"   详见 download_status.json 获取详细信息")

        if stats["errors"]:
            logger.error(f"\n❌ 错误详情:")
            for err in stats["errors"][:10]:
                logger.error(f"  - {err.get('material_id')}: {err.get('error', 'Unknown')}")

        logger.info(f"\n💾 下载状态已保存: {self.status_file}")
        logger.info(f"   下次运行将自动跳过已下载的素材")
        logger.info(f"{'='*60}")


def download_from_local_directory(
    materials_dir: Path,
    output_dir: Path = None,
) -> Dict:
    """
    从本地目录扫描素材（不下载，只确认路径）
    
    Args:
        materials_dir: 本地素材目录
        output_dir: 输出目录（如需复制）
        
    Returns:
        Dict: 统计信息
    """
    materials_dir = Path(materials_dir)
    
    if not materials_dir.exists():
        raise FileNotFoundError(f"素材目录不存在: {materials_dir}")

    folders = [
        f for f in materials_dir.iterdir() 
        if f.is_dir() and not f.name.startswith(".")
    ]

    images = 0
    videos = 0
    
    for folder in folders:
        for ext in ["*.jpg", "*.jpeg", "*.png", "*.webp"]:
            images += len(list(folder.glob(ext)))
        for ext in ["*.mp4", "*.mov", "*.avi"]:
            videos += len(list(folder.glob(ext)))

    stats = {
        "source": "local_directory",
        "path": str(materials_dir),
        "total_folders": len(folders),
        "total_images": images,
        "total_videos": videos,
    }

    logger.info(f"\n📂 本地目录扫描结果:")
    logger.info(f"   路径: {materials_dir}/")
    logger.info(f"   素材文件夹: {len(folders)} 个")
    logger.info(f"   图片: {images} 张")
    logger.info(f"   视频: {videos} 个")

    return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="素材下载器")
    parser.add_argument("--excel", help="Excel/CSV文件路径")
    parser.add_argument("--output-dir", default="downloaded_materials", help="输出目录")
    parser.add_argument("--workers", type=int, default=None, help="并发数")
    parser.add_argument("--sample", type=int, default=None, help="采样数量")
    parser.add_argument("--local-dir", help="本地素材目录（不下载，只扫描）")
    
    args = parser.parse_args()
    
    if args.local_dir:
        download_from_local_directory(args.local_dir)
    else:
        downloader = MaterialDownloader(
            excel_path=args.excel,
            output_dir=args.output_dir,
            workers=args.workers,
            sample=args.sample,
        )
        downloader.process_all()