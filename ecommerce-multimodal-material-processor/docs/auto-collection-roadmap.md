# 自动采集路线图 (Auto Collection Roadmap)

> 本文档规划电商素材自动采集、处理、归档的完整演进路线,从手动半自动化到全自动化智能系统的技术路径。

## 当前状态评估 (v2.0)

###  已实现能力

#### 1. 半自动采集阶段
- **Excel/CSV导入**: 手动整理素材URL列表,批量下载
- **本地目录扫描**: 递归扫描已有素材文件夹
- **并发下载引擎**: ThreadPoolExecutor + 超时控制 + 断点续传

#### 2. AI智能标注
- **8种AI Provider**: Gemini/MiniMax/Kimi/MINICPM/Paddle等
- **多模态支持**: 图片(Base64) + 视频(ffmpeg抽帧) + 音频(Whisper转写)
- **MCP协议集成**: MiniMax understand_image接口(结构化输出)
- **智能重试**: 指数退避 + 配额等待 + 缓存去重

#### 3. 结果导出与归档
- **多格式输出**: Excel/JSON/Markdown
- **原子写入**: tempfile + rename保证数据完整性
- **详细报告**: 每个素材一份Markdown报告(含元数据、标签、置信度)
- **SMB同步**: 可选的网络共享目录同步

#### 4. 质量监控
- **标签分布统计**: 自动计算各类别占比
- **"其他"标签预警**: 超过20%触发告警
- **缓存完整性校验**: JSON格式验证 + 数据一致性检查

---

###  当前痛点

1. **人工介入过多**
   - 需要手动整理Excel URL列表
   - 无法自动发现新增素材
   - SMB目录变化需人工触发同步

2. **实时性不足**
   - 批量处理模式,非实时流式
   - 新素材从产生到完成标注可能需要数小时
   - 无法满足"即产即标"的业务需求

3. **闭环缺失**
   - 标注结果无法反哺业务系统
   - 缺乏反馈机制优化AI模型
   - 历史案例未形成知识库

4. **扩展性受限**
   - 单机处理,无法水平扩展
   - 素材量级>10万时性能下降明显
   - 多团队协作困难

---

## 演进路线图 (2026 Q3 - 2027 Q2)

### Phase 1: 定时采集增强 (2026 Q3, v2.5)

**目标**: 减少人工干预,实现定时自动采集和增量处理

#### 1.1 定时任务调度器

