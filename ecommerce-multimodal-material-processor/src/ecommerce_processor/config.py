"""
配置管理模块 - 使用 Pydantic Settings 进行环境变量管理

依赖要求：
- pydantic>=2.0.0
- pydantic-settings>=2.0.0

安装命令：pip install pydantic pydantic-settings
"""
from pathlib import Path
from typing import Optional, List, Any


try:
    from pydantic_settings import BaseSettings
    from pydantic import Field
    _PYDANTIC_AVAILABLE = True
except ImportError:
    _PYDANTIC_AVAILABLE = False
    BaseSettings = object  # 占位符
    Field = lambda default=None, **kwargs: default  # 简化版Field


class Settings(BaseSettings):
    """
    全局配置类
    
    使用Pydantic Settings进行环境变量管理。
    如果pydantic未安装，将使用简化版实现。
    """

    # ---- API Keys (至少配置一个) ----
    minmax_api_key: Optional[str] = None
    kimi_api_key: Optional[str] = None
    minicpm_api_key: Optional[str] = None
    paddle_api_key: Optional[str] = None
    custom_minmax_api_key: Optional[str] = None
    yescode_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

    # ---- Provider URLs ----
    minicpm_base_url: str = "https://api.minicpm.com/v1"
    minicpm_instruct_model_id: str = "minicpm-v-4"
    custom_minmax_url: Optional[str] = None

    # ---- Processing Parameters ----
    image_max_size: int = 768
    image_quality: int = 75

    default_batch_size: int = 5
    default_batch_delay: float = 20.0
    default_workers: int = 5

    # ---- Retry Settings ----
    max_retries: int = 5
    retry_base_delay: int = 10
    quota_wait_hours: int = 5

    # ---- Output Directories ----
    archive_output_dir: Path = Path("material_archives")
    excel_export_dir: Path = Path("excel_exports")
    cache_dir: Path = Path("./cache")

    # ---- Search Service ----
    search_service_host: str = "127.0.0.1"
    search_service_port: int = 8000

    # ---- Quality Thresholds ----
    quality_other_label_threshold: float = 0.20
    quality_min_success_rate: float = 0.95


    # ---- LLM模型参数 (针对自建服务器优化) ----
    llm_model: str = "gemma-4-12b-it"  # 默认模型名称
    llm_timeout_ms: int = 180000  # 超时时间(毫秒), 180秒适合本地大模型
    llm_temperature: float = 0.7  # 温度参数(0.0-2.0)
    llm_max_tokens: int = 2600  # 最大生成Token数
    llm_concurrency: int = 1  # 并发请求数(建议1避免过载)
    enable_mock_llm: bool = False  # 是否启用模拟模式(测试用)
    enable_fallback: bool = True  # 是否启用故障回退    # ---- Logging ----
    log_level: str = "INFO"

    if _PYDANTIC_AVAILABLE:
        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            case_sensitive = False
    
    def __init__(self, **data):
        if _PYDANTIC_AVAILABLE:
            super().__init__(**data)
        else:
            from os import environ
            for key, value in self.__class__.__annotations__.items():
                env_value = environ.get(key.upper())
                if env_value is not None:
                    setattr(self, key, env_value)
                elif key in data:
                    setattr(self, key, data[key])
                else:
                    setattr(self, key, getattr(self.__class__, key, None))

    def validate_provider_config(self) -> List[str]:
        """
        验证至少配置了一个Provider的API Key
        
        Returns:
            List[str]: 已配置的Provider列表
        """
        providers = []
        if self.minmax_api_key:
            providers.append("minmax")
        if self.kimi_api_key:
            providers.append("kimi")
        if self.minicpm_api_key:
            providers.append("minicpm")
        if self.paddle_api_key:
            providers.append("paddle")
        if self.custom_minmax_api_key:
            providers.append("custom_minmax")
        if self.yescode_api_key:
            providers.append("yescode")
        if self.gemini_api_key:
            providers.append("gemini")

        if not providers:
            raise ValueError(
                "未检测到任何Provider的API Key！请至少在 .env 中配置一个Provider：\n"
                "- MINMAX_API_KEY\n"
                "- KIMI_API_KEY\n"
                "- MINICPM_API_KEY\n"
                "- PADDLE_API_KEY\n"
                "- CUSTOM_MINMAX_API_KEY\n"
                "- YESCODE_API_KEY\n"
                "- GEMINI_API_KEY"
            )

        return providers

    @property
    def available_providers(self) -> dict:
        """返回已配置的Provider及其API Key"""
        return {
            "minmax": self.minmax_api_key,
            "kimi": self.kimi_api_key,
            "minicpm": self.minicpm_api_key,
            "paddle": self.paddle_api_key,
            "custom_minmax": self.custom_minmax_api_key,
            "yescode": self.yescode_api_key,
            "gemini": self.gemini_api_key,
        }


# 全局单例（延迟初始化，避免导入时崩溃）
_settings_instance = None

def get_settings() -> Settings:
    """
    获取全局配置实例（线程安全）
    
    Returns:
        Settings: 配置实例
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


# 兼容性：直接访问 settings 属性
class _SettingsProxy:
    """Settings代理类，支持属性访问"""
    
    def __getattr__(self, name):
        return getattr(get_settings(), name)
    
    def __setattr__(self, name, value):
        setattr(get_settings(), name, value)


settings = _SettingsProxy()
