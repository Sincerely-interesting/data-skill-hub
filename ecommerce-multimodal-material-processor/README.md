<div align="center">

# ecommerce-multimodal-material-processor

>  电商多模态素材智能处理Pipeline | AI驱动的端到端内容工作流

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Status: Production Ready](https://img.shields.io/badge/Status-Production%20Ready-brightgreen.svg)]()

**一个生产级的电商素材处理工具链,将分散在Excel、共享盘和文件夹中的图片/视频内容,转化为可打标、可检索、可导出、可追溯的结构化业务资产。**

</div>

---

##  核心特性

###  一键式部署
- **零配置启动**: `pip install -r requirements.txt && python run_pipeline.py doctor`
- **CLI统一入口**: 5个核心命令(doctor/download/label/archive/export)

###  多Provider支持
- **8种AI Provider**: Gemini/MiniMax/Kimi/MINICPM/Paddle等主流视觉模型
- **智能路由**: JSON配置 + 自动fallback机制
- **灵活切换**: 10s/20s/30s/60s多档延迟配置
- **成本优化**: 按需选择,平衡质量与成本

###  多源输入
- Excel/CSV URL列表
- 本地目录递归扫描
- SMB共享目录挂载

###  多格式输出
- Markdown详细报告
- Excel结构化汇总表(带公式)
- JSON缓存数据
- 原子写入保证

---

##  目录结构

```
ecommerce-multimodal-material-processor/
├── src/ecommerce_processor/          # 核心处理模块
│   ├── downloader.py                 # 素材下载 + 并发控制
│   ├── labeler.py                    # AI标注引擎(多Provider)
│   ├── archiver.py                   # 归档报告生成
│   ├── exporter.py                   # 导出服务
│   ├── video_utils.py                # 视频处理工具
│   ├── config.py                     # 配置管理(Pydantic)
│   └── deps_checker.py               # 环境依赖检查
├── run_pipeline.py                   # 统一CLI入口(5个子命令)
├── requirements.txt                  # Python依赖
├── .env.example                      # 环境变量模板
├── examples/
│   └── demo-conversation.md          # 使用示例对话
├── references/
│   ├── architecture-guide.md         # 架构设计文档
│   ├── mcp-implementation-guide.md   # MCP协议实现指南
│   ├── auto-collection-roadmap.md    # 自动采集路线图
│   └── labeling-criteria.md          # 标注标准规范
├── SKILL.md                          # Skill定义文件(核心)
├── README.md                         # 项目说明文档
└── LICENSE                           # MIT许可证
```

---

##  快速开始

### Step 1: 环境准备

```bash
# 克隆项目
git clone <your-repo-url>
cd ecommerce-multimodal-material-processor

# 创建虚拟环境(推荐)
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### Step 2: 配置API Key

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件,至少配置一个Provider的API Key
# 例如:
GEMINI_API_KEY=your_gemini_api_key_here
# 或
MINIMAX_API_KEY=your_minimax_api_key_here
```

**支持的Provider**:

| Provider | 环境变量 | 获取地址 |
|----------|----------|----------|
| Gemini | `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) |
| MiniMax | `MINMAX_API_KEY` | [MiniMax开放平台](https://platform.minimaxi.com/) |
| Kimi | `KIMI_API_KEY` | [Moonshot AI](https://platform.moonshot.cn/) |
| MINICPM | `MINICPM_API_KEY` | [MiniCPM](https://www.minicpm.info/) |
| Paddle | `PADDLE_API_KEY` | [百度飞桨](https://www.paddlepaddle.org.cn/) |

### Step 3: 环境检查

```bash
python run_pipeline.py doctor
```

**预期输出**:
```
============================================================
 环境预检 (Doctor)
============================================================

 Python: 3.12.3
 核心依赖: openai / pandas / tqdm / opencv-python
 ffmpeg: /usr/bin/ffmpeg (视频处理就绪)
 API Keys:
    gemini: 已配置
    minmax: 未配置 (可选)
 kimi: 未配置 (可选)
 输出目录权限: 正常
 缓存目录: ./cache (已创建)

 环境检查通过! 可以开始处理素材。
```

### Step 4: 完整流程示例

```bash
# 1. 从Excel下载素材
python run_pipeline.py download \
  --excel materials.xlsx \
  --output downloaded_materials \
  --workers 5

# 2. 使用Gemini进行AI打标
python run_pipeline.py label \
  --provider gemini \
  --materials-dir downloaded_materials \
  --batch-size 5 \
  --batch-delay 20

# 3. 生成归档报告(Markdown)
python run_pipeline.py archive \
  --materials-dir downloaded_materials

# 4. 导出Excel汇总表
python run_pipeline.py export-cache \
  --format excel \
  --output excel_exports
```

**或者使用本地目录模式**(跳过下载步骤):

```bash
# 直接扫描本地目录并处理
python run_pipeline.py download --local-dir /path/to/your/materials
python run_pipeline.py label --provider gemini --materials-dir downloaded_materials
python run_pipeline.py export-cache --format excel
```

---

##  详细使用指南

### 命令参考

#### `doctor` - 环境诊断

```bash
python run_pipeline.py doctor
```

检查项:
- Python版本(>=3.10)
- 必要依赖包
- ffmpeg可用性
- API Key配置
- 目录权限

---

#### `download` - 素材获取

**从Excel/CSV下载**:
```bash
python run_pipeline.py download \
  --excel materials.xlsx \          # Excel或CSV文件路径
  --output downloaded_materials \   # 输出目录
  --workers 5 \                     # 并发下载数(默认5)
  --sample 100                      # 仅下载前N个(用于测试)
```

**扫描本地目录**:
```bash
python run_pipeline.py download \
  --local-dir /path/to/materials    # 本地素材目录路径
```

**支持的Excel格式**:
- 列名: `material_id`, `url`, `image_url`, `video_url`(自动识别)
- 文件格式: `.xlsx`, `.xls`, `.csv`

---

#### `label` - AI智能标注

```bash
python run_pipeline.py label \
  --provider gemini \               # 选择AI Provider
  --materials-dir downloaded_materials \  # 素材目录
  --batch-size 5 \                  # 批次大小(默认5)
  --batch-delay 20 \                # 批次间隔秒数(默认20)
  --workers 5 \                     # 并发worker数(默认5)
  --max-retries 5 \                 # 最大重试次数(默认5)
  --output labeling_results.json    # 输出缓存文件名
```

**Provider选择建议**:

| 场景 | 推荐Provider | 原因 |
|------|-------------|------|
| 大批量快速处理 | minicpm | 速度快、成本低 |
| 高精度要求 | gemini | 视觉理解能力强 |
| 中文场景 | minimax/kimi | 中文优化好 |
| 成本敏感 | paddle | 性价比高 |

---

#### `archive` - 归档报告生成

```bash
python run_pipeline.py archive \
  --materials-dir downloaded_materials \
  --provider minicpm \              # 用于补充描述的Provider
  --output material_archives        # 输出目录(默认material_archives)
```

生成的Markdown报告包含:
- 素材基本信息(路径、大小、分辨率、时长)
- 标注结果与置信度
- 处理元数据(Provider、模型、时间戳)
- 详细描述文本

---

#### `export-cache` - 结果导出

```bash
# 导出为Excel
python run_pipeline.py export-cache \
  --format excel \
  --output excel_exports \
  --cache-file labeling_results.json

# 导出为JSON
python run_pipeline.py export-cache \
  --format json \
  --output json_exports
```

**Excel输出列**:
- material_id, file_path, file_type
- primary_label, confidence, alternative_labels
- provider, model, processing_time
- image_resolution, video_duration(如适用)
- metadata(扩展字段)

---

##  业务标签体系

本工具针对电商内容场景设计了**8种业务标签**:

| 标签ID | 标签名称 | 描述 | 典型场景 |
|--------|----------|------|----------|
| `celebrity_wear` | 明星穿搭 | 明星人物纯背景镜头 | 明星代言、代言人特写 |
| `outfit_core` | 穿搭精选(核心) | 核心产品空镜拍摄 | 主推款产品展示 |
| `outfit_secondary` | 穿搭精选(次要) | 常规产品空镜 | 常规款式展示 |
| `single_display` | 单品展示(上脚) | 单件商品上身展示 | 鞋类上脚图、服装穿搭 |
| `creative_still` | 创意静物 | 艺术化静物构图 | 创意拍摄、概念片 |
| `still_display` | 静物展示 | 标准静物摆拍 | 产品白底图、细节图 |
| `performance_test` | 性能测试 | 产品功能性测试画面 | 运动测试、耐磨测试 |
| `other` | 其他 | 无法归类的素材 | 特殊case、待人工确认 |

**质量控制规则**:
-  "其他"标签占比 > 20% → 触发预警
-  建议各标签占比相对均衡
-  定期抽检验证准确率

---

##  高级配置

### 自定义参数

通过环境变量或命令行参数调整:

```bash
# 方式1: 环境变量
export DEFAULT_BATCH_SIZE=10
export DEFAULT_BATCH_DELAY=30
export MAX_RETRIES=7

# 方式2: 命令行参数(优先级更高)
python run_pipeline.py label --batch-size 10 --batch-delay 30
```

**完整参数列表**:

| 参数 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| batch_size | DEFAULT_BATCH_SIZE | 5 | 每批处理的素材数量 |
| batch_delay | DEFAULT_BATCH_DELAY | 20.0 | 批次间等待时间(秒) |
| workers | DEFAULT_WORKERS | 5 | 并发worker数量 |
| max_retries | MAX_RETRIES | 5 | 最大重试次数 |
| retry_base_delay | RETRY_BASE_DELAY | 10 | 重试基础延迟(秒) |
| quota_wait_hours | QUOTA_WAIT_HOURS | 5 | 配额耗尽等待时间(小时) |
| image_max_size | IMAGE_MAX_SIZE | 768 | 图片最大边长(px) |
| image_quality | IMAGE_QUALITY | 75 | JPEG压缩质量(0-100) |

---

### 视频处理配置

```bash
# 启用音频提取与转写(需要ffmpeg和whisper)
export EXTRACT_AUDIO=true
export USE_WHISPER=true

# 视频抽帧参数
export VIDEO_FPS=1              # 抽帧频率(每秒1帧)
export MAX_FRAMES=60            # 最大保留帧数
export AUDIO_FORMAT=mp3         # 音频输出格式
```

**依赖安装**:
```bash
# whisper(可选,用于音频转写)
pip install openai-whisper

# 或者使用 faster-whisper(更快,推荐)
pip install faster-whisper
```

---

### SMB共享目录同步(可选)

如果需要将结果同步到SMB共享目录:

```bash
# .env 配置
SMB_SERVER=dewu-server
SMB_SHARE=materials
SMB_USER=your_username
SMB_PASS=your_password

# 执行同步
python run_pipeline.py sync-smb \
  --source material_archives \
  --dest "\\dewu-server\\materials\\labeled" \
  --include "*.md,*.json"
```

**注意**: Windows系统可直接使用UNC路径;Linux/macOS需要mount smbfs。

---

##  性能优化建议

### 大批量处理(500+素材)

```bash
# 优化方案1: 使用minicpm(速度快)
python run_pipeline.py label \
  --provider minicpm \
  --batch-size 10 \
  --workers 10 \
  --batch-delay 15

# 优化方案2: 分批并行(多终端)
# 终端1:
python run_pipeline.py label --sample 0:250 --provider gemini
# 终端2:
python run_pipeline.py label --sample 250:500 --provider gemini

# 优化方案3: 夜间运行(避免高峰期)
nohup python run_pipeline.py label --provider gemini > log.txt 2>&1 &
```

### 成本控制策略

| 策略 | 适用场景 | 预计节省 |
|------|----------|----------|
| 先用minicpm初筛,再用gemini复检"其他" | 大批量+高精度需求 | ~40% |
| 降低图片分辨率(512px) | 对精度要求不高的场景 | ~30% |
| 增大batch_size,减少API调用次数 | 成本敏感型任务 | ~20% |
| 利用缓存机制,避免重复标注 | 增量更新场景 | ~50%+ |

---

##  故障排查

### 常见问题及解决方案

详见 [SKILL.md](./SKILL.md) 的**故障排查指南**章节,涵盖:
- ffmpeg缺失
- API限流(529错误)
- 标签分布异常
- 视频编码不支持
- Excel文件被占用
- SMB同步失败
- 处理速度慢

**快速诊断命令**:
```bash
# 完整环境检查
python run_pipeline.py doctor

# 测试单个Provider连通性
python test_deps.py --provider gemini

# 验证安装完整性
python verify_installation.py
```

---

##  生产部署建议

### 服务器配置要求

| 规格 | 最低配置 | 推荐配置 |
|------|----------|----------|
| CPU | 4核 | 8核+ |
| 内存 | 8GB | 16GB+ |
| 存储 | 50GB SSD | 200GB+ SSD |
| 网络 | 10Mbps | 100Mbps+ |
| Python | 3.10+ | 3.12+ |

### 监控与日志

```bash
# 日志位置
logs/ecommerce_processor_{date}.log

# 日志级别调整
export LOG_LEVEL=DEBUG  # DEBUG/INFO/WARNING/ERROR

# 关键监控指标
- 处理成功率(应>95%)
- "其他"标签占比(应<20%)
- 平均处理延时
- API调用成本
```

### 定时任务示例(Linux crontab)

```bash
# 每天凌晨2点执行全量打标
0 2 * * * cd /path/to/project && source venv/bin/activate && python run_pipeline.py label --provider gemini --materials-dir /data/materials >> /var/log/ecommerce_processor.log 2>&1

# 每周日3点导出Excel报告
0 3 * * 0 cd /path/to/project && source venv/bin/activate && python run_pipeline.py export-cache --format excel >> /var/log/ecommerce_export.log 2>&1
```

---

##  贡献指南

### 开发环境搭建

```bash
# Fork并克隆仓库
git clone https://github.com/your-username/ecommerce-multimodal-material-processor.git
cd ecommerce-multimodal-material-processor

# 创建特性分支
git checkout -b feature/new-provider

# 安装开发依赖
pip install -r requirements.txt
pip install pytest black flake8

# 运行测试
pytest tests/

# 代码格式化
black src/
flake8 src/
```

### 提交规范

- feat: 新功能
- fix: Bug修复
- docs: 文档更新
- style: 代码格式调整
- refactor: 重构
- test: 测试相关
- chore: 构建/工具链

### Pull Request流程

1. Fork本项目
2. 创建特性分支(`git checkout -b feature/amazing-feature`)
3. 提交更改(`git commit -m 'Add amazing feature'`)
4. 推送到分支(`git push origin feature/amazing-feature`)
5. 创建Pull Request

---

##  许可证

本项目采用 [MIT License](./LICENSE) 开源协议。

```
MIT License

Copyright (c) 2026 AI Content Realize Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
```

---

##  致谢

- **AI Providers**: Google(Gemini), MiniMax, Moonshot(Kimi), MiniCPM, Baidu(Paddle)
- **开源社区**: OpenAI(httpx), HuggingFace(sentence-transformers), LanceDB
- **灵感来源**: [ai-content-realize](https://github.com/your-org/ai-content-realize) 项目

---

##  联系方式

- **Issue反馈**: [GitHub Issues](https://github.com/your-org/ecommerce-multimodal-material-processor/issues)
- **讨论交流**: [GitHub Discussions](https://github.com/your-org/ecommerce-multimodal-material-processor/discussions)
- **邮件联系**: team@example.com

---

<div align="center">

** 如果这个项目对你有帮助,请给一个Star支持! **

Made with  by AI Content Realize Team

</div>