```python
# 新增模块: scheduler.py

import schedule
import time
from datetime import datetime
from ecommerce_processor import MaterialDownloader, MaterialLabeler

class CollectionScheduler:
    """
    定时采集调度器
    
    支持的任务:
    - 定期扫描源目录/SMB,发现新素材
    - 增量下载(仅处理新增项)
    - 定时执行打标流程
    - 结果通知(邮件/Webhook)
    """
    
    def __init__(self, config_path="scheduler_config.json"):
        self.config = self.load_config(config_path)
        self.downloader = MaterialDownloader()
        self.labeler = MaterialLabeler()
    
    def setup_jobs(self):
        """配置定时任务"""
        
        # 每2小时扫描一次源目录
        schedule.every(2).hours.do(
            self.job_scan_source_directory,
            source_dir=self.config["source_dir"],
        )
        
        # 每天凌晨3点执行全量打标
        schedule.every().day.at("03:00").do(
            self.job_full_labeling,
            materials_dir=self.config["materials_dir"],
            provider=self.config["default_provider"],
        )
        
        # 每6小时增量打标(仅处理新素材)
        schedule.every(6).hours.do(
            self.job_incremental_labeling,
            materials_dir=self.config["materials_dir"],
        )
        
        # 每周日生成周报
        schedule.sunday.at("10:00").do(
            self.job_generate_weekly_report,
        )
    
    def job_scan_source_directory(self, source_dir):
        """扫描源目录,发现新素材"""
        logger.info(f" Scanning source directory: {source_dir}")
        
        # 记录上次扫描状态
        last_scan_file = Path(".last_scan_state")
        last_state = {}
        if last_scan_file.exists():
            with open(last_scan_file, "r") as f:
                last_state = json.load(f)
        
        # 当前扫描
        current_files = set(source_dir.rglob("*.*"))
        last_files = set(last_state.get("files", []))
        
        # 发现新增文件
        new_files = current_files - last_files
        
        if new_files:
            logger.info(f" Found {len(new_files)} new files")
            
            # 记录到待处理队列
            queue_file = Path(".pending_queue.json")
            queue = []
            if queue_file.exists():
                with open(queue_file, "r") as f:
                    queue = json.load(f)
            
            queue.extend([str(f) for f in new_files])
            
            with open(queue_file, "w") as f:
                json.dump(queue, f, indent=2)
            
            # 发送通知
            self.send_notification(
                f"发现 {len(new_files)} 个新素材,已加入处理队列"
            )
        else:
            logger.info("ℹ No new files found")
        
        # 更新扫描状态
        with open(last_scan_file, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "files": [str(f) for f in current_files],
            }, f, indent=2)
    
    def job_incremental_labeling(self, materials_dir):
        """增量打标: 仅处理未缓存的素材"""
        cache_file = Path("labeling_cache.json")
        cache = CacheManager(cache_file)
        
        # 获取所有素材ID
        all_materials = [d.name for d in materials_dir.iterdir() if d.is_dir()]
        
        # 筛选出未处理的素材
        unprocessed = [
            m for m in all_materials
            if not cache.is_cached(m)
        ]
        
        if not unprocessed:
            logger.info(" All materials are up-to-date")
            return
        
        logger.info(f" Processing {len(unprocessed)} new materials...")
        
        # 执行打标
        results = []
        for material_id in tqdm(unprocessed, desc="Incremental Labeling"):
            result = await self.labeler.label_material(
                materials_dir / material_id
            )
            cache.save_result(material_id, result)
            results.append(result)
        
        # 统计
        labels = Counter(r["label"] for r in results)
        logger.info(f" Completed {len(results)} materials")
        logger.info(f" Label distribution: {dict(labels)}")
        
        # 质量检查
        other_ratio = labels.get("other", 0) / len(results)
        if other_ratio > 0.2:
            logger.warning(f' "Other" label ratio ({other_ratio:.1%}) exceeds threshold!')
            self.send_quality_alert(other_ratio, results)
    
    def run(self):
        """启动调度器"""
        self.setup_jobs()
        logger.info("⏰ Scheduler started")
        
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次
```

**配置示例** (`scheduler_config.json`):

```json
{
  "source_dir": "\\\\dewu-server\\materials\\incoming",
  "materials_dir": "./downloaded_materials",
  "default_provider": "gemini",
  
  "notification": {
    "enabled": true,
    "webhook_url": "https://hooks.slack.com/TXXX/BXXX/XXXX",
    "email_recipients": ["team@company.com"],
    "notify_on_completion": true,
    "notify_on_error": true,
    "quality_threshold": 0.2
  },
  
  "retention_policy": {
    "keep_raw_materials_days": 30,
    "keep_archives_days": 90,
    "compress_old_reports": true
  }
}
```

**部署方式**:

```bash
# 启动后台调度服务
nohup python run_scheduler.py > scheduler.log 2>&1 &

# 或使用systemd(Linux)
sudo cp ecommerce-scheduler.service /etc/systemd/system/
sudo systemctl enable ecommerce-scheduler
sudo systemctl start ecommerce-scheduler
```

---

#### 1.2 文件监控(File Watchdog)

