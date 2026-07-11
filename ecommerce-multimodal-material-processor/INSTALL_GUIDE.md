# 📦 安装指南 (Installation Guide)

> **完整的电商多模态素材处理Pipeline安装与配置手册** | 从零开始到生产就绪

---

## ✅ 前置要求检查清单

在开始安装之前,请确保您的系统满足以下所有要求:

### 系统环境

| 组件 | 最低版本 | 推荐版本 | 检查命令 |
|------|----------|----------|----------|
| **Python** | 3.10+ | 3.11/3.12 | `python --version` |
| **pip** | >=23.0 | 最新版 | `pip --version` |
| **操作系统** | Windows 10+/macOS 12+/Ubuntu 20.04+ | - | - |
| **内存** | 8GB RAM | 16GB+ RAM | 系统信息 |
| **磁盘空间** | 5GB可用空间 | 20GB+ (含模型缓存) | `df -h` |

### Python版本验证

```bash
# 检查Python版本(需要3.10或更高)
python --version
# 输出应为: Python 3.10.x 或更高版本

# 如果版本不符合要求:
# Windows: 从 python.org 下载最新版
# macOS: brew install python@3.11
# Ubuntu: sudo apt install python3.11 python3.11-venv
```

### 网络连接

- ✅ 可访问 PyPI (pypi.org) 用于下载依赖包
- ✅ 可访问 AI Provider API端点(Google/OpenAI/MiniMax等)
- ⚠️ 如果使用代理,请确保已正确配置 `HTTP_PROXY` 和 `HTTPS_PROXY`

---

## 🚀 快速安装 (3步完成)

### 步骤1: 克隆项目并进入目录

```bash
# 克隆仓库(如果是从Git获取)
git clone <repository-url>
cd ecommerce-multimodal-material-processor

# 或者如果您已经有项目代码
cd /path/to/ecommerce-multimodal-material-processor
```

### 步骤2: 创建虚拟环境(强烈推荐)

```bash
# 创建虚拟环境(推荐Python 3.11)
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 验证激活成功(命令行前应显示(venv))
which python
```

**为什么要使用虚拟环境?**
- 🔒 避免污染系统Python环境
- 🎯 确保依赖版本一致性
- 🔄 方便项目迁移和部署
- 🛡️ 隔离不同项目的依赖冲突

### 步骤3: 安装核心依赖

```bash
# 安装所有必需的Python包
pip install -r requirements.txt

# 预计耗时: 2-5分钟(取决于网络速度)
```

**如果遇到网络问题(国内用户):**

```bash
# 使用清华镜像源加速
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或者使用阿里云镜像
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
```

---

## ⚙️ 详细安装指南

### 方法A: 标准安装(推荐)

适用于大多数用户,包含完整的功能支持。

#### 1. 安装基础依赖

```bash
pip install \
  openai>=1.30.0 \
  pandas>=2.0.0 \
  openpyxl>=3.1.0 \
  tqdm>=4.66.0 \
  Pillow>=10.0.0 \
  opencv-python>=4.8.0 \
  python-dotenv>=1.0.0 \
  pydantic>=2.5.0 \
  pydantic-settings>=2.1.0 \
  loguru>=0.7.0 \
  httpx>=0.25.0 \
  aiofiles>=23.2.0 \
  asyncio-pool>=0.6.0 \
  xlrd>=2.0.1 \
  ffmpeg-python>=0.2.0
```

#### 2. 安装AI Provider SDK(按需选择)

根据您计划使用的AI Provider安装对应的SDK:

##### Gemini (Google)

```bash
# Google Generative AI
pip install google-generativeai>=0.5.0

# 配置API Key
export GOOGLE_API_KEY="your-api-key-here"
```

##### MiniMax

```bash
# MiniMax官方SDK(如可用)
# pip install minimax-sdk

# 或者通过OpenAI兼容接口使用
# 无需额外安装,使用openai库即可
```

##### Kimi (Moonshot AI)

```bash
# Moonshot AI SDK
pip install openai  # Kimi使用OpenAI兼容接口

# 配置
export MOONSHOT_API_KEY="your-moonshot-key"
```

##### MINICPM

