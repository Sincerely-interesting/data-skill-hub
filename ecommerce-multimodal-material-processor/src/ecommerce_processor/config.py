"""配置管理模块 - 详细文档: config.py.example"""

from pathlib import Path
from typing import List, Optional
import base64
import logging

logger = logging.getLogger(__name__)

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
    # 当素材是本地文件、且 provider 为远程服务时，video_url 通常是
    # provider 可直接下载的 *直接 URL*；但 MiniCPM-vLLM 系（面壁托管）例外——
    # 它要求整段视频以 data:video/...;base64 内嵌进请求体，由
    # config.build_video_part 的 minicpm_base64 形态在本地读字节生成（不抽帧）。
    # 填素材的托管基础地址后自动拼成 {media_base_url}/{material_id}/{filename}；
    # 留空：本地文件回退为 file:// 绝对路径（minicpm_base64 会读该文件字节 base64）。
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
    retry_base_delay: int = 3
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

    # 十、分析模板（归档提示词参照的模板，由配置文件控制读取哪一个）
    #   archive_template 取值：
    #     "storyboard"      → 视频分镜头脚本标准格式模板（docs/STORYBOARD_TEMPLATE_STANDARD.md）
    #                         用于"把视频还原成视频原文（分镜头脚本）"，按模板结构反向拆解。
    #     "full_dimension"  → 商品素材全维内容理解分析模板（docs/ANALYSIS_TEMPLATE_FULL_DIMENSION.md）
    #                         用于多维度结构化理解分析。
    #   两种模板均为本地 ./docs/* 文件，通过 .env 的 ARCHIVE_TEMPLATE 切换读取。
    archive_template: str = "storyboard"
    video_direct_mode: bool = True
    # 视频部件字段形态：不同 provider 的"视频引用"字段名/传递方式不同，必须匹配否则被拒。
    #   "openai_compatible" → {"type":"video_url","video_url":{"url":u}}   （URL 引用，端点需能 fetch）
    #   "gemma_hf"         → {"type":"video","video":u}                （Gemma HF Transformers，用户贴的官方文档）
    #   "gemini"            → {"file_data":{"mime_type":"video/mp4","file_uri":u}} （Gemini generateContent，u 须为 GCS/上传 URI）
    #   "minicpm_base64"    → {"type":"video_url","video_url":{"url":"data:video/mp4;base64,..."}} （面壁/MiniCPM-vLLM 官方 cookbook，整段视频 base64 内联，不抽帧）
    # 与 resolve_video_url（本地回退 file:// 后由本形态读字节 base64）协同生效。
    video_payload_format: str = "openai_compatible"
    template_path_full_dimension: str = "docs/ANALYSIS_TEMPLATE_FULL_DIMENSION.md"
    template_path_storyboard: str = "docs/STORYBOARD_TEMPLATE_STANDARD.md"

    # 十一、标注标准/示例注入（让 AI 主动读取 references/examples，提升分类一致性）
    #   grounding_enabled: 是否把"标注标准规范"注入分类 prompt（默认开）。
    #   label_criteria_path: 标注标准文档（references/labeling-criteria.md），比 prompt 内的
    #                        8 类简化说明更细，作为模型判定的"标尺"，直接对齐分类精度/漂移问题。
    #   fewshot_examples_enabled: 是否注入示例文档（默认关；demo-conversation.md 是对话示例、
    #                        非分类 few-shot，批处理注入易引入噪声，故默认关，需要时再开）。
    #   examples_path: 示例文档路径。
    #   路径均相对仓库根解析（与 resolve_template_path 同构）。
    grounding_enabled: bool = True
    #   label_prompt_path: 主分类 prompt（权威，从外部文件注入，拒绝硬编码）。
    label_prompt_path: str = "prompts/label_prompt.txt"
    label_criteria_path: str = "references/labeling-criteria.md"
    fewshot_examples_enabled: bool = False
    examples_path: str = "examples/demo-conversation.md"

    # 十一·五、文档定位基准（模板 + 标注标准等所有相对文档的基准目录）
    #   doc_base_enabled: 开关（默认开）。开=按 doc_base_dir 定位文档；关=按运行目录(cwd)定位。
    #   doc_base_dir:     基准目录，相对 config.py 所在目录（Linux 相对路径，用 "/" 分隔）。
    #     本文件在 src/ecommerce_processor/，代码用文档在同级 docs/、references/，故为 "."。
    #   最终路径 = config.py目录 / doc_base_dir / (template_path_* 或 label_criteria_path 等)
    doc_base_enabled: bool = True
    doc_base_dir: str = "."

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

    # 十二·五、请求体上限与自适应压缩（修复打标 413 request_too_large）
    #   minicpm_base64 形态会把整段视频 base64 内联，叠加多张图片后极易超出
    #   端点请求体上限（如 ModelBest ~8-10MB），返回 HTTP 413。
    #   打开 auto_compress_oversize 后：
    #     - 视频：build_video_part 生成 base64 前，若超预算用 ffmpeg 整段重编码到达标（不抽帧）
    #     - 图片：labeler 发送前用 Pillow 降分辨率重压 JPEG
    #   413 在 labeler 中被视为"不可重试"，直接失败不再空烧 5 次指数退避。
    max_request_mb: float = 8.0            # 单次请求体软上限（MB），留余量应对端点硬限
    auto_compress_oversize: bool = True    # 超限时是否自动压缩视频/图片
    ffmpeg_path: Optional[str] = None      # ffmpeg 可执行路径（留空则用 PATH 中的 ffmpeg）

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


_VIDEO_MIME = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".m4v": "video/mp4",
}