```python
# 新增模块: file_watcher.py

import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class MaterialFileHandler(FileSystemEventHandler):
    """
    文件系统事件处理器
    
    监控以下事件:
    - CREATED: 新文件创建 → 加入处理队列
    - MODIFIED: 文件修改 → 标记为需重新处理
    - MOVED: 文件移动 → 更新路径映射
    """
    
    def __init__(self, queue_manager):
        super().__init__()
        self.queue = queue_manager
        self.debounce_timer = {}  # 防抖计时器
    
    def on_created(self, event):
        """新文件创建事件"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # 过滤非素材文件
        if not self._is_material_file(file_path):
            return
        
        logger.debug(f" New file detected: {file_path}")
        
        # 防抖: 避免大文件复制过程中多次触发
        self._debounce("created", file_path, delay=5.0, callback=lambda: self._enqueue(file_path))
    
    def on_modified(self, event):
        """文件修改事件"""
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        if not self._is_material_file(file_path):
            return
        
        logger.debug(f" File modified: {file_path}")
        
        # 标记为需重新处理
        self._debounce("modified", file_path, delay=10.0, callback=lambda: self._mark_for_reprocess(file_path))
    
    def _is_material_file(self, file_path):
        """判断是否为素材文件"""
        material_extensions = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".avi"}
        return file_path.suffix.lower() in material_extensions
    
    def _debounce(self, event_type, file_path, delay, callback):
        """防抖机制"""
        key = f"{event_type}:{file_path}"
        
        if key in self.debounce_timer:
            self.debounce_timer[key].cancel()
        
        timer = threading.Timer(delay, callback)
        self.debounce_timer[key] = timer
        timer.start()


def start_watching(watch_dir, queue_manager):
    """启动文件监控"""
    event_handler = MaterialFileHandler(queue_manager)
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=True)
    
    observer.start()
    logger.info(f" Started watching: {watch_dir}")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    
    observer.join()
```

**优势**:
- 实时响应: 文件创建后5秒内加入队列
- 低开销: 基于操作系统事件,无需轮询
- 可靠: 防抖机制避免重复处理

---

### Phase 2: 智能采集网络 (2026 Q4, v3.0)

**目标**: 构建多源自动采集能力,支持API对接、爬虫、Webhook等多种方式

#### 2.1 API对接层

```python
# 新增模块: api_collectors/

class BaseCollector(ABC):
    """采集器基类"""
    
    @abstractmethod
    async def collect(self, since: datetime) -> List[Dict]:
        """
        采集指定时间之后的新素材
        
        Returns:
            List[Dict]: 素材元数据列表
                - material_id: str
                - url: str
                - type: image|video
                - metadata: Dict
        """
        pass


class DAMCollector(BaseCollector):
    """
    数字资产管理(DAM)系统采集器
    
    支持的系统:
    - Bynder
    - Brandfolder
    - Canto
    - 自建DAM
    """
    
    def __init__(self, config):
        self.api_key = config["api_key"]
        self.base_url = config["base_url"]
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
    
    async def collect(self, since: datetime) -> List[Dict]:
        params = {
            "modified_since": since.isoformat(),
            "limit": 100,
            "fields": "id,name,url,type,metadata",
        }
        
        response = await self.client.get("/api/v2/assets", params=params)
        response.raise_for_status()
        
        assets = response.json()["assets"]
        
        return [
            {
                "material_id": asset["id"],
                "url": asset["url"],
                "type": asset["type"],
                "metadata": asset.get("metadata", {}),
            }
            for asset in assets
            if asset["type"] in ("image", "video")
        ]


class CloudStorageCollector(BaseCollector):
    """
    云存储采集器
    
    支持:
    - AWS S3
    - Google Cloud Storage
    - Azure Blob Storage
    - 阿里云OSS
    """
    
    def __init__(self, provider, config):
        self.provider = provider
        self.config = config
        
        if provider == "s3":
            import boto3
            self.client = boto3.client(
                "s3",
                aws_access_key_id=config["access_key"],
                aws_secret_access_key=config["secret_key"],
            )
            self.bucket = config["bucket"]
            self.prefix = config.get("prefix", "")
        
        elif provider == "gcs":
            from google.cloud import storage
            self.client = storage.Client.from_service_account_json(config["credentials"])
            self.bucket = self.client.bucket(config["bucket"])
            self.prefix = config.get("prefix", "")
    
    async def collect(self, since: datetime) -> List[Dict]:
        materials = []
        
        if self.provider == "s3":
            paginator = self.client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=self.prefix,
            )
            
            for page in paginator.paginate():
                for obj in page.get("Contents", []):
                    if obj["LastModified"] >= since.tzinfo and self._is_material(obj["Key"]):
                        url = self.client.generate_presigned_url(
                            "get_object",
                            Params={"Bucket": self.bucket, "Key": obj["Key"]},
                            ExpiresIn=3600,
                        )
                        
                        materials.append({
                            "material_id": obj["Key"].split("/")[-1],
                            "url": url,
                            "type": "image" if self._is_image(obj["Key"]) else "video",
                            "metadata": {"size": obj["Size"], "modified": obj["LastModified"].isoformat()},
                        })
        
        elif self.provider == "gcs":
            blobs = self.client.list_blobs(prefix=self.prefix)
            
            async for blob in blobs:
                if blob.time_created >= since and self._is_material(blob.name):
                    url = blob.generate_signed_url(expiration=timedelta(hours=1))
                    
                    materials.append({
                        "material_id": blob.name.split("/")[-1],
                        "url": url,
                        "type": "image" if self._is_image(blob.name) else "video",
                        "metadata": {"size": blob.size, "modified": blob.time_created.isoformat()},
                    })
        
        return materials
```

