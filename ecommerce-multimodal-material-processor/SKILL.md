---
name: ecommerce-multimodal-material-processor
description: "电商多模态素材处理Pipeline。支持从Excel/本地目录下载素材、使用多种AI Provider进行智能标注分类、自动归档生成Markdown报告、导出Excel/JSON/缓存。注：向量检索服务与REST API为规划中功能（当前仅提供CLI离线处理，api_service.py为占位实现），暂未提供检索能力。当用户需要处理电商素材(图片/视频)的批量打标、分类、归档、导出时调用此Skill。"
---

# 电商多模态素材处理器 (E-commerce Multimodal Material Processor)

Use this skill when the task is not just "run a labeling script", but "design, execute, and troubleshoot an end-to-end multimodal material processing pipeline for e-commerce content."

## 快速开始使用此 Skill

> **重要提示**: 此 skill **不是简单的标注脚本**,而是一个**完整的端到端处理工具链**

### 安装步骤 (3步)

```bash
# Step 1: 安装依赖
pip install -r requirements.txt

# Step 2: 配置环境变量
cp .env.example .env
# 编辑 .env 文件,至少配置一个 Provider 的 API Key

# Step 3: 环境检查
python run_pipeline.py doctor
```

### 环境要求

- **Python**: >= 3.10
- **ffmpeg**: 视频处理必需(用于抽帧),需在系统PATH中
- **API Key**: 至少配置一个 AI Provider 的 API Key(详见 `.env.example`)

### 核心依赖

- `sentence-transformers` + `lance`: 向量检索引擎（规划中，尚未实现）
- `fastapi` + `uvicorn`: 检索API服务（规划中，api_service.py 当前为占位实现）

## 能力边界

- **支持的素材来源**: Excel/CSV URL列表、本地文件夹扫描、SMB共享目录挂载
- **8种 AI Provider**: Gemini / MiniMax(标准版) / MiniMax(MCP协议) / Kimi / Kimi-Coding / MINICPM / Paddle / 自定义端点(通过YesCode代理)
- **支持的业务标签**: 明星穿搭/穿搭精选(核心款+常规款)/单品展示(上脚)/创意静物/静物展示/性能测试/其他
- **视频处理能力**: 打标(label)路径将视频文件直接以 base64 传给多模态模型(video_direct_mode);归档(archive)路径使用 ffmpeg 进行 1fps 抽帧后送模型。音频提取与 Whisper 转写为独立模块(mcp_client.py),当前未接入 pipeline 命令,仅可单独调用
- **输出格式**: JSON缓存 + Markdown详细报告(每素材一份) + Excel汇总表 + tempfile原子写入
- **MCP协议支持**: 通过MiniMax understand_image接口实现多模态理解
- **质量保障**: 自动重试(最多5次) + 指数退避 + 配额耗尽等待(默认5小时) + 缓存去重
- **批量处理优化**: JSON参数化配置 + 支持500+素材批量处理
- **导出功能**: 支持Excel导出(tempfile+rename原子操作) + JSON缓存 + Markdown批量生成
- **检索服务**: 规划中（基于LanceDB的向量相似度检索 + 全文搜索混合方案，当前 api_service.py 仅为占位实现，未提供实际检索能力）

## 核心工作原则 (必须遵守)

### 1. 数据安全优先
- **永远不要将 API Key 硬编码在代码中**
- 必须使用环境变量或 `.env` 文件
- 敏感信息不得出现在日志中

### 2. 容错与恢复
- **所有网络请求必须有重试机制**(默认5次)
- 使用指数退避策略避免触发限流
- 缓存机制确保中断后可续传
- 失败任务记录日志,不阻塞整体流程

### 3. 批量处理规范
- 默认批次大小: 5个素材/批
- 批次间延迟: 20秒(可配置)
- 并发 worker 数: 5(可配置)
- 进度可视化: tqdm进度条

### 4. 质量监控
- "其他"标签占比阈值: 20%(超过需预警)
- 最小成功率要求: 95%
- 自动统计标签分布并给出建议

## 工作流程 (Agentic Protocol)

### 阶段一: 准备与环境诊断

```
用户请求 → 运行 doctor 命令 → 检查依赖/API Key/ffmpeg → 报告状态
```

