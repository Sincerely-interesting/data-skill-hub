#  电商多模态素材处理 Skill 示例对话

> 展示如何与AI助手交互,完成电商素材的端到端处理流程

---

## 对话一: 完整流水线处理 (本地目录输入)

**用户**: 我本地有一个素材目录 `{用户指定路径}`,里面大概500个素材子文件夹,图片和视频都有,需要打标分类并生成归档报告。

**处理专家**:

好的,我来执行完整的端到端处理流水线。先进行环境预检。

---

###  Step 1: 环境检查

```
 Python: 3.12.3 
 依赖库: openai 1.30+ / pandas / tqdm / opencv 
 ffmpeg: /usr/bin/ffmpeg 
 .env 配置:
│    已配置至少一个Provider的API Key 
│   状态: 全部就绪,可以开始处理
```

---

###  Step 2: 素材获取 (本地目录)

```
 输入来源: 本地目录 {用户指定路径}
 扫描子文件夹: 487个素材
├─  图片素材: 12,456张 (jpg/png/webp)
├─  视频素材: 893个 (mp4/mov)
└─  跳过无效文件: 23个 (损坏/格式不支持)
```

---

###  Step 3: AI智能标注 (批量处理)

```
 配置:
│ Provider策略: 智能路由 (Gemini为主 + MiniMax备选)
│ 并发数: 3个任务同时进行
│ 重试机制: 失败自动切换Provider,最多3次
│ 输出格式: 结构化JSON (8大标签体系)
│
 执行进度:
███████████████████████████████████████ 100%
│
 成功标注: 13,349个 (99.2%)
 低置信度(<0.6): 108个 → 已标记待人工审核
 完全失败: 0个 (所有任务均通过重试成功)
|
 标签分布统计:
├─ outfit_core (穿搭精选-核心款): 3,847 (28.8%)  主力标签
├─ single_display (单品展示-上脚): 2,156 (16.2%)
├─ still_display (静物展示): 1,892 (14.2%)
├─ creative_still (创意静物): 987 (7.4%)
├─ celebrity_wear (明星穿搭): 267 (2.0%)
├─ performance_test (性能测试): 134 (1.0%)
├─ outfit_secondary (穿搭精选-常规款): 1,543 (11.6%)
└─ other (其他): 2,523 (18.9%)  占比偏高,建议审查
```

---

###  Step 4: 归档报告生成

```
 正在生成归档报告...
 报告已保存至: ./output/archive_report_20260711_143022.md

 报告内容概览:
│
├─  执行摘要
│   ├─ 处理时间: 2026-07-11 14:30:22
│   ├─ 总素材数: 13,349
│   ├─ 处理耗时: 1h 23m 45s
│   └─ 平均每个素材: 3.77秒
│
├─  标签分布图表 (Mermaid语法)
│   └─ 饼图 + 柱状图对比
│
├─  各标签Top10代表性素材
│   ├─ outfit_core: [IMG_001.jpg, IMG_015.jpg, ...]
│   ├─ single_display: [VIDEO_042.mp4, IMG_089.png, ...]
│   └─ ... (每个标签列出置信度最高的10个)
│
├─  异常案例汇总
│   ├─ 低置信度样本列表 (108个)
│   ├─ 标签冲突样本 (疑似误判)
│   └─ 建议人工审核优先级排序
│
└─  详细数据表 (Markdown表格)
    ├─ 素材ID | 标签 | 置信度 | Provider | 耗时 | 备注
    ├─ IMG_0001 | outfit_core | 0.94 | gemini | 2.3s | -
    └─ ... (完整13,349行)
```

---

###  Step 5: 数据导出

```
 导出选项: 全部格式

 Excel导出完成:
   文件: ./output/labeled_materials_20260711.xlsx
   大小: 24.5MB
   工作表: 
     - Sheet1: 全量数据 (13,349行)
     - Sheet2: 按标签分页 (8个工作表)
     - Sheet3: 统计摘要

 JSON导出完成:
   文件: ./output/labeled_materials_20260711.json
   大小: 18.2MB
   结构: 符合JSON Schema定义

 缓存文件更新:
   文件: ./cache/labeling_cache.json
   用途: 支持增量处理和断点续传
```

---

