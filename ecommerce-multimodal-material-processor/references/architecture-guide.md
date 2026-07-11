# 架构设计指南 (Architecture Guide)

> 本文档详细描述电商多模态素材处理系统的技术架构、模块设计和实现原理。

## 系统架构概览

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    用户接口层 (CLI)                          │
│  run_pipeline.py (统一入口: doctor/download/label/archive/  │
│ export)                                                    │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                   核心处理层                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │Downloader│ │ Labeler  │ │Archiver  │ │   Exporter    │   │
│  │(并发下载)│ │(AI标注)  │ │(报告生成)│ │ (多格式导出)  │   │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘   │
│       │            │            │               │           │
│  ┌────▼────────────▼────────────▼───────────────▼───────┐   │
│  │              共享基础设施                              │   │
│  │  config.py | video_utils.py | deps_checker.py        │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                  数据持久化层                               │
│  ┌────────────┐  ┌─────────────┐  ┌────────────────────┐   │
│  │ JSON Cache │  │ Markdown    │  │ Excel/CSV          │   │
│  │ (.json)    │  │ Archives    │  │ Exports            │   │
│  └────────────┘  └─────────────┘  └────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                外部服务集成层                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ AI Providers (8种):                                  │    │
│  │ Gemini | MiniMax | Kimi | MINICPM | Paddle | Custom │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │  ffmpeg  │ │ Whisper  │ │  LanceDB │ │ SMB Network  │   │
│  │(视频处理)│ │(音频转写)│ │(向量检索)│ │ (文件同步)   │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 模块设计详解

### 1. 配置管理模块 (`config.py`)

**设计模式**: Pydantic Settings + 环境变量注入

**核心类**: `Settings(BaseSettings)`

```python
class Settings(BaseSettings):
    # API Keys (至少配置一个)
    gemini_api_key: Optional[str] = None
    minmax_api_key: Optional[str] = None
    kimi_api_key: Optional[str] = None
    # ... 其他Provider
    
    # 处理参数
    image_max_size: int = 768          # 图片最大边长
    image_quality: int = 75            # JPEG质量
    default_batch_size: int = 5        # 批次大小
    default_batch_delay: float = 20.0  # 批次延迟(秒)
    
    # 重试策略
    max_retries: int = 5               # 最大重试次数
    retry_base_delay: int = 10         # 基础延迟(秒)
    quota_wait_hours: int = 5          # 配额等待时间
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
```

**特性**:
- ✅ 类型安全的配置管理
- ✅ 自动从.env文件加载
- ✅ 支持环境变量覆盖
- ✅ 运行时验证配置合法性

**使用示例**:
```python
from ecommerce_processor.config import settings

# 访问配置
api_key = settings.gemini_api_key
batch_size = settings.default_batch_size

# 验证Provider配置
configured_providers = settings.validate_provider_config()
```

---

### 2. 素材下载模块 (`downloader.py`)

**设计模式**: 生产者-消费者模型 + ThreadPoolExecutor

**核心功能**:
1. **Excel/CSV解析**
   - 自动识别URL列名(material_id, url, image_url, video_url)
   - 支持.xlsx/.xls/.csv格式
   - 使用pandas进行高效解析

2. **本地目录扫描**
   - 递归遍历子文件夹
   - 按扩展名识别素材类型:
     - 图片: `.jpg`, `.jpeg`, `.png`, `.webp`
     - 视频: `.mp4`, `.mov`, `.avi`, `.mkv`

3. **并发下载引擎**
   ```python
   class MaterialDownloader:
       def __init__(self, excel_path, output_dir, workers=5):
           self.executor = ThreadPoolExecutor(max_workers=workers)
           self.session = httpx.Client(timeout=30.0)
       
       def process_all(self):
           futures = []
           for material in materials:
               future = self.executor.submit(self.download_single, material)
               futures.append(future)
           
           # 使用tqdm显示进度
           results = tqdm(
               as_completed(futures),
               total=len(futures),
               desc="Downloading"
           )
           
           return self.aggregate_results(results)
   ```

**容错机制**:
- 超时控制: 30秒/文件
- 重试机制: 3次重试 + 指数退避
- 断点续传: 检查已存在文件,跳过重复下载
- 错误记录: 失败任务写入failed列表,不阻塞整体流程