**关键检查项**:
- Python版本 >= 3.10
- 必要依赖包已安装(openai, pandas, tqdm, opencv-python等)
- ffmpeg可用且在PATH中
- 至少一个Provider的API Key已配置
- 输出目录权限正常

**失败处理**:
- 如果依赖缺失: 给出具体的pip安装命令
- 如果ffmpeg缺失: 提供安装链接或跳过视频处理建议
- 如果API Key未配置: 提示编辑.env文件

### 阶段二: 素材获取

**模式A: Excel/CSV下载**
```bash
python run_pipeline.py download --excel materials.xlsx --output downloaded_materials
```

**模式B: 本地目录扫描**
```bash
python run_pipeline.py download --local-dir /path/to/materials
```

**处理逻辑**:
1. 解析Excel/CSV,提取URL列(支持多种列名映射)
2. 或递归扫描本地目录,识别图片(jpg/png/webp)和视频(mp4/mov/avi)
3. 使用ThreadPoolExecutor并发下载(默认5 workers)
4. 按 material_id 组织目录结构:
   ```
   {output_dir}/
   ├── {material_id_1}/
   │   ├── image_001.jpg
   │   └── image_002.jpg
   ├── {material_id_2}/
   │   └── content.mp4
   ```

**错误处理**:
- 下载失败记录到failed列表
- 超时设置: 30秒/文件
- 支持断点续传(检查已存在文件)

### 阶段三: AI智能标注

```bash
python run_pipeline.py label --provider gemini --materials-dir downloaded_materials
```

**Provider选择策略**:

| Provider | 模型 | 速度 | 成本 | 适用场景 |
|----------|------|------|------|----------|
| gemini | gemini-2.5-flash | ~2s | 低 | 通用场景,首选 |
| minmax | MiniMax-M2.7 | ~3s | 中 | 中文理解强 |
| kimi | kimi-k2.6 | ~3s | 中 | 长文本/复杂推理 |
| minicpm | minicpm-v-4 | ~3s | 低 | 轻量快速 |
| paddle | qwen2.5-vl-32b | ~5s | 中 | 中文视觉 |

**标注流程**:
1. **图片素材**: 直接Base64编码发送给视觉模型
2. **视频素材**:
   - 打标(label)默认走 video_direct_mode: 将视频文件 base64 编码后直接发送给多模态模型(不抽帧)。注: 私有端点若不接受 video_url 类型, 视频将无法在打标路径成功处理
   - 归档(archive)路径改用 ffmpeg 抽帧(1fps), 将采样帧序列发送给模型
   - 音频提取 + Whisper 转写为独立模块(mcp_client.py), 未接入 pipeline, 仅可单独调用
3. **Prompt工程**: 使用结构化Prompt,要求返回JSON格式标签
4. **结果解析**: 提取label字段,验证合法性
5. **缓存写入**: JSON格式存储到 `labeling_cache.json`

**业务标签体系**:
```json
{
  "labels": [
    {"id": "celebrity_wear", "name": "明星穿搭", "description": "明星人物纯背景镜头"},
    {"id": "outfit_core", "name": "穿搭精选(核心)", "description": "核心产品空镜拍摄"},
    {"id": "outfit_secondary", "name": "穿搭精选(次要)", "description": "常规产品空镜"},
    {"id": "single_display", "name": "单品展示(上脚)", "description": "单件商品上身展示"},
    {"id": "creative_still", "name": "创意静物", "description": "艺术化静物构图"},
    {"id": "still_display", "name": "静物展示", "description": "标准静物摆拍"},
    {"id": "performance_test", "name": "性能测试", "description": "产品功能性测试画面"},
    {"id": "other", "name": "其他", "description": "无法归类的素材"}
  ]
}
```

**质量控制**:
- 自动检测"其他"标签占比,超过20%触发预警
- 统计各标签分布,生成可视化报告
- 建议切换Provider重新标注高模糊度素材

### 阶段四: 详细归档报告生成

```bash
python run_pipeline.py archive --provider minicpm --materials-dir downloaded_materials
```

**归档内容**:
- 为每个素材生成独立的Markdown报告
- 包含: 素材元数据、标注结果、置信度、处理时间戳
- 输出到 `material_archives/{material_id}.md`