##  最终交付清单

```
 处理结果包:
│
├─  归档报告: archive_report_20260711_143022.md (156KB)
├─  Excel数据: labeled_materials_20260711.xlsx (24.5MB)
├─  JSON数据: labeled_materials_20260711.json (18.2MB)
├─  缓存文件: labeling_cache.json (12.8MB)
│
└─  关键指标:
   ├─  处理成功率: 99.2%
   ├─  平均处理速度: 3.77秒/张
   ├─  高置信度占比(>0.8): 87.3%
   └─  需人工审核: 108个 (0.8%)

 后续建议:
1. 查看"其他"标签(18.9%)是否需要新增标签类别
2. 对108个低置信度样本进行人工复核
3. 定期运行增量处理命令处理新素材
```

---

## 对话二: 仅执行标注任务 (已有素材)

**用户**: 我已经下载好了所有素材在 `./materials` 目录,只需要执行AI标注这一步,用Gemini作为Provider。

**处理专家**:

明白,直接进入标注环节。让我先检查一下缓存状态,看看是否有之前的结果可以复用。

---

###  Step 1: 缓存检查

```bash
# 检查现有缓存
python run_pipeline.py label --check-cache --materials-dir ./materials
```

**输出**:

```
 缓存状态分析:
│
├─ 缓存文件: labeling_cache.json
├─ 总记录数: 5,234条
├─ 上次更新: 2026-07-10 09:15:33
│
├─ 与当前素材比对:
│   ├─ 新增素材: 2,123个 (未标注)
│   ├─ 已有缓存: 3,111个 (可跳过)
│   └─ 缓存失效: 0个 (无过期记录)
│
└─ 建议: 启用增量模式,仅处理新增的2,123个素材
```

---

###  Step 2: 执行增量标注

```bash
# 增量标注命令
python run_pipeline.py label \
  --materials-dir ./materials \
  --provider gemini \
  --incremental \
  --cache-file labeling_cache.json \
  --concurrency 5 \
  --retry-count 3
```

**实时日志输出**:

```
[14:35:01]  开始增量标注任务...
[14:35:01]  待处理素材: 2,123个
[14:35:01]  配置: provider=gemini, concurrency=5, retries=3
[14:35:02]  加载缓存: 3,111条记录
[14:35:05] ████████░░░░░░░░░░░░░░░░░░░░ 50/2123 (2.4%) | ETA: 2h 15m
[14:36:12] █████████████░░░░░░░░░░░░░░ 150/2123 (7.1%) | ETA: 2h 08m
[14:38:45] ████████████████████░░░░░░░ 500/2123 (23.6%) | ETA: 1h 52m
... (中间省略) ...
[16:42:33] ████████████████████████████████████████ 2123/2123 (100.0%)
[16:42:33]  任务完成!
[16:42:33] │
[16:42:33] ├─  成功: 2,118个 (99.76%)
[16:42:33] ├─  失败: 5个 (0.24%)
[16:42:33] └─  低置信度: 89个 (4.19%)
[16:42:33] │
[16:42:33]  标签分布:
[16:42:33] ├─ outfit_core: 612 (28.9%)
[16:42:33] ├─ single_display: 345 (16.3%)
[16:42:33] ├─ still_display: 298 (14.1%)
[16:42:33] ├─ ... (其他标签省略)
[16:42:33] │
[16:42:33]  缓存已更新: 5,235条记录
[16:42:33] ⏱ 总耗时: 2h 7m 32s
[16:42:33]  平均速度: 3.59秒/个
```

---

###  Step 3: 结果快速预览

```bash
# 查看本次标注结果的统计摘要
python run_pipeline.py label --stats --cache-file labeling_cache.json
```

**输出**:

```
 本次标注统计 (2026-07-11 14:35 ~ 16:42):
│
├─ 处理数量: 2,123个
├─ 成功率: 99.76%
├─ 平均置信度: 0.847
│
├─ Top 3 标签:
│   1.  outfit_core (28.9%) - 612个
│   2.  single_display (16.3%) - 345个
│   3.  still_display (14.1%) - 298个
│
├─ Provider使用情况:
│   ├─ gemini: 2,118次 (99.76%)  主力
│   └─ fallback_to_minimax: 5次 (0.24%)  触发降级
│
└─ 性能指标:
   ├─ P50延迟: 2.8秒
   ├─ P95延迟: 8.5秒
   └─ P99延迟: 15.2秒
```

