import os
"""
缓存导出器 - 将JSON缓存导出为Excel格式
"""
import json
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd
from loguru import logger

from .config import settings


class CacheExporter:
    """
    缓存导出器
    
    将打标/归档的JSON缓存导出为Excel格式，
    使用原子写入确保文件完整性。
    """

    def __init__(
        self,
        cache_file: Path = None,
        output_dir: Path = None,
        output_filename: str = None,
    ):
        """
        初始化导出器
        
        Args:
            cache_file: 缓存文件路径（默认 labeling_cache.json）
            output_dir: 输出目录（默认 excel_exports/）
            output_filename: 输出文件名（默认 results_时间戳.xlsx）
        """
        self.cache_file = Path(cache_file) if cache_file else settings.cache_dir / "labeling_cache.json"
        self.output_dir = Path(output_dir) if output_dir else settings.excel_export_dir
        
        # 生成输出文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_filename = output_filename or f"results_{timestamp}.xlsx"
        
        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_cache(self) -> Dict[str, Any]:
        """
        加载缓存数据
        
        Returns:
            Dict: 缓存数据
        """
        if not self.cache_file.exists():
            raise FileNotFoundError(f"缓存文件不存在: {self.cache_file}")

        logger.info(f"📦 加载缓存: {self.cache_file}")
        
        with open(self.cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        logger.info(f"   记录数: {len(cache_data)}")
        return cache_data

    def transform_to_dataframe(self, cache_data: Dict[str, Any]) -> pd.DataFrame:
        """
        将缓存数据转换为DataFrame
        
        Args:
            cache_data: 缓存字典
            
        Returns:
            pd.DataFrame: 结构化数据
        """
        records = []
        
        for material_id, data in cache_data.items():
            record = {
                "material_id": material_id,
                "label": data.get("label", ""),
                "confidence": data.get("confidence", 0.0),
                "provider": data.get("provider", ""),
                "model": data.get("model", ""),
                "timestamp": data.get("timestamp", ""),
                "error": data.get("error", ""),
                "reasoning": data.get("reasoning", "")[:200] if data.get("reasoning") else "",  # 截断长文本
            }
            records.append(record)

        df = pd.DataFrame(records)
        
        # 按置信度排序（高到低）
        df = df.sort_values(by=["confidence"], ascending=False)
        
        # 重置索引
        df.reset_index(drop=True, inplace=True)
        
        return df

    def export_to_excel(
        self,
        include_summary: bool = True,
        include_label_distribution: bool = True,
    ) -> Path:
        """
        导出缓存到Excel
        
        Args:
            include_summary: 是否包含汇总Sheet
            include_label_distribution: 是否包含标签分布统计
            
        Returns:
            Path: 导出的Excel文件路径
        """
        # 加载数据
        cache_data = self.load_cache()
        df = self.transform_to_dataframe(cache_data)
        
        # 创建Excel writer（使用tempfile实现原子写入）
        output_path = self.output_dir / self.output_filename
        temp_fd, temp_path = tempfile.mkstemp(suffix=".xlsx", dir=self.output_dir)
        
        try:
            with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
                # Sheet 1: 完整数据
                df.to_excel(writer, sheet_name="打标结果", index=False)
                
                # 调整列宽
                worksheet = writer.sheets["打标结果"]
                for idx, col in enumerate(df.columns):
                    max_length = max(
                        df[col].astype(str).map(len).max(),
                        len(col)
                    )
                    worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)
                
                if include_summary:
                    # Sheet 2: 汇总统计
                    summary_data = {
                        "指标": [
                            "总素材数",
                            "成功打标",
                            "失败/错误",
                            "其他标签",
                            "平均置信度",
                            "导出时间",
                        ],
                        "值": [
                            len(df),
                            len(df[df["label"].notna() & (df["error"] == "")]),
                            len(df[df["error"] != ""]),
                            len(df[df["label"] == "其他"]),
                            f"{df['confidence'].mean():.2%}",
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        ],
                    }
                    summary_df = pd.DataFrame(summary_data)
                    summary_df.to_excel(writer, sheet_name="汇总统计", index=False)
                
                if include_label_distribution:
                    # Sheet 3: 标签分布
                    label_counts = df["label"].value_counts()
                    label_df = pd.DataFrame({
                        "标签": label_counts.index,
                        "数量": label_counts.values,
                        "占比": (label_counts.values / len(df) * 100).round(2),
                    })
                    label_df.to_excel(writer, sheet_name="标签分布", index=False)

            # 原子重命名：临时文件 → 最终文件
            import os
            try:
                os.close(temp_fd)
                os.replace(str(temp_path), str(output_path))
            except Exception as e:
                # 清理临时文件
                try:
                    os.unlink(temp_path)
                except:
                    pass
                raise e
            
            file_size = output_path.stat().st_size / 1024  # KB
            logger.success(f"\n✅ Excel导出完成")
            logger.info(f"   文件: {output_path}")
            logger.info(f"   大小: {file_size:.2f} KB")
            logger.info(f"   记录数: {len(df)}")
            
            return output_path

        except Exception as e:
            # 清理临时文件
            try:
                os.close(temp_fd)
                os.unlink(temp_path)
            except:
                pass
            raise Exception(f"Excel导出失败: {e}")


def main():
    """CLI入口点"""
    import argparse
    
    parser = argparse.ArgumentParser(description="缓存导出到Excel")
    parser.add_argument("--cache-file", default=None, help="缓存文件路径")
    parser.add_argument("--output-dir", default=None, help="输出目录")
    parser.add_argument("--output-filename", default=None, help="输出文件名")
    
    args = parser.parse_args()
    
    exporter = CacheExporter(
        cache_file=args.cache_file,
        output_dir=args.output_dir,
        output_filename=args.output_filename,
    )
    
    exporter.export_to_excel()


if __name__ == "__main__":
    main()