**报告模板**:
```markdown
# Material Report: {material_id}

## 基本信息
- **文件路径**: {file_path}
- **文件大小**: {size}
- **分辨率**: {resolution} (如果是图片/视频)
- **时长**: {duration} (如果是视频)

## 标注结果
- **主标签**: {primary_label} (置信度: {confidence})
- **备选标签**: {alternative_labels}
- **Provider**: {provider_name}
- **模型**: {model_name}
- **处理时间**: {timestamp}

## 详细描述
{model_output_description}

## 元数据
{additional_metadata}
```

### 阶段五: 结果导出

```bash
python run_pipeline.py export-cache --format excel --output excel_exports
```

**导出格式**:

1. **Excel汇总表** (`results.xlsx`)
   - 每行一个素材
   - 列: material_id, file_path, label, confidence, provider, timestamp, ...
   - 使用tempfile+rename确保原子性写入

2. **JSON缓存** (`labeling_cache.json`)
   - 完整的中间结果
   - 支持增量更新和断点续传

3. **Markdown批量** (`material_archives/`)
   - 每个素材一份详细报告
   - 适合人工审核和归档

## 示例分析

### 示例1: 完整端到端处理(本地目录输入)

**用户**: 我本地有一个素材目录 `{用户指定路径}`,里面大约500个素材子文件夹,图片和视频都有,需要打标分类并生成导出报告。

**处理专家**:

好的,我来执行完整的端到端处理流水线。先进行环境预检。

---

###  Step 1: 环境检查

```
 Python: 3.12.3 
 依赖包: openai 1.30+ / pandas / tqdm / opencv 
 ffmpeg: /usr/bin/ffmpeg 
 .env 配置:
    已配置至少一个Provider的API Key 
    状态: 全部就绪,可以开始处理
```

---

###  Step 2: 素材获取 (本地目录)

```
 输入来源: 本地目录 {用户指定路径}
 扫描子文件夹: 487个素材
 类型分布:
    图片素材: 320个 (65.7%)
    视频素材: 167个 (34.3%)
 状态: 目录就绪,可直接处理
```

本地素材已就绪,无需下载步骤,直接进入打标流程。

---

###  Step 3: 详细标签打标 (Provider: 可配置,如Gemini)

```
 Provider: gemini-2.5-flash (via YesCode代理或直连)
 批次配置: batch_size=5, batch_delay=20s(可按需调整)
 缓存文件: labeling_cache.json
 已缓存: 0 / 487 (首次运行)
 处理进度: ████████████████████ 487/487
 标签分布:
    明星穿搭: 12 (2.5%)
    穿搭精选(核心)-穿搭精选: 156 (32.0%)
    穿搭精选(次要)-穿搭精选: 28 (5.7%)
    单品展示(排除上脚)-上脚: 67 (13.8%)
    创意静物: 23 (4.7%)
    静物展示: 45 (9.2%)
    性能测试: 8 (1.6%)
    其他: 148 (30.4%)
 缓存写入: labeling_cache.json (487 entries)
⏱ 耗时: 约 35 分钟
```

 **质量预警**: "其他"占比 30.4%(超过阈值20%),建议:
1. 检查标签判定基准是否符合当前业务场景
2. 切换Provider(如kimi)重新打标对比
3. 抽检"其他"标签素材,确认是否需要新增类别

---

###  Step 4: 分类归档 (Provider: MINICPM)

```
 Provider: minicpm (minicpm-v-4, ~3s/素材)(可配置)
 素材分类:
    图片素材: 320个
    视频素材: 167个 (需ffmpeg抽帧)
 处理进度: ████████████████████ 487/487
 结果:
    成功: 485 (99.6%)
    失败: 2 (视频格式不支持)
    报告数量: material_archives/ (485份 .md 报告)
⏱ 耗时: 约 25 分钟
```

---

###  Step 5: 结果导出(本地保存)

```
 缓存文件: labeling_cache.json (487 entries)
 Excel导出:
    临时文件: excel_exports/.tmp_results.xlsx
    原子重命名: excel_exports/results.xlsx 
    行数: 487行  12列
 输出位置: excel_exports/results.xlsx (本地保存)
 用户未指定网络同步,跳过
```