**配置示例** (`collectors_config.json`):

```json
{
  "collectors": [
    {
      "name": "dam_system",
      "type": "dam",
      "enabled": true,
      "config": {
        "provider": "bynder",
        "api_key": "${BYNDER_API_KEY}",
        "base_url": "https://dam.company.com",
        "poll_interval_minutes": 30
      }
    },
    {
      "name": "s3_marketing_bucket",
      "type": "cloud_storage",
      "enabled": true,
      "config": {
        "provider": "s3",
        "bucket": "marketing-assets-prod",
        "prefix": "ecommerce/materials/",
        "access_key": "${AWS_ACCESS_KEY}",
        "secret_key": "${AWS_SECRET_KEY}"
      }
    },
    {
      "name": "smb_shared_folder",
      "type": "smb_watch",
      "enabled": true,
      "config": {
        "path": "\\\\fileserver\\marketing\\new_assets",
        "watch_subdirectories": true
      }
    }
  ],
  
  "deduplication": {
    "enabled": true,
    "method": "hash_md5",  # md5_hash | perceptual_hash | metadata_match
    "similarity_threshold": 0.95
  },
  
  "rate_limiting": {
    "max_collections_per_hour": 1000,
    "max_downloads_per_minute": 50
  }
}
```

---

#### 2.2 Webhook接收器

```python
# 新增模块: webhook_receiver.py

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Material Collection Webhook")

class WebhookPayload(BaseModel):
    """Webhook载荷标准格式"""
    event_type: str  # material.created | material.updated | batch.import
    timestamp: str
    data: List[Dict]  # 素材列表
    
    class Config:
        extra = "allow"  # 允许额外字段


@app.post("/webhook/materials")
async def receive_material_webhook(payload: WebhookPayload, request: Request):
    """
    接收外部系统推送的新素材通知
    
    支持的来源:
    - CMS系统(内容发布时推送)
    - 设计工具(Figma/Sketch插件)
    - ERP系统(产品上新)
    - 第三方DAM系统
    """
    # 验证签名(如果配置了密钥)
    signature = request.headers.get("X-Signature")
    if settings.webhook_secret:
        expected_sig = compute_signature(payload.json(), settings.webhook_secret)
        if signature != expected_sig:
            raise HTTPException(status_code=403, detail="Invalid signature")
    
    logger.info(f" Webhook received: {payload.event_type}, {len(payload.data)} materials")
    
    # 解析并入队
    queued_count = 0
    for item in payload.data:
        material = {
            "source": "webhook",
            "event_type": payload.event_type,
            "material_id": item.get("id") or item.get("material_id"),
            "url": item.get("url") or item.get("download_url"),
            "type": item.get("type", "image"),
            "metadata": item.get("metadata", {}),
            "received_at": datetime.now().isoformat(),
        }
        
        # 验证必填字段
        if not material["material_id"] or not material["url"]:
            logger.warning(f" Missing required fields: {material}")
            continue
        
        # 加入处理队列
        queue_manager.enqueue(material)
        queued_count += 1
    
    # 返回确认
    return {
        "status": "accepted",
        "queued": queued_count,
        "message": f"{queued_count} materials added to processing queue",
    }


@app.post("/webhook/batch-import")
async def receive_batch_import(request: Request):
    """
    接收批量导入请求(如Excel上传)
    
    Content-Type: multipart/form-data
    - file: Excel/CSV文件
    - columns_mapping: JSON字符串(列名映射)
    """
    form = await request.form()
    uploaded_file = form.get("file")
    columns_mapping = json.loads(form.get("columns_mapping", "{}"))
    
    # 保存并解析文件
    temp_path = save_uploaded_file(uploaded_file)
    materials = parse_excel(temp_path, columns_mapping)
    
    # 批量入队
    for mat in materials:
        queue_manager.enqueue(mat)
    
    return {
        "status": "accepted",
        "total": len(materials),
        "queued": len(materials),
    }
```