**输出结构**:
```
{output_dir}/
├── {material_id_1}/
│   ├── image_001.jpg
│   ├── image_002.jpg
│   └── content.mp4
├── {material_id_2}/
│   └── image_001.jpg
└── ...
```

---

### 3. AI标注引擎 (`labeler.py`)

**设计模式**: 策略模式 + Provider抽象层

**核心类**: `MaterialLabeler`

#### Provider配置体系

```python
PROVIDER_CONFIGS = {
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "base_url": "auto",  # 通过YesCode代理或直连
        "model": "gemini-2.5-flash",
    },
    "minmax": {
        "api_key_env": "MINMAX_API_KEY",
        "base_url": "https://api.minimax.chat/v1",
        "model": "MiniMax-M2.7",
    },
    "kimi": {
        "api_key_env": "KIMI_API_KEY",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k2.6",
    },
    # ... 其他Provider
}
```

#### 统一OpenAI-Compatible接口

所有Provider都通过统一的HTTP客户端调用:

```python
class MaterialLabeler:
    async def call_provider(self, provider, prompt, images=None):
        config = self.PROVIDER_CONFIGS[provider]
        
        # 构建请求头
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        # 构建请求体(OpenAI格式)
        payload = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.3,  # 低温度保证确定性
            "max_tokens": 1024,
        }
        
        # 发送请求并处理响应
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers)
            result = self.parse_response(response.json())
            
        return result
```

#### 图片处理流程

```python
async def label_image(self, image_path):
    # 1. 读取图片
    image_data = self.read_image(image_path)
    
    # 2. 预处理(缩放、压缩)
    processed = self.preprocess_image(image_data)
    
    # 3. Base64编码
    base64_image = base64.b64encode(processed).decode("utf-8")
    
    # 4. 构建多模态消息
    content = [
        {"type": "text", "text": LABELING_PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
    ]
    
    # 5. 调用AI Provider
    result = await self.call_provider(provider, content)
    
    # 6. 解析标签
    label = self.extract_label(result)
    
    return {
        "material_id": material_id,
        "file_path": str(image_path),
        "label": label["primary"],
        "confidence": label["confidence"],
        "provider": provider,
        "timestamp": datetime.now().isoformat(),
    }
```

#### 视频处理流程

```python
async def label_video(self, video_path):
    # 1. 使用ffmpeg抽帧
    frames = extract_frames(
        video_path,
        fps=settings.video_fps,      # 默认1fps
        max_frames=settings.max_frames,  # 默认60帧
    )
    
    # 2. 可选: 提取音频并转写
    if settings.extract_audio:
        audio = extract_audio(video_path)
        transcript = whisper.transcribe(audio)
        context = f"\n音频转写: {transcript}"
    else:
        context = ""
    
    # 3. 将帧序列发送给模型
    frame_contents = []
    for frame in frames:
        base64_frame = base64.b64encode(frame).decode("utf-8")
        frame_contents.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_frame}"}
        })
    
    content = [
        {"type": "text", "text": LABELING_PROMPT + context},
        *frame_contents
    ]
    
    # 4. 调用AI Provider
    result = await self.call_provider(provider, content)
    
    return self.format_result(result)
```

#### 容错与重试机制

```python
async def call_with_retry(self, provider, content, max_retries=None):
    max_retries = max_retries or settings.max_retries
    
    for attempt in range(max_retries):
        try:
            result = await self.call_provider(provider, content)
            return result
            
        except QuotaExhaustedError:
            # 配额耗尽,长时间等待
            wait_hours = settings.quota_wait_hours
            logger.warning(f"Quota exhausted, waiting {wait_hours}h...")
            await asyncio.sleep(wait_hours * 3600)
            
        except RateLimitError:
            # 触发限流,指数退避
            delay = settings.retry_base_delay * (2 ** attempt)
            logger.warning(f"Rate limited, retrying in {delay}s...")
            await asyncio.sleep(delay)
            
        except Exception as e:
            logger.error(f"Attempt {attempt+1} failed: {e}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(settings.retry_base_delay * (2 ** attempt))
    
    raise MaxRetriesExceededError(f"Failed after {max_retries} retries")
```