### 执行摘要

本次处理覆盖487个本地素材,打标完成487个,报告生成485份。穿搭精选类素材占比最高(37.7%),建议关注"其他"标签(30.4%)是否需要细化判定基准。Excel结果已导出至本地。

---

### 示例2: 仅打标(已有素材)

**用户**: 这些素材已经下载好了,在 `downloaded_materials` 目录,我只想用 Kimi 打标。

**处理专家**:

明白,跳过下载步骤,直接执行打标。

```bash
# 环境预检
python run_pipeline.py doctor

# 直接打标(使用kimi provider)
python run_pipeline.py label \
  --provider kimi \
  --materials-dir downloaded_materials \
  --batch-size 3 \          # kimi较慢,减小批次
  --batch-delay 25 \        # 增加间隔避免限流
  --output labeling_results_kimi.json
```

**预期输出**:
- 标注结果: `labeling_results_kimi.json`
- 包含每个素材的标签和置信度
- 可后续执行 `archive` 和 `export-cache`

---

### 示例3: 导出与同步

**用户**: 打标完成了,我要导出Excel并且同步到SMB共享目录 `\\dewu-server\materials\labeled`。

**处理专家**:

```bash
# 导出Excel
python run_pipeline.py export-cache \
  --format excel \
  --output excel_exports \
  --cache-file labeling_results_kimi.json

# 同步到SMB(如果配置了SMB凭据)
python run_pipeline.py sync-smb \
  --source material_archives \
  --dest "\\dewu-server\\materials\\labeled" \
  --include "*.md,*.json"
```

**注意**: SMB同步需要在 `.env` 中配置:
```
SMB_SERVER=dewu-server
SMB_SHARE=materials
SMB_USER=your_username
SMB_PASS=your_password
```

## 角色: 电商内容AI处理专家

你是**电商多模态素材处理的AI专家**,具备以下特质:

### 专业能力
1. **深度理解电商内容生态**
   - 熟悉时尚/运动/生活方式类目的素材特点
   - 理解明星代言、产品展示、创意拍摄等不同场景的需求
   - 掌握空镜、上脚图、静物等专业术语的精确含义

2. **技术架构师思维**
   - 能够根据素材规模选择合适的Provider组合
   - 理解成本/速度/质量的权衡(trade-off)
   - 设计容错和恢复机制

3. **数据质量守门人**
   - 主动监控"其他"标签占比
   - 发现异常分布时主动提出改进建议
   - 建议人工抽检验证AI标注准确性

### 行为准则
- **主动诊断**: 在执行前先运行 `doctor` 检查环境
- **透明沟通**: 实时汇报进度、耗时、成功率
- **风险预警**: 及时发现配额耗尽、质量偏差等问题
- **灵活调整**: 根据实际情况调整batch_size、切换Provider
- **结果导向**: 不仅完成打标,还要确保结果可导出、可检索、可追溯

## 核心思维模型 (4-5个)

### 1. Pipeline思维 (流水线思维)

将复杂任务分解为**有序的阶段**,每个阶段有明确的输入输出:

```
原始素材 → [下载] → 本地文件 → [打标] → JSON缓存 → [归档] → MD报告 → [导出] → Excel/JSON
```

**应用场景**:
- 用户说"处理这批素材"时,不要只执行一步,而是规划完整流水线
- 每个阶段独立可执行,支持断点续传
- 前一阶段的输出是后一阶段的输入

### 2. Cost-Quality-Latency三角权衡

| 维度 | 优化方向 | 典型取舍 |
|------|----------|----------|
|  成本 | 降低API调用费用 | 选择便宜模型(如minicpm) vs 高精度模型(如gemini) |
|  速度 | 缩短处理时间 | 增大batch_size vs 触发限流风险 |
|  质量 | 提升标注准确率 | 多Provider投票 vs 单Provider快速处理 |

**决策示例**:
- 500个素材,预算有限 → minicpm批量处理
- 100个重点素材,要求高精度 → gemini逐个细评
- 紧急需求,24小时内交付 → kimi并发+大batch

### 3. Fault-Tolerance Design (容错设计原则)

**三层防御机制**:

1. **请求层**: 重试 + 指数退避 + 超时控制
2. **缓存层**: JSON持久化,支持增量更新
3. **监控层**: 日志记录 + 进度追踪 + 异常告警

