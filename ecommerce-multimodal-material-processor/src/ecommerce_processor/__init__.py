"""
电商多模态素材处理引擎 (E-commerce Multimodal Material Processor)

独立可运行的企业级素材处理流水线：
- 素材获取（本地目录/Excel下载）
- 视觉AI打标（8种Provider，含MCP协议）
- 分镜头归档报告生成
- 视频抽帧与多模态处理
- 缓存断点续传
- Excel导出
"""

__version__ = "1.1.0"
__author__ = "E-commerce Material Processing Team"

# 核心模块
from .config import settings
from .deps_checker import check_dependencies
from .labeler import MaterialLabeler, QuotaExhaustedError
from .archiver import MaterialArchiver
from .downloader import MaterialDownloader
from .exporter import CacheExporter

# 视频和MCP扩展
from .video_utils import (
    VideoProcessor,
    extract_video_frames,
    pick_evenly,
    get_video_info,
    check_ffmpeg_available,
)
from .mcp_client import (
    MiniMaxMCPClient,
    VideoAudioExtractor,
    WhisperTranscriber,
    MultimodalMaterialProcessor,
)

# API服务（开发中，需要fastapi等依赖）
try:
    from .api_service import get_app
    api_app = get_app()  # 安全获取，依赖缺失时返回None
except Exception:
    api_app = None

__all__ = [
    # 版本信息
    "__version__",
    
    # 核心配置和工具
    "settings",
    "check_dependencies",
    
    # 核心业务模块
    "MaterialLabeler",
    "QuotaExhaustedError",
    "MaterialArchiver",
    "MaterialDownloader",
    "CacheExporter",
    
    # 视频处理
    "VideoProcessor",
    "extract_video_frames",
    "pick_evenly",
    "get_video_info",
    "check_ffmpeg_available",
    
    # MCP协议支持
    "MiniMaxMCPClient",
    "VideoAudioExtractor",
    "WhisperTranscriber",
    "MultimodalMaterialProcessor",
    
    # API服务
    "api_app",
]