#### 缓存机制

```python
class CacheManager:
    def __init__(self, cache_file="labeling_cache.json"):
        self.cache_file = Path(cache_file)
        self.cache = self.load_cache()
    
    def load_cache(self):
        if self.cache_file.exists():
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def is_cached(self, material_id):
        return material_id in self.cache
    
    def get_cached_result(self, material_id):
        return self.cache[material_id]
    
    def save_result(self, material_id, result):
        self.cache[material_id] = result
        self.persist()
    
    def persist(self):
        # 原子写入: 先写临时文件,再rename
        temp_file = self.cache_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
        temp_file.rename(self.cache_file)
```

---

### 4. 归档报告生成模块 (`archiver.py`)

**功能**: 为每个素材生成详细的Markdown报告

**报告模板**:

```python
ARCHIVE_TEMPLATE = """# Material Report: {material_id}

## 基本信息
- **文件路径**: {file_path}
- **文件大小**: {file_size}
- **文件类型**: {file_type}
{resolution_section}
{duration_section}

## 标注结果
- **主标签**: {primary_label} (置信度: {confidence:.2f})
- **备选标签**: {alternative_labels}
- **标注Provider**: {provider}
- **使用的模型**: {model}
- **处理时间**: {timestamp}

## 详细描述
{description}

## 元数据
```json
{metadata_json}
```

---
*Generated by ecommerce-multimodal-material-processor*
"""

def generate_archive(self, material_id, labeling_result, metadata=None):
    context = {
        "material_id": material_id,
        "file_path": labeling_result["file_path"],
        "file_size": format_file_size(metadata["size"]),
        "file_type": metadata["type"],
        "resolution_section": self._format_resolution(metadata),
        "duration_section": self._format_duration(metadata),
        "primary_label": labeling_result["label"],
        "confidence": labeling_result["confidence"],
        "alternative_labels": labeling_result.get("alternative_labels", []),
        "provider": labeling_result["provider"],
        "model": labeling_result.get("model", "unknown"),
        "timestamp": labeling_result["timestamp"],
        "description": labeling_result.get("description", ""),
        "metadata_json": json.dumps(metadata, indent=2, ensure_ascii=False),
    }
    
    report_content = ARCHIVE_TEMPLATE.format(**context)
    
    # 写入文件
    output_path = self.output_dir / f"{material_id}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    return output_path
```

**批量生成**:

```python
def batch_archive(self, materials_dir, cache_file):
    cache = CacheManager(cache_file)
    output_dir = Path("material_archives")
    output_dir.mkdir(exist_ok=True)
    
    results = []
    for material_id, result in tqdm(cache.cache.items(), desc="Archiving"):
        metadata = self.extract_metadata(materials_dir / material_id)
        archive_path = self.generate_archive(material_id, result, metadata)
        results.append(archive_path)
    
    return results
```

---

### 5. 导出服务模块 (`exporter.py`)

**支持的导出格式**:

#### Excel导出

```python
import pandas as pd
import tempfile

class CacheExporter:
    def export_to_excel(self, cache_file, output_path):
        # 加载缓存数据
        cache = pd.read_json(cache_file)
        
        # 展开嵌套字段
        df = pd.json_normalize(cache.cache.values())
        
        # 选择和排序列
        columns_order = [
            "material_id",
            "file_path",
            "file_type",
            "primary_label",
            "confidence",
            "alternative_labels",
            "provider",
            "model",
            "processing_time",
            "image_resolution",
            "video_duration",
        ]
        df = df[[col for col in columns_order if col in df.columns]]
        
        # 原子写入(避免文件损坏)
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".xlsx",
            dir=output_path.parent,
            delete=False
        ) as tmp:
            temp_path = tmp.name
        
        # 写入临时文件
        df.to_excel(temp_path, index=False, engine="openpyxl")
        
        # 原子重命名
        final_path = output_path / "results.xlsx"
        Path(temp_path).rename(final_path)
        
        return final_path
```

#### JSON导出

```python
def export_to_json(self, cache_file, output_path):
    cache = CacheManager(cache_file)
    
    output_path = Path(output_path) / "exported_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cache.cache, f, ensure_ascii=False, indent=2)
    
    return output_path
```

---