```bash
# 本地模型运行时
pip install torch>=2.0.0 torchvision>=0.15.0
pip install transformers>=4.36.0 accelerate>=0.25.0

# 注意: MINICPM可能需要额外的模型权重下载
# 请参考MINICPM官方文档
```

##### PaddlePaddle

```bash
# PaddlePaddle框架
pip install paddlepaddle>=2.5.0
pip install paddlenlp>=2.6.0

# GPU版本(如果有NVIDIA GPU)
# pip install paddlepaddle-gpu>=2.5.0
```

##### 其他Provider

```bash
# OpenAI GPT-4V
# 已包含在openai包中

# Azure OpenAI
pip install azure-identity>=1.15.0

# Anthropic Claude
pip install anthropic>=0.18.0

# 本地Ollama
# 无需额外安装,通过HTTP API调用
```

#### 3. 安装可选依赖(增强功能)

```bash
# 向量数据库(LanceDB)
pip install lancedb>=0.9.0

# 定时任务(APScheduler)
pip install APScheduler>=3.10.0

# Webhook服务(FastAPI)
pip install fastapi>=0.104.0 uvicorn>=0.24.0

# 分布式任务队列(Celery)
pip install celery>=5.3.0 redis>=5.0.0

# 监控和指标(Prometheus)
pip install prometheus-client>=0.19.0
```

### 方法B: 最小化安装

仅安装最基础的依赖,适合快速测试或资源受限的环境。

```bash
# 仅安装核心运行时依赖
pip install \
  pandas openpyxl Pillow \
  opencv-python python-dotenv \
  pydantic loguru httpx \
  tqdm aiofiles

# 总大小约: ~150MB
# 功能限制: 只能使用外部API Provider,无法使用本地模型
```

### 方法C: 完整安装(生产环境)

包含所有功能和可选组件。

```bash
# 1. 安装requirements.txt中的所有依赖
pip install -r requirements.txt

# 2. 安装开发工具(可选)
pip install -r dev-requirements.txt

# 3. 安装视频处理工具
# Windows:
#   下载FFmpeg: https://ffmpeg.org/download.html
#   添加到PATH环境变量
# macOS:
brew install ffmpeg
# Ubuntu:
sudo apt install ffmpeg

# 4. 验证安装完整性
python run_pipeline.py doctor
```

---

## 🔧 环境配置

### 1. 创建环境变量文件

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑.env文件
# Windows: notepad .env
# macOS/Linux: nano .env 或 vim .env
```

### 2. 配置内容详解

```ini
# ============================================
# 核心配置 (Core Configuration)
# ============================================

# 日志级别: DEBUG/INFO/WARNING/ERROR
LOG_LEVEL=INFO

# 最大并发下载数
MAX_DOWNLOAD_CONCURRENCY=5

# 最大并发标注任务数
MAX_LABEL_CONCURRENCY=3

# 缓存目录路径
CACHE_DIR=./cache

# 输出目录路径
OUTPUT_DIR=./output

# ============================================
# AI Provider 配置
# ============================================

# --- Gemini (Google) ---
GOOGLE_API_KEY=your-google-api-key-here
GEMINI_MODEL=gemini-1.5-pro
GEMINI_TIMEOUT=30

# --- MiniMax ---
MINIMAX_API_KEY=your-minimax-api-key-here
MINIMAX_GROUP_ID=your-group-id
MINIMAX_MODEL=abab6.5s-chat
MINIMAX_BASE_URL=https://api.minimax.chat/v1

# --- Kimi (Moonshot) ---
MOONSHOT_API_KEY=your-moonshot-api-key-here
KIMI_MODEL=moonshot-v1-128k
KIMI_TIMEOUT=60

# --- MINICPM (本地模型) ---
MINICPM_MODEL_PATH=/path/to/minicpm-model
MINICPM_DEVICE=cuda  # cpu/cuda/mps
MINICPM_MAX_LENGTH=2048

# --- PaddlePaddle ---
PADDLE_USE_GPU=false
PADDLE_NUM_THREADS=4
PADDLE_MODEL_NAME=pp-ocrv4

# --- OpenAI (GPT-4V) ---
OPENAI_API_KEY=your-openai-api-key-here
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=https://api.openai.com/v1

# 默认使用的Provider(优先级最高)
DEFAULT_PROVIDER=gemini

# ============================================
# 功能开关 (Feature Flags)
# ============================================