---

## 对话三: 故障排查场景

**用户**: 我在执行标注时遇到大量错误,提示"API rate limit",怎么解决?

**处理专家**:

这是典型的API速率限制问题。让我帮您诊断并提供解决方案。

---

###  Step 1: 错误日志分析

```bash
# 查看最近的错误日志
tail -100 logs/labeling_error.log | grep "rate limit"
```

**典型错误信息**:

```
[ERROR] 2026-07-11 15:23:45 - Rate limit exceeded for provider: gemini
[ERROR] 2026-07-11 15:23:46 - HTTP 429: Too Many Requests
[ERROR] 2026-07-11 15:23:47 - Retry attempt 1/3 failed for material IMG_5678.jpg
```

---

###  Step 2: 解决方案 (按优先级排序)

#### 方案A: 降低并发数 (立即生效)

```bash
# 当前配置可能是 concurrency=10 或更高
# 降低到安全范围

python run_pipeline.py label \
  --materials-dir ./materials \
  --provider gemini \
  --concurrency 2 \        # 从10降到2
  --retry-delay 30 \       # 重试间隔从5秒增加到30秒
  --rate-limit-delay 60    # 每批次之间增加60秒冷却时间
```

**原理**: 
- 减少并发请求数,避免触发Provider的速率限制
- 增加重试间隔,给API足够的恢复时间

#### 方案B: 切换到备用Provider (推荐)

```bash
# 使用MiniMax或Kimi作为主力,Gemini降级为备选

python run_pipeline.py label \
  --materials-dir ./materials \
  --provider minimax \     # 切换到MiniMax
  --fallback-providers gemini,kimi  # 设置fallback链
  --concurrency 5          # MiniMax限制较宽松,可适当提高并发
```

**优势**:
- 不同Provider有不同的配额限制
- 自动fallback机制确保任务不会中断
- 多Provider负载均衡

#### 方案C: 申请提升API配额 (长期方案)

