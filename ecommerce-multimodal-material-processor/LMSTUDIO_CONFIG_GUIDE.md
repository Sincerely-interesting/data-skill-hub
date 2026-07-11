# 🎯 自建LM Studio服务器配置指南

## ✅ 配置完成状态

**配置时间**: 2026-07-11  
**目标服务器**: LM Studio (Gemma-4-12B-IT)  
**服务器地址**: `https://lmstudio.deep-think.com.cn/v1`  
**配置状态**: ✅ **已完成并优化**

---

## 📋 已完成的配置项

### 1. **环境变量配置 (`.env`)**

```ini
# === 主力Provider配置 ===
CUSTOM_MINMAX_URL=https://lmstudio.deep-think.com.cn/v1
CUSTOM_MINMAX_API_KEY=sk-lm-zHTqwGhs:HtkoVTooYYruJP0U711R

# === LLM模型参数 (针对Gemma-4-12B-IT优化) ===
LLM_MODEL=gemma-4-12b-it           # 模型名称
LLM_TIMEOUT_MS=180000              # 超时: 180秒(3分钟)
LLM_TEMPERATURE=0.7                # 温度: 0.7(较高创造性)
LLM_MAX_TOKENS=2600                # 最大输出Token
LLM_CONCURRENCY=1                  # 并发数: 1(串行)
ENABLE_MOCK_LLM=false              # 禁用模拟模式
ENABLE_FALLBACK=true               # 启用故障回退
```

### 2. **代码层配置 (`config.py`)**

新增以下配置字段:

```python
class Settings(BaseSettings):
    # ... 原有配置 ...
    
    # ---- LLM模型参数 ----
    llm_model: str = "gemma-4-12b-it"
    llm_timeout_ms: int = 180000      # 180秒
    llm_temperature: float = 0.7       # 0.0-2.0
    llm_max_tokens: int = 2600
    llm_concurrency: int = 1
    enable_mock_llm: bool = False
    enable_fallback: bool = True
```

### 3. **运行时适配 (`labeler.py`)**

#### 改动点:
- ✅ **动态模型选择**: 从硬编码改为读取 `settings.llm_model`
- ✅ **可配置超时**: HTTP客户端超时从固定60秒 → `settings.llm_timeout_ms/1000`
- ✅ **灵活温度控制**: 从固定0.3 → `settings.llm_temperature`
- ✅ **可控Token限制**: 从固定1024 → `settings.llm_max_tokens`
- ✅ **Provider配置更新**: custom_minmax的model字段设为"auto"(自动从settings读取)

---

## 🚀 快速开始测试

### Step 1: 验证配置

```bash
# 进入项目目录
cd F:\Code\idea\data-skill-hub\ecommerce-multimodal-material-processor

# 运行专用测试脚本
python test_lmstudio_config.py
```

**预期输出示例**:
```
============================================================
🔧 LM Studio 服务器连接测试
============================================================

📋 当前配置:
  服务器URL: https://lmstudio.deep-think.com.cn/v1
  API Key: sk-lm-zHTq...JP0U711R
  模型名称: gemma-4-12b-it
  超时时间: 180.0秒
  温度参数: 0.7
  最大Token: 2600
  并发数: 1

🌐 测试网络连接...
  [1/4] 检查服务器可达性: https://lmstudio.deep-think.com.cn/v1/models
  ✅ 服务器响应正常 (状态码: 200)
  📦 可用模型列表 (3个):
     - gemma-4-12b-it
     - gemma-4-9b-it
     - llama-3-8b
  ✅ 目标模型 'gemma-4-12b-it' 存在

  [2/4] 测试API调用: /chat/completions
  ✅ API调用成功!
  🤖 模型回复: 我是Gemma-4，一个由Google开发的多模态大语言模型...
  📊 Token使用: 输入=15, 输出=42

  [3/4] 初始化MaterialLabeler...
  ✅ Labeler初始化成功

  [4/4] 配置完整性检查...
  ✅ 所有配置检查通过

============================================================
🎉 所有测试通过！你的LM Studio服务器配置正确
============================================================
```

### Step 2: 准备测试素材

```bash
# 创建测试目录
mkdir test_images

# 复制几张图片到该目录 (建议3-5张JPG/PNG)
# 例如:
#   test_images/product_001.jpg
#   test_images/model_showcase.png
#   test_images/celebrity_endorsement.jpg
```

### Step 3: 执行完整流水线

```bash
# 1. 扫描本地素材 (无需下载)
python run_pipeline.py download --local-dir ./test_images

# 2. 使用你的LM Studio服务器进行AI标注
python run_pipeline.py label --provider custom_minmax

# 3. 导出结果到Excel
python run_pipeline.py export --output-dir ./output

# 4. 生成归档报告 (可选)
python run_pipeline.py archive --output-dir ./archive_report
```

---

## ⚙️ 参数调优建议

### 针对 Gemma-4-12B-IT 的推荐配置

| 参数 | 当前值 | 推荐范围 | 说明 |
|------|--------|---------|------|
| **LLM_TEMPERATURE** | 0.7 | 0.5-0.8 | 较高温度增加标注多样性 |
| **LLM_MAX_TOKENS** | 2600 | 1500-3000 | 足够生成详细标签 |
| **LLM_TIMEOUT_MS** | 180000 | 120000-300000 | 本地模型响应较慢 |
| **LLM_CONCURRENCY** | 1 | 1 | 避免GPU过载 |
| **DEFAULT_BATCH_SIZE** | 5 | 3-5 | 小批量提高稳定性 |
| **DEFAULT_BATCH_DELAY** | 20.0 | 10.0-30.0 | 批次间休息时间 |