**部署方式**:

```bash
# 启动Webhook服务
uvicorn webhook_receiver:app --host 0.0.0.0 --port 8080

# 使用Nginx反向代理
server {
    listen 443 ssl;
    server_name webhook.yourcompany.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location /webhook/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Signature $http_x_signature;
    }
}
```

---

#### 2.3 智能去重引擎

```python
# 新增模块: deduplicator.py

import hashlib
from perceptual_hash import phash, distance

class MaterialDeduplicator:
    """
    素材去重引擎
    
    三层去重策略:
    1. 元数据匹配(快速): 文件名/大小/修改时间
    2. MD5哈希(精确): 文件内容完全相同
    3. 感知哈希(模糊): 图片视觉相似度
    """
    
    def __init__(self, cache_db="dedup_cache.db"):
        self.cache = sqlite3.connect(cache_db)
        self._init_db()
    
    def is_duplicate(self, material_meta) -> Tuple[bool, Optional[str]]:
        """
        检查是否为重复素材
        
        Returns:
            (is_duplicate, original_material_id)
        """
        # Layer 1: 元数据快速过滤
        meta_dup = self._check_metadata(material_meta)
        if meta_dup:
            return True, meta_dup
        
        # Layer 2: MD5精确匹配(需要下载后计算)
        # 在下载完成后调用 self.check_md5(content)
        
        # Layer 3: 感知哈希模糊匹配(需要图片解码)
        # 在打标前调用 self.check_perceptual_hash(image_data)
        
        return False, None
    
    def check_md5(self, content: bytes, material_id: str) -> Tuple[bool, Optional[str]]:
        """MD5精确去重"""
        md5_hash = hashlib.md5(content).hexdigest()
        
        cursor = self.cache.execute(
            "SELECT material_id FROM materials WHERE md5_hash = ?",
            (md5_hash,)
        )
        result = cursor.fetchone()
        
        if result:
            return True, result[0]
        
        # 存储新的MD5
        self.cache.execute(
            "INSERT INTO materials (material_id, md5_hash) VALUES (?, ?)",
            (material_id, md5_hash),
        )
        self.cache.commit()
        
        return False, None
    
    def check_perceptual_hash(self, image_data: bytes, material_id: str, threshold=10) -> Tuple[bool, Optional[str]]:
        """
        感知哈希模糊去重
        
        Args:
            threshold: 汉明距离阈值(越小越严格,默认10表示约95%相似)
        """
        try:
            img_hash = phash(image_data)
        except Exception:
            return False, None
        
        cursor = self.cache.execute(
            "SELECT material_id, p_hash FROM materials WHERE p_hash IS NOT NULL"
        )
        
        for row in cursor.fetchall():
            existing_id, existing_hash = row
            
            if existing_hash:
                dist = distance(img_hash, existing_hash)
                if dist <= threshold:
                    return True, existing_id
        
        # 存储感知哈希
        self.cache.execute(
            "UPDATE materials SET p_hash = ? WHERE material_id = ?",
            (str(img_hash), material_id),
        )
        self.cache.commit()
        
        return False, None
```