**Gemini API**:
1. 访问 [Google AI Studio](https://aistudio.google.com/)
2. 进入 **Settings** → **Quotas**
3. 申请提升 **Requests per minute** 和 **Tokens per day**
4. 通常1-2个工作日审批通过

**MiniMax API**:
1. 登录 [MiniMax开放平台](https://platform.minimaxi.com/)
2. 进入 **应用管理** → **限额设置**
3. 选择套餐升级或联系商务

#### 方案D: 分时段处理 (规避高峰期)

```bash
# 编写批处理脚本,分散执行
#!/bin/bash
# batch_label.sh

MATERIALS_DIR="./materials"
BATCH_SIZE=200
TOTAL=$(ls $MATERIALS_DIR/*.{jpg,png,mp4} 2>/dev/null | wc -l)
BATCHES=$(( (TOTAL + BATCH_SIZE - 1) / BATCH_SIZE ))

for i in $(seq 1 $BATCHES); do
  echo " Processing batch $i/$BATCHES..."
  
  python run_pipeline.py label \
    --materials-dir $MATERIALS_DIR \
    --provider gemini \
    --batch-size $BATCH_SIZE \
    --batch-offset $(( (i-1) * BATCH_SIZE ))
  
  echo "⏳ Waiting 5 minutes before next batch..."
  sleep 300  # 每批之间等待5分钟
done
```

**使用方法**:
```bash
chmod +x batch_label.sh
nohup ./batch_label.sh > batch_log.txt 2>&1 &
```

---

###  Step 3: 验证修复效果

```bash
# 使用小规模测试验证新配置
python run_pipeline.py label \
  --materials-dir ./test_sample \  # 先用100个样本测试
  --provider minimax \
  --concurrency 3 \
  --dry-run  # 试运行,不实际调用API
```

**预期输出**:

```
 Dry-run模式 (不实际执行API调用)
│
├─ 测试样本数: 100
├─ 配置检查:
│    Provider: minimax (可用)
│    Concurrency: 3 (安全范围内)
│    Fallback链: gemini → kimi (已配置)
│    Rate limit保护: 已启用 (每分钟最多3请求)
│
└─ 预估时间: 6-8分钟 (基于历史性能)
   
 提示: 运行真实任务时移除 --dry-run 参数
```

---

## 对话四: 生产环境部署咨询

**用户**: 我们团队想把这个Pipeline部署到生产环境,每天自动处理约10万张图片,有什么建议?

**处理专家**:

这是个很好的问题!生产环境的大规模部署需要考虑很多因素。让我给您一个完整的架构方案。

---

##  推荐架构方案

### 架构总览

```
                    ┌──────────────────────────────┐
                    │      素材源 (Sources)         │
                    │  OSS/S3/FTP/本地NFS          │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   文件监控服务 (Watchdog)     │
                    │   inotify/fswatch/Polling     │
                    └──────────────┬───────────────┘
                                   │
                    ┌──────────────▼───────────────┐
                    │   消息队列 (Redis/RabbitMQ)   │
                    │   任务分发 & 负载均衡          │
                    └──────┬───────────┬───────────┘
                           │           │
              ┌────────────▼──┐  ┌─────▼──────────┐
              │ Worker Node 1 │  │ Worker Node N  │
              │ (Celery)      │  │ (Celery)       │
              │ - GPU加速     │  │ - CPU模式       │
              │ - 并发20      │  │ - 并发10       │
              └──────┬────────┘  └─────┬──────────┘
                     │                 │
              ┌──────▼─────────────────▼──────────┐
              │        结果存储层                   │
              │  MySQL/MongoDB + LanceDB向量库     │
              └──────────────────┬────────────────┘
                                 │
              ┌──────────────────▼────────────────┐
              │        服务层                       │
              │  REST API / GraphQL / Webhook      │
              └──────────────────┬────────────────┘
                                 │
              ┌──────────────────▼────────────────┐
              │        前端展示                      │
              │  Dashboard / 报告系统 / 告警通知     │
              └───────────────────────────────────┘
```

---

###  性能指标预估 (10万张/天)

| 指标 | 单机模式 (优化后) | 分布式集群 (推荐) |
|------|------------------|------------------|
| **处理能力** | 3-5万张/天 | 10-20万张/天 |
| **节点数量** | 1台高性能服务器 | 3-5台Worker节点 |
| **硬件需求** | 32核CPU + RTX 3090 | 16核CPU + 可选GPU |
| **成本估算** | ¥5,000/月 (云服务器) | ¥8,000-12,000/月 |
| **可用性** | 99.5% (单点故障) | 99.99% (高可用) |

---

###  技术选型建议

#### 1. 任务队列: Redis + Celery

```python
# celery_config.py
from celery import Celery

app = Celery('ecommerce_processor')
app.conf.update(
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/1',
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    utc=True,
    
    # 任务路由配置
    task_routes={
        'tasks.label_image': {'queue': 'labeling'},
        'tasks.process_video': {'queue': 'video'},
        'tasks.generate_report': {'queue': 'reports'},
    },
    
    # 并发控制
    worker_concurrency=20,
    worker_prefetch_multiplier=1,
    
    # 重试策略
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# 定义任务
@app.task(bind=True, max_retries=3, default_retry_delay=60)
def label_image_task(image_path: str, provider: str = 'gemini'):
    try:
        from src.ecommerce_processor.labeler import Labeler
        labeler = Labeler(provider=provider)
        result = labeler.label_single_image(image_path)
        return result
    except Exception as exc:
        raise self.retry(exc=exc)
```

**部署命令**:

```bash
# 启动Worker (多个节点并行)
celery -A celery_config worker \
  --loglevel=info \
  -Q labeling,video,reports \
  -c 20 \
  --hostname=worker1@%h \
  -n worker1.%h

# 监控任务状态
flower -A celery_config --port=5555
```

#### 2. 定时任务: APScheduler

```python
# scheduler.py
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = BackgroundScheduler()

def job_full_pipeline():
    """每天凌晨3点执行全量处理"""
    import subprocess
    subprocess.run([
        'python', 'run_pipeline.py', 'download',
        '--excel-url', os.getenv('SOURCE_EXCEL_URL'),
        '--output-dir', './materials'
    ])
    
    subprocess.run([
        'python', 'run_pipeline.py', 'label',
        '--materials-dir', './materials',
        '--provider', 'gemini',
        '--concurrency', '20'
    ])

def job_incremental_process():
    """每2小时执行增量处理"""
    subprocess.run([
        'python', 'run_pipeline.py', 'label',
        '--incremental',
        '--cache-file', './cache/labeling_cache.json'
    ])

def job_cleanup_cache():
    """每周日凌晨4点清理过期缓存"""
    subprocess.run([
        'python', 'run_pipeline.py', 'cleanup',
        '--older-than-days', '30'
    ])

# 注册定时任务
scheduler.add_job(
    job_full_pipeline,
    CronTrigger(hour=3, minute=0),  # 每天03:00
    id='full_pipeline',
    replace_existing=True
)

scheduler.add_job(
    job_incremental_process,
    CronTrigger(hour='*/2'),  # 每2小时
    id='incremental_process',
    replace_existing=True
)

scheduler.add_job(
    job_cleanup_cache,
    CronTrigger(day_of_week='sun', hour=4),  # 每周日04:00
    id='cleanup_cache',
    replace_existing=True
)

scheduler.start()
```

#### 3. 监控告警: Prometheus + Grafana

**Prometheus导出器**:

```python
# metrics_exporter.py
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# 定义指标
LABELING_TOTAL = Counter(
    'labeling_tasks_total',
    'Total number of labeling tasks',
    ['provider', 'status']
)

LABELING_LATENCY = Histogram(
    'labeling_duration_seconds',
    'Time spent on labeling',
    ['provider'],
    buckets=[1, 2, 5, 10, 30, 60, 120, 300]
)

ACTIVE_WORKERS = Gauge(
    'active_workers',
    'Number of active worker processes'
)

CACHE_SIZE = Gauge(
    'cache_size_bytes',
    'Current cache file size in bytes'
)

# 在任务中使用
def track_labeling(provider: str, duration: float, success: bool):
    LABELING_TOTAL.labels(
        provider=provider,
        status='success' if success else 'failure'
    ).inc()
    
    LABELING_LATENCY.labels(provider=provider).observe(duration)

# 启动metrics端口
start_http_server(9090)
```

**Grafana Dashboard配置示例**:

```yaml
# grafana_dashboard.json (简化版)
{
  "dashboard": {
    "title": "E-commerce Material Processor",
    "panels": [
      {
        "title": "Processing Rate (tasks/min)",
        "type": "graph",
        "targets": [{
          "expr": "rate(labeling_tasks_total[5m])",
          "legendFormat": "{{provider}} - {{status}}"
        }]
      },
      {
        "title": "Latency Distribution (P95)",
        "type": "heatmap",
        "targets": [{
          "expr": "histogram_quantile(0.95, rate(labeling_duration_seconds_bucket[5m]))"
        }]
      }
    ]
  }
}
```

---

###  成本优化建议

#### 1. AI Provider成本控制

| Provider | 价格 (每百万Token) | 日均成本 (10万图) | 优化策略 |
|----------|-------------------|------------------|----------|
| **Gemini** | $0.25 (输入) / $1.25 (输出) | ~$150-200 | 使用Batch API降低50% |
| **MiniMax** | ¥0.5/千次调用 | ~¥300-400 | 包月套餐更划算 |
| **Kimi** | ¥0.8/千次调用 | ~¥500-600 | 适合长文本场景 |
| **自建模型** | GPU硬件成本 | ~¥2000-3000/月 | 一次性投入,长期省钱 |

**混合策略 (推荐)**:

```python
# cost_optimizer.py
class CostOptimizedRouter:
    """根据预算动态选择Provider"""
    
    def __init__(self, daily_budget: float = 500.0):
        self.daily_budget = daily_budget
        self.spent_today = 0.0
        self.provider_costs = {
            'gemini': 0.002,      # $/image
            'minimax': 0.003,     # ¥/image (converted to $)
            'kimi': 0.005,        # ¥/image
            'local_model': 0.0001, # 电费折算
        }
    
    def select_provider(self, priority: str = 'normal') -> str:
        remaining = self.daily_budget - self.spent_today
        
        if priority == 'high':
            return 'gemini'  # 高优先级始终用最好的
        
        if remaining < self.daily_budget * 0.2:
            # 预算不足80%,切换到低成本方案
            return 'local_model' if self._gpu_available() else 'minimax'
        
        # 正常情况: 70% Gemini + 30% MiniMax
        return 'gemini' if random.random() < 0.7 else 'minimax'
```

#### 2. 缓存策略优化

```bash
# 分级存储方案
├─ L1: 内存缓存 (Redis) - 最近1小时的热点数据
├─ L2: 本地SSD (LanceDB) - 最近7天的频繁访问数据
└─ L3: 对象存储 (OSS/S3) - 历史归档数据,低频访问

# 成本对比:
# Redis: ¥500/月 (8GB内存)
# SSD: ¥200/月 (500GB)
# OSS: ¥50/月 (1TB,标准存储)
# 总计: ¥750/月 (vs 全部内存 ¥3000+/月)
```

---

###  安全性考虑

#### 1. API Key管理

```bash
# 生产环境禁止使用.env文件!
# 推荐方案:

# 方案A: HashiCorp Vault
export VAULT_ADDR="https://vault.company.com"
vault kv get secret/ecommerce-processor/google-api-key

# 方案B: AWS Secrets Manager
aws secretsmanager get-secret-value --secret-id ecommerce-processor-keys

# 方案C: Kubernetes Secrets
kubectl create secret generic processor-secrets \
  --from-literal=google-api-key=$GOOGLE_API_KEY \
  --from-literal=minimax-api-key=$MINIMAX_API_KEY
```

#### 2. 数据加密

```python
# 敏感字段加密存储
from cryptography.fernet import Fernet

cipher = Fernet(os.getenv('ENCRYPTION_KEY'))

def encrypt_api_key(key: str) -> str:
    return cipher.encrypt(key.encode()).decode()

def decrypt_api_key(encrypted_key: str) -> str:
    return cipher.decrypt(encrypted_key.encode()).decode()
```

---

###  部署检查清单

- [ ] 基础设施
  - [ ] 云服务器/容器集群已就绪
  - [ ] Redis/MQ消息队列已部署
  - [ ] MySQL/MongoDB数据库已创建
  - [ ] 对象存储(OSS/S3)桶已配置
  - [ ] CDN已配置(用于加速素材下载)

- [ ] 应用部署
  - [ ] Docker镜像构建并推送到Registry
  - [ ] K8s Deployment/Service YAML编写完成
  - [ ] ConfigMap/Secrets已注入敏感配置
  - [ ] HPA (Horizontal Pod Autoscaler)已配置

- [ ] 监控运维
  - [ ] Prometheus + Grafana Dashboard搭建
  - [ ] 日志收集系统 (ELK/Loki) 已接入
  - [ ] 告警规则配置 (成功率<95%,延迟>P99等)
  - [ ] 定时备份策略 (数据库+缓存每日备份)

- [ ] 安全合规
  - [ ] API Key已迁移到密钥管理系统
  - [ ] HTTPS证书已配置
  - [ ] 网络安全组规则已设置
  - [ ] 访问控制和审计日志已启用

- [ ] 测试验收
  - [ ] 压力测试通过 (目标: 10万张/天)
  - [ ] 故障恢复测试 (模拟节点宕机)
  - [ ] 数据一致性校验 (抽样对比人工标注)
  - [ ] 用户验收测试 (UAT) 通过

---

##  最佳实践总结

###  DO (推荐做法)

1. **始终使用虚拟环境隔离依赖**
2. **启用增量处理和缓存机制**
3. **配置多Provider fallback保证可用性**
4. **设置合理的并发数和重试策略**
5. **定期审查"其他"标签,优化分类体系**
6. **监控关键指标,建立告警机制**
7. **版本锁定依赖包 (requirements-lock.txt)**

###  DON'T (避免的做法)

1. **不要在生产环境硬编码API Key**
2. **不要忽略低置信度样本的人工审核**
3. **不要设置过高的并发导致触发Rate Limit**
4. **不要跳过环境检查直接运行**
5. **不要忘记定期备份缓存和配置**

---

**文档版本**: v2.3.0  
**最后更新**: 2026-07-11  
**适用Skill版本**: ecommerce-multimodal-material-processor >= 2.0.0