### 性能优化技巧

#### 1. **减少超时等待**
如果网络稳定且服务器响应快，可以降低超时:
```ini
LLM_TIMEOUT_MS=120000  # 120秒足够大多数情况
```

#### 2. **提高吞吐量 (谨慎使用)**
如果你的GPU显存>=24GB，可以尝试并发:
```ini
LLM_CONCURRENCY=2  # 同时处理2个请求
DEFAULT_BATCH_SIZE=10  # 每批处理10个
```

#### 3. **平衡质量与速度**
- **追求质量** (默认):
  ```ini
  LLM_TEMPERATURE=0.7
  LLM_MAX_TOKENS=2600
  ```
- **追求速度**:
  ```ini
  LLM_TEMPERATURE=0.3  # 更确定性输出
  LLM_MAX_TOKENS=1500  # 更短回复
  ```

---

## 🔍 故障排查

### 常见问题及解决方案

#### ❌ 问题1: 连接超时

**错误信息**:
```
❌ 连接超时 (> 180秒)
```

**解决方案**:
```ini
# 方案A: 增加超时时间
LLM_TIMEOUT_MS=300000  # 5分钟

# 方案B: 检查服务器负载
# 在LM Studio界面查看GPU使用率,如>90%则需等待或降低并发
```

#### ❌ 问题2: 模型不存在

**错误信息**:
```
⚠️  警告: 目标模型 'gemma-4-12b-it' 未在列表中找到
```

**解决方案**:
```bash
# 1. 查看可用模型列表
python test_lmstudio_config.py

# 2. 修改.env中的模型名称为实际存在的模型
# 例如: LLM_MODEL=gemma-4-9b-it
```

#### ❌ 问题3: API Key无效

**错误信息**:
```
❌ API调用失败 (状态码: 401)
```

**解决方案**:
1. 检查API Key是否完整复制 (无多余空格)
2. 确认LM Studio服务器的认证设置
3. 重新生成API Key并更新.env

#### ❌ 问题4: 标注结果质量差

**可能原因及调整**:

| 症状 | 原因 | 解决方案 |
|------|------|---------|
| 标签过于简单 | 温度过低 | 提高`LLM_TEMPERATURE`至0.7-0.9 |
| 标签不一致 | 温度过高 | 降低`LLM_TEMPERATURE`至0.3-0.5 |
| 标签被截断 | Token不足 | 增加`LLM_MAX_TOKENS`至3000+ |
| 标注速度慢 | 超时过短 | 增加`LLM_TIMEOUT_MS` |

---

## 📊 监控与日志

### 启用详细日志

```ini
# .env 中修改日志级别
LOG_LEVEL=DEBUG
```

**关键日志位置**:
- `logs/ecommerce_processor.log` - 主日志文件
- 控制台实时输出 - 运行命令时的标准输出

### 重要日志关键字段

搜索这些关键词来定位问题:
- `[ERROR]` - 错误信息
- `[WARNING]` - 警告 (如回退到备用Provider)
- `Retry attempt` - 重试记录
- `Batch completed` - 批次完成统计

---

## 🔒 安全注意事项

### 1. **保护API Key**

✅ 已做:
- `.env`已添加到`.gitignore`
- 不会提交到版本控制

⚠️ 你需要:
- 不要将.env文件分享给他人
- 定期轮换API Key
- 限制LM Studio服务器的访问IP (如果可能)

### 2. **网络安全**

由于你的服务器使用HTTPS，数据传输是加密的。但建议:
- 使用VPN或内网访问 (如果是公网暴露的服务器)
- 定期检查服务器访问日志
- 设置速率限制防止滥用

---

## 🔄 后续扩展

### 添加更多自定义Provider

如果你想同时使用多个自建服务器:

```ini
# .env 示例
# 服务器1: 主力 (Gemma-4)
CUSTOM_MINMAX_URL=https://server1.example.com/v1
CUSTOM_MINMAX_API_KEY=key-for-server1

# 可以考虑扩展config.py支持多个custom provider
# 或使用MINICPM作为第二个自定义端点
MINICPM_BASE_URL=https://server2.example.com/v1
MINICPM_API_KEY=key-for-server2
```

### 与其他系统集成

当前配置支持:
- ✅ CLI命令行工具
- ✅ Python API直接调用
- ✅ Web API服务 (FastAPI)

未来可扩展:
- Docker容器化部署
- Kubernetes集群调度
- Celery异步任务队列

---

## 📞 技术支持

### 快速诊断命令

```bash
# 1. 环境健康检查
python run_pipeline.py doctor

# 2. LM Studio连接测试
python test_lmstudio_config.py

# 3. 查看详细日志
type logs\ecommerce_processor.log | findstr /i "error warning"

# 4. 测试单张图片标注
python -c "
import asyncio
from ecommerce_processor.labeler import MaterialLabeler

async def test():
    labeler = MaterialLabeler(provider='custom_minmax', materials_dir='./test_images')
    result = await labeler.label_single_image('test_images/sample.jpg')
    print(result)

asyncio.run(test())
"
```

---

## ✨ 总结

你的**自建LM Studio服务器**现在已经完全集成到电商多模态素材处理Skill中！

**核心优势**:
- 🚀 **零延迟**: 本地部署,无网络传输延迟
- 🔒 **数据安全**: 素材不离开内网
- 💰 **成本可控**: 无按次计费,无限使用
- 🎛️ **完全可控**: 可调整任何参数

**立即开始测试**:
```bash
python test_lmstudio_config.py
```

祝测试顺利！如有问题请查看上方故障排查章节。