**效果预期**:
- 元数据过滤: 排除60-70%的明显重复
- MD5精确去重: 排除95%以上的完全重复文件
- 感知哈希: 发现经过裁剪/压缩/水印添加的近似重复

---

### Phase 3: 分布式处理架构 (2027 Q1, v3.5)

**目标**: 支持水平扩展,处理百万级素材

#### 3.1 任务队列(Celery + Redis)

```python
# tasks.py

from celery import Celery
from ecommerce_processor import MaterialLabeler

app = Celery("processor", broker="redis://localhost:6379/0")

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_routes={
        "tasks.label_image": {"queue": "labeling"},
        "tasks.label_video": {"queue": "video_processing"},
        "tasks.generate_archive": {"queue": "io_bound"},
    },
)


@app.task(bind=True, max_retries=5, default_retry_delay=60)
def label_material_task(self, material_id, material_path, provider="gemini"):
    """
    Celery异步任务: 标注单个素材
    
    特性:
    - 自动重试(最多5次)
    - 失败通知(Sentry/邮件)
    - 进度追踪(Flower UI)
    """
    try:
        labeler = MaterialLabeler(provider=provider)
        result = labeler.label_material(Path(material_path))
        
        # 存储结果
        cache.save_result(material_id, result)
        
        # 触发后续任务(归档、导出)
        generate_archive_task.delay(material_id, result)
        
        return {"status": "success", "material_id": material_id, "label": result["label"]}
        
    except QuotaExhaustedError as exc:
        # 配额耗尽,长时间等待后重试
        raise self.retry(exc=exc, countdown=5 * 3600)  # 5小时
        
    except RateLimitError as exc:
        # 限流,指数退避
        countdown = 60 * (2 ** self.request.retries)
        raise self.retry(exc=exc, countdown=countdown)
        
    except Exception as exc:
        # 其他错误,记录日志
        logger.error(f"Task failed: {exc}", exc_info=True)
        raise self.retry(exc=exc)


@app.task
def batch_label_task(material_ids, provider="gemini"):
    """
    批量标注任务(用于工作流编排)
    """
    from celery import group
    
    # 并发启动子任务
    job = group(
        label_material_task.s(mid, f"/data/materials/{mid}", provider)
        for mid in material_ids
    )
    
    result = job.apply_async()
    
    return result.id  # 返回GroupResult ID,可用于查询进度
```

**部署架构**:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Worker 1   │     │  Worker 2   │     │  Worker N   │
│ (8核/16GB)  │     │ (8核/16GB)  │     │ (8核/16GB)  │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                  ┌────────▼────────┐
                  │     Redis       │
                  │  (Broker+Backend)│
                  └────────┬────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ Flower   │ │  Sentry  │ │ Grafana  │
       │ (Monitor)│ │ (Errors) │ │ (Metrics)│
       └──────────┘ └──────────┘ └──────────┘
```

**扩容计算**:

| 日均素材量 | Worker数量 | 配置 | 成本估算 |
|-----------|------------|------|----------|
| 1万 | 1台 | 4核8G | ~$50/月 |
| 10万 | 4台 | 8核16G | ~$200/月 |
| 100万 | 20台 | 16核32G | ~$1000/月 |

---

#### 3.2 微服务拆分

```yaml
# docker-compose.yml (微服务版本)

version: '3.8'

services:
  # API网关
  gateway:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - api-server
      - collector-service
      - labeling-service
  
  # RESTful API服务
  api-server:
    build: ./services/api
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/ecommerce
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
  
  # 采集服务
  collector-service:
    build: ./services/collector
    environment:
      - REDIS_URL=redis://redis:6379/0
      - S3_BUCKET=${AWS_S3_BUCKET}
    deploy:
      replicas: 2
  
  # 标注服务
  labeling-service:
    build: ./services/labeler
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - GEMINI_API_KEY=${GEMINI_API_KEY}
    deploy:
      replicas: 4
  
  # Celery Worker
  worker:
    build: ./services/worker
    command: celery -A tasks worker -l info -c 4
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
    deploy:
      replicas: 8
  
  # 基础设施
  db:
    image: postgres:15-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
  
  redis:
    image: redis:7-alpine
    volumes:
      - redisdata:/data