### 6. 视频处理工具 (`video_utils.py`)

**依赖**: ffmpeg (必须在系统PATH中)

**核心函数**:

```python
import subprocess
import cv2
import numpy as np

def extract_frames(video_path, fps=1, max_frames=60):
    """
    从视频中抽取关键帧
    
    Args:
        video_path: 视频文件路径
        fps: 抽帧频率(每秒多少帧)
        max_frames: 最大保留帧数
    
    Returns:
        List[np.ndarray]: 帧图像列表(JPEG编码的字节数据)
    """
    cap = cv2.VideoCapture(str(video_path))
    
    frames = []
    frame_interval = int(cap.get(cv2.CAP_PROP_FPS) / fps)
    frame_count = 0
    saved_count = 0
    
    while True and saved_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        
        if frame_count % frame_interval == 0:
            # 编码为JPEG
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            frames.append(buffer.tobytes())
            saved_count += 1
        
        frame_count += 1
    
    cap.release()
    return frames


def extract_audio(video_path, output_format="mp3"):
    """
    提取视频的音频轨道
    
    Args:
        video_path: 视频文件路径
        output_format: 输出音频格式(mp3/wav/flac)
    
    Returns:
        bytes: 音频数据
    """
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix=f".{output_format}", delete=False) as tmp:
        output_path = tmp.name
    
    cmd = [
        "ffmpeg",
        "-i", str(video_path),       # 输入文件
        "-vn",                       # 不包含视频
        "-acodec", "libmp3lame",     # 音频编码器
        "-y",                        # 覆盖输出文件
        output_path
    ]
    
    subprocess.run(cmd, check=True, capture_output=True)
    
    with open(output_path, "rb") as f:
        audio_data = f.read()
    
    # 清理临时文件
    Path(output_path).unlink()
    
    return audio_data


def get_video_info(video_path):
    """
    获取视频元信息
    
    Returns:
        dict: 包含duration(时长)、fps(帧率)、resolution(分辨率)等
    """
    cap = cv2.VideoCapture(str(video_path))
    
    info = {
        "duration": cap.get(cv2.CAP_PROP_FRAME_COUNT) / cap.get(cv2.CAP_PROP_FPS),
        "fps": cap.get(cv2.CAP_PROP_FPS),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    
    cap.release()
    return info
```

---

### 7. 依赖检查模块 (`deps_checker.py`)

**功能**: 运行时环境诊断

```python
class DependencyChecker:
    def run_full_check(self):
        """执行完整的环境检查"""
        errors = []
        warnings = []
        
        # 1. Python版本检查
        python_version = sys.version_info
        if python_version < (3, 10):
            errors.append(f"Python版本过低: {python_version.major}.{python_version.minor}, 需要 >= 3.10")
        
        # 2. 必要依赖检查
        required_packages = [
            ("openai", "1.30"),
            ("pandas", "2.0"),
            ("tqdm", "4.65"),
            ("opencv-python", "4.8"),
            ("httpx", "0.25"),
            ("Pillow", "10.0"),
            ("pydantic", "2.0"),
        ]
        
        for package, min_version in required_packages:
            try:
                mod = __import__(package.replace("-", "_"))
                version = getattr(mod, "__version__", "unknown")
                if parse_version(version) < parse_version(min_version):
                    warnings.append(f"{package} 版本较低: {version}, 建议 >= {min_version}")
            except ImportError:
                errors.append(f"缺少必要依赖: {package}(pip install {package})")
        
        # 3. ffmpeg检查
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            warnings.append("ffmpeg未安装,视频处理功能将不可用")
        else:
            logger.info(f"✅ ffmpeg已安装: {ffmpeg_path}")
        
        # 4. API Key配置检查
        configured = settings.validate_provider_config()
        if len(configured) == 0:
            errors.append("未配置任何Provider的API Key,请编辑.env文件")
        else:
            logger.info(f"✅ 已配置 {len(configured)} 个Provider: {', '.join(configured)}")
        
        # 5. 目录权限检查
        output_dirs = [
            settings.archive_output_dir,
            settings.excel_export_dir,
            settings.cache_dir,
        ]
        
        for dir_path in output_dirs:
            dir_path.mkdir(parents=True, exist_ok=True)
            if not os.access(dir_path, os.W_OK):
                errors.append(f"输出目录不可写: {dir_path}")
        
        passed = len(errors) == 0
        return passed, errors, warnings
```