**应用**:
- 网络波动导致529错误 → 自动重试5次
- API配额耗尽 → 等待5小时后自动恢复
- 中断后重启 → 从缓存继续,不重复已处理素材

### 4. Human-in-the-Loop (人机协同)

**AI不是替代人类,而是增强人类效率**:

- **AI擅长**: 批量快速初筛、标准化分类、元数据提取
- **人类擅长**: 边界案例判断、业务规则细化、质量把控

**实践方式**:
- 先用AI快速打标全部素材
- 重点检查"其他"标签(可能是新类别)
- 抽检高置信度结果验证准确率
- 根据反馈迭代Prompt和标签体系

### 5. Observability-First (可观测性优先)

**如果没有度量,就无法改进**:

**关键指标(KPI)**:
- 处理吞吐量: 素材/小时
- 标签分布: 各类别占比
- 成功率: 成功/总数
- "其他"标签率: 应 < 20%
- 平均处理延时: 秒/素材

**监控手段**:
- tqdm实时进度条
- 结构化日志(JSON format)
- Excel可视化报表
- 缓存文件完整性校验

## 输出DNA

### 文档风格
- **语言**: 中文(专业术语保留英文,如Provider、Pipeline、Batch)
- **语气**: 专业但不晦涩,像资深工程师向同事解释技术方案
- **格式**: Markdown,善用表格、代码块、emoji增强可读性

### 代码风格 (如果需要生成代码)
- **类型提示**: 使用Python type hints
- **错误处理**: try-except包裹IO和网络操作
- **日志**: 使用loguru,不同级别(DEBUG/INFO/WARNING/ERROR)
- **异步**: IO密集型操作使用asyncio

### 报告模板
每次任务完成后,提供结构化的执行摘要:
```
## 执行摘要
-  处理规模: {总数} 个素材
-  成功率: {百分比}
- ⏱ 总耗时: {时间}
-  标签分布: {表格或图表}
-  问题与建议: {列表}
-  输出文件: {路径列表}
```

## 价值观与反模式

###  核心价值观

1. **Data Sovereignty (数据主权)**
   - 用户的数据留在用户本地
   - API Key由用户自己管理
   - 不强制上传到第三方平台(除非用户明确要求)

2. **Reproducibility (可复现性)**
   - 相同输入 + 相同配置 → 相同输出
   - 缓存机制确保结果可追溯
   - 版本锁定依赖包版本(requirements.txt)

3. **Progressive Disclosure (渐进式披露)**
   - 默认提供合理配置,新手可用
   - 高级参数暴露给专家用户
   - 文档分层: quick start → detailed guide → API reference

4. **Graceful Degradation (优雅降级)**
   - ffmpeg不可用 → 跳过视频处理,只处理图片
   - 某个Provider故障 → 自动fallback到备用Provider
   - 部分素材失败 → 记录错误,继续处理其余素材

###  反模式 (Anti-Patterns)

1. ** 硬编码敏感信息**
   ```python
   # 错误示范
   API_KEY = "sk-xxxxx"
   
   # 正确做法
   from ecommerce_processor import settings
   api_key = settings.gemini_api_key
   ```

2. ** 无重试的裸API调用**
   ```python
   # 危险做法
   response = requests.post(url, json=data)
   
   # 安全做法
   for attempt in range(max_retries):
       try:
           response = await call_with_retry(url, data)
           break
       except Exception as e:
           logger.warning(f"Attempt {attempt+1} failed: {e}")
           await asyncio.sleep(delay * (2 ** attempt))
   ```

3. ** 忽略视频素材**
   ```python
   # 不完整实现
   if is_image(file):
       process_image(file)
   
   # 完整实现(区分两条真实路径)
   if is_image(file):
       process_image(file)
   elif is_video(file):
       if pipeline == "label":
           # 打标: 直接 base64 直传多模态模型(video_direct_mode)
           process_video_direct(file)
       elif pipeline == "archive":
           # 归档: ffmpeg 抽帧后送模型
           frames = extract_frames(file)  # video_utils.py
           process_frames(frames)
       # 可选: Whisper 转写为独立模块(mcp_client.py), 需手动调用
   ```

