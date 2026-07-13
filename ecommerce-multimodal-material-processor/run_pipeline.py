"""
统一CLI入口 - 电商多模态素材处理流水线
"""
import sys
import asyncio
import argparse
from pathlib import Path
from typing import TYPE_CHECKING

# 添加src目录到Python路径（运行时必需）
sys.path.insert(0, str(Path(__file__).parent / "src"))

# 类型检查时的导入提示（帮助IDE静态分析）
if TYPE_CHECKING:
    from ecommerce_processor.config import Settings
    from ecommerce_processor.labeler import MaterialLabeler as LabelerType
    from ecommerce_processor.archiver import MaterialArchiver as ArchiverType
    from ecommerce_processor.downloader import MaterialDownloader as DownloaderType
    from ecommerce_processor.exporter import CacheExporter as ExporterType
    from ecommerce_processor.deps_checker import DependencyChecker as CheckerType

# 运行时导入
from ecommerce_processor import (
    settings,
    check_dependencies,
    MaterialLabeler,
    MaterialArchiver,
    MaterialDownloader,
    CacheExporter,
)
from ecommerce_processor.deps_checker import DependencyChecker
from loguru import logger


def setup_logging(level: str = "INFO"):
    """配置日志"""
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    logger.add(
        "logs/ecommerce_processor_{time:YYYYMMDD}.log",
        rotation="500 MB",
        retention="7 days",
        level="DEBUG",
        encoding="utf-8",
    )


def cmd_doctor(args):
    """环境检查命令"""
    print("\n" + "=" * 60)
    print(" 环境预检 (Doctor)")
    print("=" * 60 + "\n")
    
    checker = DependencyChecker()
    passed, errors, warnings = checker.run_full_check()
    
    if passed:
        print("\n 环境检查通过，可以开始处理！")
        return 0
    else:
        print(f"\n 发现 {len(errors)} 个问题，请修复后重试。")
        return 1


def cmd_download(args):
    """素材下载命令"""
    if args.local_dir:
        # 本地目录模式（只扫描，不下载）
        from ecommerce_processor.downloader import download_from_local_directory
        
        print("\n 扫描本地目录...")
        stats = download_from_local_directory(args.local_dir)
        
        print(f"\n 扫描完成:")
        print(f"   文件夹数: {stats['total_folders']}")
        print(f"   图片: {stats['total_images']}")
        print(f"   视频: {stats['total_videos']}")
        return 0
    
    else:
        # Excel下载模式
        downloader = MaterialDownloader(
            excel_path=args.excel,
            output_dir=args.output_dir or Path("downloaded_materials"),
            workers=args.workers,
            sample=args.sample,
        )
        
        stats = downloader.process_all()
        
        if stats["failed"] > 0:
            return 1
        return 0


async def cmd_label(args):
    """打标命令"""
    labeler = MaterialLabeler(
        provider=args.provider,
        model=args.model,
        materials_dir=args.materials_dir,
        batch_size=args.batch_size,
        batch_delay=args.batch_delay,
        force=args.force,
    )
    
    await labeler.process_all(sample=args.sample)
    return 0


async def cmd_archive(args):
    """归档命令"""
    archiver = MaterialArchiver(
        provider=args.provider,
        materials_dir=args.materials_dir,
        output_dir=args.output_dir,
        media_type=args.media_type,
        sample=args.sample,
    )
    
    await archiver.process_all()
    return 0


def cmd_export(args):
    """导出Excel命令"""
    exporter = CacheExporter(
        cache_file=args.cache_file,
        output_dir=args.output_dir,
        output_filename=args.filename,
    )
    
    exporter.export_to_excel()
    return 0


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="电商多模态素材处理流水线 - 企业级独立运行版本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 环境检查
  python run_pipeline.py doctor
  
  # 从Excel下载素材
  python run_pipeline.py download --excel materials.xlsx --workers 5 --sample 100
  
  # 使用本地素材进行打标
  python run_pipeline.py label --provider gemini --materials-dir ./downloaded_materials
  
  # 归档报告生成
  python run_pipeline.py archive --provider minicpm --media-type image
  
  # 导出Excel
  python run_pipeline.py export --cache-file labeling_cache.json