---

## 数据流图

### 完整处理流水线

```
┌──────────────┐
│   输入源     │
│ (Excel/本地) │
└──────┬───────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│   Downloader ├────▶│  本地文件    │
│  (并发下载)   │     │  (按ID组织)  │
└──────────────┘     └──────┬───────┘
                            │
                            ▼
                   ┌──────────────┐
                   │   Labeler    │◀──────┐
                   │  (AI打标)    │       │
                   └──────┬───────┘       │
                          │               │
                          ▼               │  重试/退避
                   ┌──────────────┐       │
                   │  Cache Manager│──────┘
                   │  (JSON缓存)   │
                   └──────┬───────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
     ┌────────────┐ ┌──────────┐ ┌──────────┐
     │  Archiver  │ │ Exporter │ │ Search   │
     │ (MD报告)   │ │(Excel)   │ │ Service  │
     └─────┬──────┘ └────┬─────┘ └────┬─────┘
           │             │            │
           ▼             ▼            ▼
    material_archives/  excel_exports/  LanceDB
    (*.md)             (*.xlsx)       (向量索引)
```

---

## 性能优化策略

### 1. 并发控制

**问题**: 大量IO操作导致处理缓慢

**解决方案**:
- 下载阶段: `ThreadPoolExecutor`(默认5 workers)
- 打标阶段: `asyncio.Semaphore`(限制并发API调用)
- 导出阶段: 单线程(避免文件竞争)

```python
# 并发下载示例
with ThreadPoolExecutor(max_workers=workers) as executor:
    futures = [executor.submit(download, url) for url in urls]
    results = [future.result() for future in as_completed(futures)]
```

### 2. 内存优化

**问题**: 大批次图片加载导致内存溢出

**解决方案**:
- 流式处理: 逐个读取图片,不一次性加载全部
- 及时释放: 处理完立即释放内存
- 限制分辨率: 最大768px,减少内存占用

```python
async def process_batch(self, batch):
    results = []
    for item in batch:
        image = load_image(item.path)  # 加载
        result = await self.label(image)  # 处理
        del image  # 释放
        results.append(result)
    return results
```

### 3. API调用优化

**问题**: 频繁触发限流,增加延迟

**解决方案**:
- 批量请求: 将多个素材合并为一次API调用(如果模型支持)
- 智能退避: 根据错误类型调整等待时间
- 缓存优先: 已处理的素材直接返回缓存结果

```python
# 智能退避示例
async def handle_rate_limit(self, error):
    if error.status_code == 429:
        # 短时限流,快速重试
        retry_after = int(error.headers.get("Retry-After", 10))
        await asyncio.sleep(retry_after)
    elif error.status_code == 529:
        # 服务过载,较长等待
        await asyncio.sleep(60)
    elif isinstance(error, QuotaExhaustedError):
        # 配额耗尽,长时间等待
        await asyncio.sleep(5 * 3600)  # 5小时
```

---

## 安全性考虑

### 1. API Key保护

- ❌ 禁止硬编码在代码中
- ✅ 使用环境变量或`.env`文件
- ✅ `.env`文件加入`.gitignore`
- ✅ 日志中脱敏显示(`sk-***abc`)

### 2. 文件操作安全

- 原子写入: tempfile + rename
- 路径遍历防护: 验证输出路径在允许范围内
- 文件名清理: 移除特殊字符

### 3. 网络安全

- HTTPS强制: 所有API调用必须使用HTTPS
- 超时设置: 避免长时间挂起
- 证书验证: 不禁用SSL验证

---

## 测试策略

### 单元测试

```python
# tests/test_labeler.py
import pytest
from ecommerce_processor.labeler import MaterialLabeler

def test_extract_label_valid():
    labeler = MaterialLabeler()
    response = '{"label": "空镜草稿(核心款)", "confidence": 0.95}'
    result = labeler.extract_label(response)
    assert result["primary"] == "空镜草稿(核心款)"
    assert result["confidence"] == 0.95

def test_extract_label_invalid():
    labeler = MaterialLabeler()
    response = '{"error": "invalid response"}'
    with pytest.raises(LabelParseError):
        labeler.extract_label(response)
```