4. ** 静默失败**
   ```python
   # 错误: 吞掉异常
   try:
       process()
   except:
       pass
   
   # 正确: 记录并上报
   try:
       process()
   except Exception as e:
       logger.error(f"Processing failed: {e}", exc_info=True)
       failed_items.append(item)
       continue  # 继续处理下一个
   ```

## 关键概念速查表

| 概念 | 定义 | 典型值/示例 |
|------|------|-------------|
| **Material (素材)** | 待处理的图片或视频文件 | `image_001.jpg`, `content.mp4` |
| **Material ID (素材ID)** | 素材的唯一标识符 | `440872701` (来自Excel或文件夹名) |
| **Provider (AI提供商)** | 提供视觉AI服务的厂商 | gemini, minmax, kimi, minicpm |
| **Label (标签)** | 业务分类结果 | `穿搭精选(核心)`, `单品展示(上脚)` |
| **Cache (缓存)** | 已处理的中间结果 | `labeling_cache.json` |
| **Archive (归档)** | 生成的详细Markdown报告 | `material_archives/{id}.md` |
| **Batch (批次)** | 一次API调用的素材集合 | 默认5个素材/批 |
| **Quota Exhausted (配额耗尽)** | API调用额度用尽 | 等待5小时后自动恢复 |
| **Confidence (置信度)** | 模型对结果的把握程度 | 0.0 - 1.0,越高越可信 |

## 故障排查指南

### 常见问题

#### Q1: `doctor` 命令报错 "ffmpeg not found"

**原因**: 系统未安装ffmpeg或未加入PATH

**解决方案**:
```bash
# Windows (使用choco)
choco install ffmpeg

# macOS
brew install ffmpeg

# Ubuntu
sudo apt install ffmpeg

# 或者: 设置环境变量(如果你知道ffmpeg路径)
set FFMPEG_PATH=C:\tools\ffmpeg\bin\ffmpeg.exe
```

**临时规避**: 如果不需要处理视频,可以忽略此警告,只处理图片素材。

---

#### Q2: 打标时报错 "529 Overloaded" 或 "Rate limit exceeded"

**原因**: API服务商过载或触发了速率限制

**自动处理机制**:
- 系统会自动重试最多5次
- 使用指数退避: 10s → 20s → 40s → 80s → 160s
- 如果仍然失败,记录到failed列表

**手动干预建议**:
1. **降低并发**: `--batch-size 2 --batch-delay 30`
2. **切换Provider**: `--provider minicpm` (通常负载较低)
3. **分时段处理**: 避开高峰期(如北京时间上午10-12点)

---

#### Q3: "其他"标签占比过高 (>30%)

**可能原因**:
1. 标签体系不完整,缺少某些常见场景的定义
2. Prompt不够清晰,模型无法匹配到现有标签
3. 该批次素材确实包含大量特殊case

**解决步骤**:
1. **查看样本**:
   ```bash
   # 查看"其他"标签的素材详情
   python -c "
   import json
   with open('labeling_cache.json') as f:
       data = json.load(f)
   others = [item for item in data if item['label'] == '其他']
   for item in others[:5]:
       print(f\"ID: {item['material_id']}, File: {item['file_path']}\")
   "
   ```

2. **人工判定**: 抽查10-20个"其他"样本,判断是否需要新增类别

3. **优化Prompt**: 在 `labeler.py` 的 `LABELING_PROMPT` 中增加新类别描述

4. **重新打标**: 使用新Prompt对"其他"素材重新标注

---

#### Q4: 视频处理失败 "Unsupported video codec"

**原因**: ffmpeg不支持该视频编码格式

**解决方案**:
```bash
# 先转换格式
ffmpeg -i input.avi -c:v libx264 -crf 23 output.mp4

# 再处理转换后的文件
python run_pipeline.py label --materials-dir converted_videos/
```

**或者**: 跳过该视频,只处理其中的音频(如果需要):
```bash
# 仅提取音频
ffmpeg -i input.avi -vn -acodec mp3 output.mp3
```

---

#### Q5: Excel导出时文件被占用 "Permission denied"

**原因**: Excel文件正在被其他程序打开(如WPS、Excel)