volumes:
  pgdata:
  redisdata:
```

---

### Phase 4: 自主学习与优化 (2027 Q2, v4.0)

**目标**: 引入主动学习和反馈循环,持续提升标注质量

#### 4.1 主动学习(Active Learning)

```python
# 新增模块: active_learning.py

class ActiveLearningOrchestrator:
    """
    主动学习协调器
    
    策略:
    1. 不确定性采样: 选择模型最不确定的样本让人类标注
    2. 多样性采样: 选择代表性样本来覆盖特征空间
    3. 错误分析: 重点选择历史错误案例
    """
    
    def select_samples_for_review(
        self,
        unlabeled_pool: List[Dict],
        budget: int = 50,
        strategy: str = "uncertainty",
    ) -> List[Dict]:
        """
        选择需要人工审核的样本
        
        Args:
            unlabeled_pool: 未确认的标注结果
           预算: 人工审核数量上限
            strategy: uncertainty | diversity | error_prone
        """
        if strategy == "uncertainty":
            # 选择置信度最低的样本
            sorted_pool = sorted(
                unlabeled_pool,
                key=lambda x: x.get("confidence", 0),
            )
            return sorted_pool[:budget]
        
        elif strategy == "diversity":
            # 使用聚类算法选择多样性样本
            embeddings = self.extract_embeddings(unlabeled_pool)
            clusters = KMeans(n_clusters=budget).fit_predict(embeddings)
            
            selected = []
            for cluster_id in range(budget):
                cluster_samples = [
                    s for s, c in zip(unlabeled_pool, clusters) if c == cluster_id
                ]
                selected.append(random.choice(cluster_samples))
            
            return selected
        
        elif strategy == "error_prone":
            # 选择历史上容易出错的类别
            error_prone_labels = self.get_high_error_rate_labels()
            
            selected = [
                s for s in unlabeled_pool
                if s["label"] in error_prone_labels
            ][:budget]
            
            return selected
        
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
    
    def incorporate_feedback(self, human_corrections: List[Dict]):
        """
        将人工修正反馈给模型
        
        流程:
        1. 更新训练数据集
        2. 触发模型微调(或Prompt优化)
        3. 更新标签体系(如果发现新模式)
        """
        for correction in human_corrections:
            material_id = correction["material_id"]
            correct_label = correction["correct_label"]
            original_label = correction["original_label"]
            
            # 记录到反馈数据库
            self.feedback_db.insert({
                "material_id": material_id,
                "original_prediction": original_label,
                "human_correction": correct_label,
                "timestamp": datetime.now().isoformat(),
                "reviewer": correction.get("reviewer", "unknown"),
            })
            
            # 更新缓存
            cache.update(material_id, {"label": correct_label})
        
        # 分析错误模式
        error_analysis = self.analyze_error_patterns()
        
        if error_analysis["should_update_prompt"]:
            self.optimize_prompt(error_analysis["suggestions"])
        
        if error_analysis["should_add_new_label"]:
            self.propose_new_category(error_analysis["candidate_labels"])
```

#### 4.2 反馈循环UI

```javascript
// frontend/review-app/src/components/ReviewPanel.jsx