### 集成测试

```bash
# tests/test_integration.sh
#!/bin/bash

# 准备测试数据
python setup_test_data.py --count 100

# 运行完整流程
python run_pipeline.py download --excel test_materials.xlsx --output test_output
python run_pipeline.py label --provider gemini --materials-dir test_output
python run_pipeline.py archive --materials-dir test_output
python run_pipeline.py export-cache --format excel

# 验证输出
assert [ -f test_output/labeling_cache.json ]
assert [ $(ls test_output/material_archives/*.md | wc -l) -eq 100 ]
assert [ -f excel_exports/results.xlsx ]

# 清理
rm -rf test_output excel_exports
```

### 性能测试

```python
# tests/benchmark.py
import time
from ecommerce_processor.labeler import MaterialLabeler

def benchmark_labeling(num_samples=500):
    labeler = MaterialLabeler(provider="minicpm")
    
    start_time = time.time()
    results = []
    
    for i in range(num_samples):
        result = labeler.label_image(f"test_images/sample_{i}.jpg")
        results.append(result)
    
    elapsed = time.time() - start_time
    
    print(f"处理 {num_samples} 个素材耗时: {elapsed:.2f}s")
    print(f"平均每个素材: {elapsed/num_samples:.2f}s")
    print(f"吞吐量: {num_samples/elapsed:.2f} 素材/秒")

if __name__ == "__main__":
    benchmark_labeling()
```

---

## 部署架构

### 开发环境

```
开发者机器
├── Python 3.10+ (venv)
├── .env.local (开发用API Keys)
├── VS Code + Python插件
└── Git版本控制
```

### 生产环境

```
生产服务器
├── Docker容器(推荐)
│   ├── python:3.12-slim基础镜像
│   ├── 安装ffmpeg系统依赖
│   ├── 复制项目代码
│   └── 设置环境变量
├── Systemd/Cron定时任务
├── Nginx反向代理(如需Web界面)
└── 监控告警(Prometheus + Grafana)
```

**Dockerfile示例**:

```dockerfile
FROM python:3.12-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建非root用户
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# 入口命令
CMD ["python", "run_pipeline.py"]
```

**docker-compose.yml示例**:

```yaml
version: '3.8'

services:
  processor:
    build: .
    env_file:
      - .env.production
    volumes:
      - ./data:/app/data          # 持久化数据
      - ./logs:/app/logs          # 日志
      - ./output:/app/output      # 输出结果
    restart: unless-stopped
  
  # 可选: Web监控界面
  monitoring:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    volumes:
      - ./monitoring:/var/lib/grafana
```

---

## 未来演进路线

### Phase 1: 当前版本(v2.0) ✅
- ✅ 多Provider支持(8种)
- ✅ MCP协议集成
- ✅ 视频音频处理
- ✅ 向量检索服务

### Phase 2: 近期规划(v2.5)
- [ ] Web UI界面(Streamlit/FastAPI)
- [ ] 分布式处理支持(Celery + Redis)
- [ ] 更多导出格式(PDF/HTML/PPT)
- [ ] 标签体系可视化分析

### Phase 3: 中期规划(v3.0)
- [ ] 自定义Prompt模板编辑器
- [ ] 主动学习(Human-in-the-Loop优化)
- [ ] 多语言国际化(i18n)
- [ ] 插件系统(自定义Processor)

### Phase 4: 远景规划(v4.0)
- [ ] 云原生部署(Kubernetes)
- [ ] 实时处理流(Kafka + Flink)
- [ ]联邦学习(隐私保护)
- [ ] AutoML自动调优

---

## 参考资源

- [OpenAI API文档](https://platform.openai.com/docs/api-reference)
- [httpx异步客户端](https://www.python-httpx.org/)
- [Pydantic Settings](https://docs.pydantic/latest/concepts/pydantic_settings/)
- [LanceDB向量数据库](https://lancedb.github.io/)
- [ffmpeg官方文档](https://ffmpeg.org/documentation.html)

---

**维护者**: AI Content Realize Team  
**最后更新**: 2026-07-11  
**版本**: v2.0.0
