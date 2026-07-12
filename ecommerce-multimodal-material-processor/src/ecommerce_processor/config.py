"""配置管理模块 - 详细文档: config.py.example"""

from pathlib import Path
from typing import List, Optional

try:
    from pydantic_settings import BaseSettings
except ImportError:
    class BaseSettings:
        __annotations__ = {}
        def __init__(self, **data): pass

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

    # 二、VLM配置
    vlm_model: str = "minicpm-v-4.6"
    vlm_provider: str = "custom_minmax"
    vlm_temperature: float = 0.3
    vlm_max_tokens: int = 4000
    vlm_timeout_ms: int = 300000

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

    # 九、LLM参数
    llm_timeout_ms: int = 180000
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2600
    llm_concurrency: int = 1
    enable_mock_llm: bool = False

    # 十、分析模板
    analysis_template: str = "full_dimension"
    video_direct_mode: bool = True
    template_path_full_dimension: str = "docs/ANALYSIS_TEMPLATE_FULL_DIMENSION.md"
    template_path_storyboard: str = "docs/STORYBOARD_TEMPLATE_STANDARD.md"
    enable_fallback: bool = True

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

    def __init__(self, **data):
        try:
            super().__init__(**data)
        except Exception:
            from os import environ
            for key in self.__class__.__annotations__:
                val = environ.get(key.upper())
                if val is not None:
                    setattr(self, key, val)
                elif key in data:
                    setattr(self, key, data[key])
                else:
                    setattr(self, key, getattr(self.__class__, key, None))

    def validate_provider_config(self) -> List[str]:
        providers = []
        for name in ['minmax', 'kimi', 'minicpm', 'paddle', 'custom_minmax', 'yescode', 'gemini']:
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
    
    @property
    def vlm_api_key(self) -> Optional[str]:
        return getattr(self, f'{self.vlm_provider}_api_key', None)
    
    @property
    def vlm_base_url(self) -> Optional[str]:
        if self.vlm_provider == 'custom_minmax':
            return self.custom_minmax_url
        elif self.vlm_provider == 'minicpm':
            return self.minicpm_base_url
        return None

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