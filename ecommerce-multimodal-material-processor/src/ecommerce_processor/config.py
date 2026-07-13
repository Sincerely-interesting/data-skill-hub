"""配置管理模块 - 详细文档: config.py.example"""

from pathlib import Path
from typing import List, Optional

try:
    from pydantic_settings import BaseSettings
    from pydantic import model_validator
except ImportError:
    class BaseSettings:
        __annotations__ = {}
        def __init__(self, **data): pass
    def model_validator(*args, **kwargs):
        def decorator(cls): return cls
        return decorator

class Settings(BaseSettings):
    """系统配置"""
    
    # 一、AI模型提供商
    model_provider: str = "custom_minmax"
    llm_model: str = "gemma-4-12b-it"
    minmax_api_key: Optional[str] = None
    kimi_api_key: Optional[str] = None
    minicpm_api_key: Optional[str] = None
    paddle_api_key: Optional[str] = None
    custom_minmax_api_key: Optional[str] = None
    yescode_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    minicpm_base_url: str = "https://api.minicpm.com/v1"
    minicpm_instruct_model_id: str = "minicpm-v-4"
    custom_minmax_url: Optional[str] = None

    # 二、VLM 配置（视觉模型，用于打标 / 归档看图）
    # 与下方"九、LLM 参数"完全独立——即使两者地址/参数相同，也必须分开填写。
    vlm_model: str = "gemma-4-12b-it"
    vlm_provider: str = "custom_minmax"
    vlm_base_url: Optional[str] = None
    vlm_api_key: Optional[str] = None
    vlm_temperature: float = 0.3
    vlm_max_tokens: int = 4000
    vlm_timeout_ms: int = 300000
    # 视频直传的素材可达基础 URL（可选）：
    # 当素材是本地文件、且 provider 为远程服务时，video_url 必须是
    # provider 可直接下载的 *直接 URL*（绝不能是 data:video/...;base64 内嵌）。
    # 填素材的托管基础地址后自动拼成 {media_base_url}/{material_id}/{filename}；
    # 留空：本地文件回退为 file:// 绝对路径（仅 provider 与代码同机时有效）。
    media_base_url: Optional[str] = None

    # 三、图片处理
    image_max_size: int = 768
    image_quality: int = 75

    # 四、批量处理
    default_batch_size: int = 5
    default_batch_delay: float = 20.0
    default_workers: int = 5

    # 五、重试机制
    max_retries: int = 5
    retry_base_delay: int = 10
    quota_wait_hours: int = 5

    # 六、输出目录
    archive_output_dir: Path = Path("material_archives")
    excel_export_dir: Path = Path("excel_exports")
    cache_dir: Path = Path("./cache")

    # 七、搜索服务
    search_service_host: str = "127.0.0.1"
    search_service_port: int = 8000

    # 八、质量控制
    quality_other_label_threshold: float = 0.20
    quality_min_success_rate: float = 0.95

    # 九、LLM 参数（文本模型，用于报告 / 分析等文本生成，与 VLM 完全独立）
    # 即使 VLM 与 LLM 指向同一地址、参数相同，也必须各自配置，互不影响。
    llm_provider: str = "custom_minmax"
    llm_timeout_ms: int = 180000
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2600
    llm_concurrency: int = 1
    enable_mock_llm: bool = False
    # 独立文本 LLM 端点（.env: LLM_BASE_URL / LLM_API_KEY），
    # 不再依赖 VLM 的 custom_minmax_url，实现真正分离。
    llm_base_url: Optional[str] = None
    llm_api_key: Optional[str] = None

    # 十、分析模板
    analysis_template: str = "full_dimension"
    video_direct_mode: bool = True
    template_path_full_dimension: str = "docs/ANALYSIS_TEMPLATE_FULL_DIMENSION.md"
    template_path_storyboard: str = "docs/STORYBOARD_TEMPLATE_STANDARD.md"

    # 十一、处理限制
    max_images: int = 10
    max_videos: int = 3
    max_api_videos: int = 3
    max_tags: int = 8

    # 十二、文件验证
    max_image_size_mb: float = 50.0
    max_video_size_mb: float = 500.0
    allowed_image_types: str = ".jpg,.jpeg,.png,.webp,.gif"
    allowed_video_types: str = ".mp4,.mov,.avi,.mkv"

    # 十三、打标阈值
    threshold_strong: float = 80.0
    threshold_medium: float = 60.0
    threshold_weak: float = 40.0

    # 十四、API超时
    api_timeout_seconds: float = 30.0
    api_connect_timeout: float = 5.0

    # 十五、日志
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    def validate_provider_config(self) -> List[str]:
        providers = []
        # 既识别 legacy 的 {provider}_api_key，也识别双独立配置下的 vlm_api_key / llm_api_key，
        # 这样精简后的 .env（只配 VLM_*/LLM_*）也能通过 doctor 校验。
        for name in ['minmax', 'kimi', 'minicpm', 'paddle', 'custom_minmax', 'yescode', 'gemini', 'vlm', 'llm']:
            if getattr(self, f'{name}_api_key'):
                providers.append(name)
        if not providers:
            raise ValueError("未检测到任何Provider的API Key！")
        return providers

    @property
    def available_providers(self) -> dict:
        return {name: getattr(self, f'{name}_api_key') 
                for name in ['minmax', 'kimi', 'minicpm', 'paddle', 
                             'custom_minmax', 'yescode', 'gemini']}
    
    @model_validator(mode="after")
    def _backfill_endpoints(self) -> "Settings":
        # VLM 端点：优先用独立的 vlm_base_url / vlm_api_key，
        # 否则回退到 legacy 的 custom_minmax_url / custom_minmax_api_key。
        if not self.vlm_base_url and self.custom_minmax_url:
            self.vlm_base_url = self.custom_minmax_url
        if not self.vlm_api_key and self.custom_minmax_api_key:
            self.vlm_api_key = self.custom_minmax_api_key
        # LLM 端点：优先用独立的 llm_base_url / llm_api_key，
        # 否则回退到 custom_minmax_*（方便单地址部署，但仍是独立字段）。
        if not self.llm_base_url and self.custom_minmax_url:
            self.llm_base_url = self.custom_minmax_url
        if not self.llm_api_key and self.custom_minmax_api_key:
            self.llm_api_key = self.custom_minmax_api_key
        return self

def resolve_video_url(video_path, material_id: str) -> str:
    """把视频解析为 provider 可访问的 *直接 URL*（绝不转 base64）。

    对接标准（OpenAI-compatible / NVIDIA NIM / crossmodel）：
        video_url.url 必须是 provider 可直接下载的 URL，
        不能是 data:video/...;base64,... 形式的 base64 内嵌。

    解析优先级：
        1) 已是 http(s) URL → 直接用
        2) 配置了 MEDIA_BASE_URL → {base}/{material_id}/{filename}
        3) 兜底 → file:// 绝对路径（仅当 provider 与代码同机时有效；
           远程 provider 请先托管素材，或起本地静态服务后填 MEDIA_BASE_URL）
    """
    s = str(video_path)
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if settings.media_base_url:
        base = settings.media_base_url.rstrip("/")
        return f"{base}/{material_id}/{Path(video_path).name}"
    return Path(video_path).resolve().as_uri()


_settings_instance = None

def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance

class _SettingsProxy:
    def __getattr__(self, name): 
        return getattr(get_settings(), name)
    def __setattr__(self, name, value): 
        setattr(get_settings(), name, value)

settings = _SettingsProxy()