# 启用智能路由(自动选择最佳Provider)
ENABLE_SMART_ROUTING=true

# 启用自动fallback(当主Provider失败时切换)
ENABLE_AUTO_FALLBACK=true

# 启用主动学习(收集反馈优化模型)
ENABLE_ACTIVE_LEARNING=false

# 启用向量检索功能
ENABLE_VECTOR_SEARCH=false

# 启用定时任务调度
ENABLE_SCHEDULER=false

# ============================================
# 高级配置 (Advanced Settings)
# ============================================

# 重试次数
MAX_RETRIES=3

# 重试间隔(秒)
RETRY_DELAY=5

# 请求超时时间(秒)
REQUEST_TIMEOUT=120

# 文件大小限制(MB)
MAX_FILE_SIZE=50

# 支持的图片格式
SUPPORTED_IMAGE_FORMATS=jpg,jpeg,png,gif,bmp,webp,tiff

# 支持的视频格式
SUPPORTED_VIDEO_FORMATS=mp4,mov,avi,mkv,wmv,flv

# ============================================
# 监控与告警 (Monitoring)
# ============================================

# 启用Prometheus指标导出
ENABLE_METRICS_EXPORT=false
METRICS_PORT=9090

# 告警邮箱(可选)
ALERT_EMAIL=admin@example.com

# ============================================
# 代理设置 (Proxy Configuration)
# ============================================
# HTTP_PROXY=http://127.0.0.1:7890
# HTTPS_PROXY=http://127.0.0.1:7890
```

### 3. 敏感信息保护

⚠️ **重要安全提醒**:

```bash
# 1. 确保.gitignore中包含.env
echo ".env" >> .gitignore

# 2. 不要将含有真实API Key的.env文件提交到Git
git status  # 确认.env不在暂存区

# 3. 生产环境建议使用密钥管理服务
# AWS Secrets Manager / HashiCorp Vault / etc.
```

---

## ✅ 安装验证

### 运行环境检查

```bash
# 执行完整的健康检查
python run_pipeline.py doctor
```

**预期输出示例**:

```
╔══════════════════════════════════════════════════════════════╗
║         🏥 E-commerce Material Processor - Doctor Report       ║
╠══════════════════════════════════════════════════════════════╣
║ ✅ Python Version: 3.11.5 (OK)                                ║
║ ✅ pip Version: 24.0 (OK)                                    ║
║ ✅ Virtual Environment: Active (venv)                         ║
║                                                              ║
║ 📦 Dependencies Check:                                       ║
║   ✅ pandas 2.2.0                                            ║
║   ✅ openai 1.30.0                                           ║
║   ✅ Pillow 10.2.0                                           ║
║   ✅ opencv-python 4.9.0                                     ║
║   ✅ pydantic 2.6.0                                          ║
║   ⚠️ lancedb Not Installed (Optional)                        ║
║                                                              ║
║ 🔌 API Providers Status:                                     ║
║   ✅ GOOGLE_API_KEY: Configured                              ║
║   ❌ MINIMAX_API_KEY: Missing                                ║
║   ⚠️ MOONSHOT_API_KEY: Not Configured                       ║
║                                                              ║
║ 📂 Directory Structure:                                      ║
║   ✅ ./cache: Exists                                         ║
║   ✅ ./output: Exists                                        ║
║   ✅ ./materials: Ready                                      ║
║                                                              ║
║ 💾 Disk Space: 45.2GB Available (✅ Sufficient)              ║
║ 🧵 System Resources: 16GB RAM, 8 CPUs (✅ Good)              ║
╚══════════════════════════════════════════════════════════════╝

🎉 Overall Status: HEALTHY (7/10 checks passed)
⚠️  Warnings: 2 (Non-critical, can proceed)
❌ Errors: 1 (MINIMAX_API_KEY required for MiniMax provider)
```

### 功能测试

```bash
# 测试基础下载功能
python run_pipeline.py download --excel-url "https://example.com/test.xlsx" --dry-run

# 测试标注功能(单张图片)
python run_pipeline.py label --image-path ./test_image.jpg --provider gemini --dry-run

# 测试归档报告生成
python run_pipeline.py archive --cache-file labeling_cache.json --dry-run
```

---

## 🐛 常见问题排查 (Troubleshooting)

### 问题1: pip安装超时

**症状**: `pip install` 命令长时间无响应或报错 `Read timed out`

**解决方案**:

```bash
# 使用国内镜像源
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 或临时指定镜像
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn

# 增加超时时间
pip install --default-timeout=1000 -r requirements.txt
```

### 问题2: Python版本不兼容

**症状**: `SyntaxError` 或 `ModuleNotFoundError` 关于某些模块

**解决方案**:

```bash
# 检查当前版本
python --version

# 如果低于3.10,需要升级
# Windows: 重新安装Python
# macOS: brew upgrade python
# Ubuntu: 
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11
```

### 问题3: FFmpeg未找到

**症状**: 运行视频处理时报错 `ffmpeg not found in PATH`

**解决方案**:

```bash
# Windows:
# 1. 下载: https://www.gyan.dev/ffmpeg/builds/
# 2. 解压到 C:\ffmpeg
# 3. 添加环境变量:
setx PATH "%PATH%;C:\ffmpeg\bin"
# 4. 重启终端验证
ffmpeg -version

# macOS:
brew install ffmpeg

# Ubuntu:
sudo apt update
sudo apt install ffmpeg
```

### 问题4: 权限错误 (Permission Denied)

**症状**: 安装时报错 `PermissionError: [Errno 13] Permission denied`

**解决方案**:

```bash
# 使用用户级安装(无需sudo)
pip install --user -r requirements.txt

# 或使用虚拟环境(推荐)
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 问题5: SSL证书验证失败

**症状**: `SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]`

**解决方案**:

```bash
# 方法1: 更新certifi
pip install --upgrade certifi

# 方法2: 信任主机(不推荐用于生产环境)
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

# 方法3: 如果使用公司代理,可能需要配置CA证书
# 设置环境变量:
# REQUESTS_CA_BUNDLE=/path/to/ca-bundle.crt
# SSL_CERT_FILE=/path/to/ca-bundle.crt
```

### 问题6: 内存不足 (OOM)

**症状**: 运行本地模型(MINICPM/Paddle)时程序崩溃或极慢

**解决方案**:

```bash
# 1. 减少批处理大小
# 在config.json中设置:
# "batch_size": 1

# 2. 使用CPU模式而非GPU(如果显存不足)
# .env文件中:
# MINICPM_DEVICE=cpu
# PADDLE_USE_GPU=false

# 3. 增加系统交换空间(swap)
# Linux:
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 4. 关闭其他占用内存的程序
```

### 问题7: API Key无效或配额用尽

**症状**: `401 Unauthorized` 或 `Quota exceeded` 错误

**解决方案**:

```bash
# 1. 检查API Key是否正确(无多余空格)
# 2. 检查账户余额/配额
# 3. 确认API Key有对应模型的访问权限
# 4. 测试API连通性:
curl -H "Authorization: Bearer $GOOGLE_API_KEY" \
  https://generativelanguage.googleapis.com/v1beta/models
```

---

## 🔄 升级指南

### 从旧版本升级

```bash
# 1. 备份当前配置和数据
cp .env .env.backup
cp -r cache cache_backup

# 2. 拉取最新代码
git pull origin main

# 3. 更新依赖
pip install --upgrade -r requirements.txt

# 4. 迁移数据(如有数据库变更)
python migrate.py --from-version=old-version --to-version=new-version

# 5. 验证升级
python run_pipeline.py doctor
```

### 依赖更新

```bash
# 更新单个包
pip install --upgrade package-name

# 更新所有过时的包
pip list --outdated
pip list --outdated --format=json | \
  python -c "import json,sys; packages=json.load(sys.stdin); \
  print(' '.join([p['name'] for p in packages]))" | \
  xargs pip install --upgrade

# 锁定当前版本(用于生产环境 reproducible build)
pip freeze > requirements-lock.txt
pip install -r requirements-lock.txt
```

---

## 🏗️ 生产环境部署

### Docker部署(推荐)

**Dockerfile**:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建非root用户
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# 暴露端口(如需Web界面)
EXPOSE 8000

# 启动命令
CMD ["python", "run_pipeline.py", "scheduler", "--mode=daemon"]
```

**docker-compose.yml**:

```yaml
version: '3.8'