def _build_minicpm_base64_part(video_url: str) -> dict:
    """MiniCPM-vLLM 官方 cookbook 形态：整段视频 base64 内联（不抽帧）。

    面壁/MiniCPM 托管端点按 vLLM 约定，视频须作为 data-URI base64 内嵌进
    请求体，而非远程 URL 引用。此处直接读本地文件字节做 base64
    （**绝不做抽帧/逐帧**，是整段传），以匹配端点要求。
    远程 http(s) URL 场景无法在本地 base64，则回退为 openai_compatible 形态
    （端点可能不支持，仅作尽力而为）。
    """
    s = str(video_url)
    path = None
    if s.startswith("file://"):
        path = s[len("file://"):]  # file:///C:/x -> /C:/x
        if path.startswith("/") and len(path) > 2 and path[2] == ":":
            path = path[1:]  # /C:/x -> C:/x
    elif s.startswith("http://") or s.startswith("https://"):
        logger.warning("minicpm_base64 需要本地文件字节，远程 URL 无法本地 base64，回退为 URL 引用: %s", s)
        return {"type": "video_url", "video_url": {"url": s}}
    else:
        path = s  # 直接是本地路径
    p = Path(path)
    if not p.exists():
        logger.warning("minicpm_base64 找不到本地文件，回退为 URL 引用: %s", video_url)
        return {"type": "video_url", "video_url": {"url": s}}

    # 自适应压缩：base64 内联会使体积膨胀 ~33%，叠加图片后极易触发端点 413。
    # 若开启 auto_compress_oversize，则在 base64 前把视频整段重编码到预算内（不抽帧）。
    src = p
    if getattr(settings, "auto_compress_oversize", True) and getattr(settings, "max_request_mb", 0):
        try:
            from .video_utils import compress_video_to_fit
            # 预算：请求体软上限 × 0.9（给图片/文本留余量），再折算成原始字节（÷ base64 膨胀 ~1.33）
            max_bytes = int(settings.max_request_mb * 1024 * 1024 * 0.9 / 1.34)
            src = compress_video_to_fit(
                p, max_bytes,
                ffmpeg_bin=getattr(settings, "ffmpeg_path", None) or "ffmpeg",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("视频自适应压缩失败，改用原始文件: %s", e)
            src = p

    suffix = src.suffix.lower()
    mime = _VIDEO_MIME.get(suffix, "video/mp4")
    data = base64.standard_b64encode(src.read_bytes()).decode("utf-8")
    return {"type": "video_url", "video_url": {"url": f"data:{mime};base64,{data}"}}


def build_video_part(video_url: str) -> dict:
    """按当前 provider 形态拼装“视频引用”部件。

    对接标准差异（同一段视频在不同 provider 的字段名/传递方式不同）：
        - openai_compatible: {"type":"video_url","video_url":{"url": video_url}}
                            （URL 引用，端点需能 fetch 该 URL）
        - gemma_hf:         {"type":"video","video": video_url}
        - gemini:            {"file_data":{"mime_type":"video/mp4","file_uri": video_url}}
        - minicpm_base64:   {"type":"video_url","video_url":{"url":"data:video/mp4;base64,..."}}
                            （面壁/MiniCPM-vLLM 官方 cookbook：整段视频 base64 内联，
                             由本函数读本地文件字节生成，**不抽帧、不逐帧**）
    """
    fmt = (getattr(settings, "video_payload_format", "openai_compatible") or "openai_compatible").strip().lower()
    if fmt == "gemma_hf":
        return {"type": "video", "video": video_url}
    if fmt == "gemini":
        return {"file_data": {"mime_type": "video/mp4", "file_uri": video_url}}
    if fmt == "minicpm_base64":
        return _build_minicpm_base64_part(video_url)
    # 默认 / openai_compatible
    return {"type": "video_url", "video_url": {"url": video_url}}


_TEMPLATE_MAP = {
    "storyboard": "template_path_storyboard",
    "full_dimension": "template_path_full_dimension",
}

def _resolve_repo_file(rel_path: str) -> Path:
    """把文档相对路径解析为绝对路径：基准目录 + rel_path。

    基准目录由两个配置项控制（见 Settings.doc_base_enabled / doc_base_dir）：
      - doc_base_enabled 开（默认）：基准 = config.py目录 / doc_base_dir
      - doc_base_enabled 关：基准 = 运行目录 (cwd)
    不再逐级向上查找。绝对 rel_path 直接返回。
    """
    rel = Path(rel_path)
    if rel.is_absolute():
        return rel.resolve()
    if getattr(settings, "doc_base_enabled", True):
        base = Path(__file__).resolve().parent / getattr(settings, "doc_base_dir", ".")
    else:
        base = Path.cwd()
    return (base / rel).resolve()


def resolve_template_path(name: str = None) -> Path:
    """根据配置（或显式名称）返回归档模板文件的绝对路径。

    模板均为本地 ./docs/* 文件，路径向上逐级查找（见 _resolve_repo_file）。
    """
    name = name or settings.archive_template
    key = _TEMPLATE_MAP.get(name)
    if not key:
        raise ValueError(
            f"未知的归档模板: {name!r}（可选: storyboard / full_dimension）"
        )
    return _resolve_repo_file(getattr(settings, key))


def resolve_grounding_path(rel_path: str = None) -> Path:
    """标注标准/示例文档路径解析（见 _resolve_repo_file）。

    用于把 references/labeling-criteria.md、examples/demo-conversation.md 等
    文档解析为绝对路径，供 labeler 注入分类 prompt。
    """
    return _resolve_repo_file(rel_path or settings.label_criteria_path)


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