export function ReviewPanel({ samples, onSubmitFeedback }) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [corrections, setCorrections] = useState({});
  
  const sample = samples[currentIndex];
  
  return (
    <div className="review-panel">
      <div className="sample-display">
        <img src={sample.image_url} alt={sample.material_id} />
        <div className="ai-prediction">
          <span className="label">AI预测:</span>
          <Badge variant={sample.confidence > 0.8 ? "success" : "warning"}>
            {sample.label_name} ({(sample.confidence * 100).toFixed(1)}%)
          </Badge>
        </div>
      </div>
      
      <div className="correction-form">
        <h3>人工修正(如有误)</h3>
        <Select
          options={LABEL_OPTIONS}
          value={corrections[sample.material_id] || sample.label}
          onChange={(value) =>
            setCorrections({...corrections, [sample.material_id]: value})
          }
        />
        
        <TextArea
          placeholder="可选: 描述修正原因..."
          onChange={(e) => setReason(e.target.value)}
        />
      </div>
      
      <div className="actions">
        <Button onClick={() => setCurrentIndex(i => i - 1)} disabled={currentIndex === 0}>
          上一个
        </Button>
        <Button onClick={() => setCurrentIndex(i => i + 1)} disabled={currentIndex === samples.length - 1}>
          下一个 ({currentIndex + 1}/{samples.length})
        </Button>
        <Button
          type="primary"
          onClick={() => onSubmitFeedback(corrections)}
        >
          提交所有修正
        </Button>
      </div>
      
      <ProgressBar percent={(currentIndex / samples.length) * 100} />
    </div>
  );
}
```

---

## 投资回报率(ROI)分析

### 成本节省测算

**当前流程**(手工+半自动):
- 人工筛选素材: 2小时/天 × $30/hour = $60/天
- 人工初步分类: 3小时/天 × $30/hour = $90/天
- AI辅助标注复核: 1小时/天 × $30/hour = $30/天
- **日成本**: $180/天
- **年成本**: $65,700/年

**Phase 1完成后**(定时自动采集):
- 人工干预降至: 30分钟/天(仅处理异常) = $15/天
- API调用成本: ~$5/天(500素材×$0.01)
- **日成本**: $20/天
- **年成本**: $7,300/年
- **节省**: **88.9%** ($58,400/年)

**Phase 4完成后**(自主学习+极少人工):
- 人工干预降至: 10分钟/天(仅边缘case) = $5/天
- API调用成本: ~$5/天
- **日成本**: $10/天
- **年成本**: $3,650/年
- **节省**: **94.4%** ($62,050/年)

---

### 效率提升指标

| 指标 | 当前(v2.0) | Phase 1 | Phase 2 | Phase 4 |
|------|------------|---------|---------|---------|
| **素材→可检索时间** | 4小时 | 1小时 | 10分钟 | 实时(<1min) |
| **人工参与度** | 高(每批需操作) | 中(每日检查) | 低(异常处理) | 极低(周报审核) |
| **标注准确率** | 85% | 87% | 90% | 95%+(持续提升) |
| **处理容量** | 500/天 | 2000/天 | 10000/天 | 100000+/天 |
| **系统可用性** | 95% | 99% | 99.9% | 99.99% |

---

## 风险与缓解

### 技术风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| API Provider服务中断 | 中 | 高 | 多Provider降级 + 本地缓存 |
| 分布式系统复杂度爆炸 | 高 | 中 | 渐进式演进,不过度设计 |
| 数据一致性(分布式) | 中 | 高 | 事务机制 + 幂等设计 |
| 性能瓶颈(DB/Redis) | 低 | 高 | 分库分表 + 读写分离 |

### 业务风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 标签体系频繁变更 | 高 | 中 | 动态Schema + 版本管理 |
| 数据隐私合规(GDPR) | 中 | 高 | 数据脱敏 + 访问审计 |
| 团队技能缺口 | 中 | 中 | 培训 + 文档完善 |

---

## 总结与行动建议

### 近期行动(未来3个月)

1.  **立即实施**: 部署`Phase 1`的定时任务调度器
2.  **本月目标**: 实现`file_watcher`,支持实时监控
3.  **下季度目标**: 完成`API对接层`,对接内部DAM系统

### 中期规划(6-12个月)

1.  **Q4 2026**: 发布`v3.0`,包含完整的采集网络
2.  **Q1 2027**: 开始分布式架构迁移(PoC)
3.  **团队建设**: 招聘DevOps工程师,建立on-call机制

### 远景愿景(12-24个月)

1.  **Q2 2027**: `v4.0`自主学习系统上线
2.  **ROI目标**: 处理成本降低90%+,准确率达到95%+
3.  **生态建设**: 开源核心组件,建立社区

---

**维护者**: AI Content Realize Team  
**最后更新**: 2026-07-11  
**版本**: v1.0 (路线图初稿)