完整流水线:
  python run_pipeline.py doctor && \\
  python run_pipeline.py download --excel materials.xlsx && \\
  python run_pipeline.py label --provider gemini && \\
  python run_pipeline.py archive --provider minicpm && \\
  python run_pipeline.py export
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # doctor 命令
    parser_doctor = subparsers.add_parser("doctor", help="环境依赖检查")
    parser_doctor.set_defaults(func=cmd_doctor)

    # download 命令
    parser_download = subparsers.add_parser("download", help="素材下载")
    parser_download.add_argument("--excel", "-e", help="Excel/CSV文件路径")
    parser_download.add_argument("--local-dir", "-l", help="本地素材目录（只扫描）")
    parser_download.add_argument("--output-dir", "-o", default=None, help="输出目录")
    parser_download.add_argument("--workers", "-w", type=int, default=None, help="并发下载数")
    parser_download.add_argument("--sample", "-s", type=int, default=None, help="采样数量")
    parser_download.set_defaults(func=cmd_download)

    # label 命令
    parser_label = subparsers.add_parser("label", help="视觉AI打标")
    parser_label.add_argument("--materials-dir", "-m", default="downloaded_materials", help="素材目录")

    # 动态获取所有可用的Provider选项（从MaterialLabeler获取）
    from ecommerce_processor.labeler import MaterialLabeler
    available_providers = list(MaterialLabeler.PROVIDER_CONFIGS.keys())
    
    parser_label.add_argument("--provider", "-p", 
                              default="custom_minmax",
                              choices=available_providers,
                              help=f"Provider选择 (可选: {', '.join(available_providers)})")
    parser_label.add_argument("--model", "-M", default=None,
                              help="视觉模型名称（默认使用配置中的 vlm_model，如 minicpm-v-4.6）")
    parser_label.add_argument("--batch-size", "-b", type=int, default=None, help="每批数量")
    parser_label.add_argument("--batch-delay", "-d", type=float, default=None, help="批次延迟(秒)")
    parser_label.add_argument("--sample", "-s", type=int, default=None, help="采样数量")
    parser_label.add_argument("--force", "-f", action="store_true",
                              help="忽略已有缓存，强制重新打标（用于重试此前失败项）")
    parser_label.set_defaults(func=lambda args: asyncio.run(cmd_label(args)))

    # archive 命令
    parser_archive = subparsers.add_parser("archive", help="归档报告生成")
    parser_archive.add_argument("--materials-dir", "-m", default=None, help="素材目录")

    # 归档命令复用labeler的Provider配置（MaterialArchiver内部也是使用MaterialLabeler的配置）
    archive_providers = available_providers
    
    parser_archive.add_argument("--provider", "-p",
                                default="custom_minmax",
                                choices=archive_providers,
                                help=f"Provider选择 (可选: {', '.join(archive_providers)})")
    parser_archive.add_argument("--output-dir", "-o", default=None, help="输出目录")
    parser_archive.add_argument("--media-type", "-t", choices=["image", "video", "all"], default="all")
    parser_archive.add_argument("--sample", "-s", type=int, default=None, help="采样数量")
    parser_archive.set_defaults(func=lambda args: asyncio.run(cmd_archive(args)))

    # export 命令
    parser_export = subparsers.add_parser("export", help="导出Excel")
    parser_export.add_argument("--cache-file", "-c", default=None, help="缓存文件路径")
    parser_export.add_argument("--output-dir", "-o", default=None, help="输出目录")
    parser_export.add_argument("--filename", "-f", default=None, help="输出文件名")
    parser_export.set_defaults(func=cmd_export)

    # 解析参数
    args = parser.parse_args()

    # 配置日志
    setup_logging(settings.log_level)

    # 如果没有提供命令，显示帮助
    if not args.command:
        parser.print_help()
        return 1

    # 执行命令
    try:
        result = args.func(args)
        return result if isinstance(result, int) else 0
    except KeyboardInterrupt:
        print("\n\n  用户中断操作")
        return 130
    except Exception as e:
        logger.exception(f" 执行失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())