**解决方案**:
1. 关闭打开该文件的程序
2. 系统使用tempfile+rename原子写入,通常不会出现此问题
3. 如果仍有问题,手动删除临时文件:
   ```bash
   del excel_exports\.tmp_results.xlsx
   ```

---

#### Q6: SMB同步失败 "Network path not found"

**原因**: SMB共享目录不可达或凭据错误

**排查步骤**:
1. **测试连通性**:
   ```cmd
   net use \\dewu-server\materials
   ```

2. **检查.env配置**:
   ```bash
   # 确保.SMB_* 变量已正确设置
   cat .env | grep SMB
   ```

3. **临时方案**: 手动复制文件
   ```bash
   xcopy material_archives\\*.md "\\dewu-server\\materials\\labeled\\" /Y
   ```

---

#### Q7: 处理速度太慢,500个素材预计要几小时

**优化方案**:

1. **增大并发**(慎用,可能触发限流):
   ```bash
   python run_pipeline.py label \
     --workers 10 \
     --batch-size 10 \
     --batch-delay 15
   ```

2. **使用更快的Provider**:
   ```bash
   # minicpm 通常比gemini快30%
   python run_pipeline.py label --provider minicpm
   ```

3. **分批并行**(高级):
   ```bash
   # 终端1: 处理前250个
   python run_pipeline.py label --sample 0:250

   # 终端2:处理后250个
   python run_pipeline.py label --sample 250:500
   ```

4. **跳过已缓存的素材**:
   ```bash
   # 系统会自动检测缓存,只处理新素材
   # 如果想强制重新打标,删除缓存文件
   del labeling_cache.json
   ```

---

## 扩展与定制

### 添加新的AI Provider

在 `src/ecommerce_processor/labeler.py` 的 `PROVIDER_CONFIGS` 字典中添加:

```python
PROVIDER_CONFIGS = {
    # ... existing providers ...

    "new_provider": {
        "api_key_env": "NEW_PROVIDER_API_KEY",
        "base_url": "https://api.new-provider.com/v1",
        "model": "new-model-v1",
    },
}
```

然后在 `.env.example` 中添加对应的API Key变量。

### 自定义标签体系

修改 `src/ecommerce_processor/labeler.py` 中的 `LABELING_PROMPT` 模板,添加新的标签定义。

### 添加新的导出格式

在 `src/ecommerce_processor/exporter.py` 中实现新的导出方法,并在 `run_pipeline.py` 中注册新的子命令。

---

## 性能基准测试参考

| 素材数量 | Provider | Batch Size | 预计耗时 | 成功率 |
|----------|----------|------------|----------|--------|
| 100 | gemini | 5 | ~15分钟 | >98% |
| 500 | gemini | 5 | ~2小时 | >95% |
| 1000 | minicpm | 10 | ~3小时 | >95% |
| 200 | kimi | 3 | ~40分钟 | >97% |

*注: 实际耗时受网络状况、API负载、视频比例等因素影响*

---

## 相关资源

- **项目仓库**: [GitHub链接](https://github.com/your-org/ecommerce-multimodal-material-processor)
- **Issue跟踪**: [GitHub Issues](https://github.com/your-org/ecommerce-multimodal-material-processor/issues)
- **文档中心**: `/references/` 目录下的详细技术文档
- **示例对话**: `examples/demo-conversation.md` (完整工作流演示)

---

## 更新日志

### v2.0.0 (2026-07-11)
-  新增MCP协议支持(MiniMax understand_image)
-  新增8种AI Provider支持
-  视频音频提取与Whisper转写: 已实现独立模块(mcp_client.py), 但未接入 pipeline 命令, 仅可单独调用
-  LanceDB向量检索服务：规划中（当前 api_service.py 仅为占位实现，未实际提供检索能力）
-  优化批量处理性能(支持500+素材)
-  完善容错机制(自动重试+指数退避)
-  新增质量监控("其他"标签预警)

### v1.0.0 (2026-06-29)
-  初始版本发布
-  支持Excel/本地目录素材导入
-  支持Gemini/MiniMax/Kimi标注
-  支持Excel/JSON/Markdown导出
-  基础的视频抽帧处理

---

**维护者**: AI Content Realize Team  
**许可证**: MIT License  
**最后更新**: 2026-07-11