services:
  processor:
    build: .
    env_file:
      - .env.production
    volumes:
      - ./data:/app/data
      - ./cache:/app/cache
      - ./output:/app/output
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - TZ=Asia/Shanghai
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  redis_data:
```

**部署命令**:

```bash
# 构建镜像
docker-compose build

# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f processor

# 停止服务
docker-compose down
```

### systemd服务(Linux)

创建 `/etc/systemd/system/ecommerce-processor.service`:

```ini
[Unit]
Description=E-commerce Multimodal Material Processor
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/ecommerce-multimodal-material-processor
ExecStart=/opt/venv/bin/python run_pipeline.py scheduler --mode=daemon
Restart=always
RestartSec=5
EnvironmentFile=/opt/.env

[Install]
WantedBy=multi-user.target
```

```bash
# 启用开机自启
sudo systemctl enable ecommerce-processor
sudo systemctl start ecommerce-processor

# 查看状态
sudo systemctl status ecommerce-processor

# 查看日志
journalctl -u ecommerce-processor -f
```

### Nginx反向代理(可选)

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 文件上传大小限制
    client_max_body_size 100M;
}
```

---

## 📊 性能优化建议

### 硬件配置推荐

| 场景 | CPU | 内存 | GPU | 存储 | 并发数 |
|------|-----|------|-----|------|--------|
| **个人使用** | 4核 | 8GB | 不需要 | SSD 100GB | 3-5 |
| **小型团队** | 8核 | 16GB | GTX 1660+ | SSD 500GB | 10-20 |
| **企业生产** | 16核+ | 32GB+ | RTX 3090/A100 | NVMe 1TB+ | 50-100+ |

### 软件层面优化

```bash
# 1. 使用uvloop替代asyncio(性能提升2-5倍)
pip install uvloop
# 在代码入口添加:
import uvloop
uvloop.install()

# 2. 启用JIT编译(对于NumPy/Pandas重度使用)
# 环境变量:
export NUMPY_EXPERIMENTAL_ARRAY_FUNCTION=1

# 3. 调整文件监控(inotify)限制
# Linux:
echo fs.inotify.max_user_watches=524288 | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# 4. 使用SSD存储缓存和输出
# 确保CACHE_DIR和OUTPUT_DIR在SSD分区上
```

---

## 📝 安装后检查清单

安装完成后,请逐项确认:

- [ ] Python版本 >= 3.10
- [ ] 虚拟环境已创建并激活
- [ ] 所有依赖安装成功(`pip list`无报错)
- [ ] `.env`文件已创建且至少配置了1个Provider的API Key
- [ ] FFmpeg已安装并可执行(`ffmpeg -version`)
- [ ] 必要的目录结构已创建(cache/, output/, materials/)
- [ ] `python run_pipeline.py doctor` 通过所有关键检查
- [ ] 成功运行了至少1次dry-run测试
- [ ] 了解基本的CLI命令用法
- [ ] 已阅读README.md了解完整功能
- [ ] (生产环境) 已配置日志轮转和备份策略
- [ ] (生产环境) 已设置监控和告警

---

## 🆘 获取帮助

### 文档资源

- 📘 **完整README**: [README.md](./README.md)
- 🛠️ **SKILL定义**: [SKILL.md](./SKILL.md)
- 🏗️ **架构设计**: [references/architecture-guide.md](./references/architecture-guide.md)
- 🔌 **MCP协议**: [references/mcp-implementation-guide.md](./references/mcp-implementation-guide.md)
- 🗺️ **发展路线图**: [references/auto-collection-roadmap.md](./references/auto-collection-roadmap.md)
- 🏷️ **标注标准**: [references/labeling-criteria.md](./references/labeling-criteria.md)

### 社区支持

- **GitHub Issues**: [提交Bug报告或功能请求](https://github.com/your-org/ecommerce-multimodal-material-processor/issues)
- **讨论区**: [使用问题和最佳实践](https://github.com/your-org/ecommerce-multimodal-material-processor/discussions)
- **Wiki**: [详细教程和FAQ](https://github.com/your-org/ecommerce-multimodal-material-processor/wiki)

### 紧急联系

- **技术支持邮箱**: support@example.com
- **Slack频道**: #ecommerce-processor-help

---

**最后更新**: 2026-07-11  
**适用版本**: v2.3.0+  
**维护团队**: AI Content Realize Team
