---
name: 电商多模态素材打标（薄壳客户端）
description: 电商素材 8 类标签打标的**纯接口层**客户端。所有打标在服务端完成，本客户端不含任何模型密钥、提示词或打标引擎，仅负责鉴权、本地打包压缩包、分块可续传上传素材、发起打标请求、取回结构化结果。
---

# 电商素材打标 · 薄壳客户端

> 本 Skill 是**纯接口层**（"对话与引用"）。它**不持有**任何模型密钥，**不包含**任何 VLM 调用、提示词或打标引擎代码。
> 真正的打标（自研引擎）全部在**服务商后端**完成。你只拿到这个薄壳 + 一个凭证 token。

## 使用前（只填 2 个参数）

复制 `.env.example` 为 `.env`，只填：

```
GATEWAY_BASE_URL=http://119.91.111.63:8080
CREDENTIAL=sk_服务商下发的token
```

无需 `pip install` —— 本客户端仅用 Python 标准库。

## 子命令

| 命令 | 作用 |
|---|---|
| `python skill_client.py auth` | 鉴权 + 查看本凭证配额（剩余批量次数/有效期） |
| `python skill_client.py batch --dir 素材根目录` | 批量打标（服务端执行）；**自动扫描磁盘选最富裕且够用的盘**作工作 / 输出目录；成功后把结果落地本地并生成 PDF 报告 |
| `python skill_client.py report` | 查看本凭证使用回执（已用/剩余批量次数、累计上传文件数） |

`batch` 可选参数：
- `--out-dir 目录`：结果 JSON / PDF 的输出目录（默认=**自动选中的最富裕且够用的盘**）
- `--no-pdf`：只落地 `labeling_result.json`，不生成 PDF
- `--no-auto-drive`：禁用自动选盘（严格用 `--out-dir` 指定或素材所在盘，空间不足仅警告不降级）
- `--confirm-drive`：打印预检后阻塞等待客户确认（手动场景；自动化请勿开启）

> 注：旧版 `upload` / `label` 单文件子命令已移除。所有打标统一走 `batch` 压缩包协议。

## 打标结果与 PDF 报告

**服务端不保留缓存**：打标结果凭本凭证随 `batch` 响应一次性返回本地，客户端负责落地与出报告。

`batch` 成功后自动：
1. 落地 `labeling_result.json`（`{material_id: {label, confidence, reasoning, ...}}`，即打标缓存格式）到输出目录。
2. 调用同目录 `reporter.py` 生成 `素材分析报告.pdf`（数据总览 / 标签分布 / 分类代表素材 TOP3 / 图片视频分型 / 待人工复核清单 / 全量明细）。

**PDF 是可选辅助**，需要 `reportlab`：
```
pip install reportlab
```
未安装时 `batch` 只落地 JSON、跳过 PDF（输出含 `report_pdf_skipped` 提示），**不影响打标本身**。核心链路（鉴权/打包/上传/落地 JSON）仍是纯标准库、零依赖。

也可对已有 JSON 单独出报告：
```
python reporter.py -c labeling_result.json -o 素材分析报告.pdf
```

## 环境预检：自动扫描磁盘选最富裕盘

为避免客户把大素材放在系统盘（如 C:）时，打包临时 / 输出把磁盘写爆导致整批失败（真实踩坑：C 盘满 → `WinError 112` / `No space left on device`），`batch` / `pack` 在动手前会先做**环境预检**：

1. **扫描**所有挂载盘可用空间（标准库 `shutil.disk_usage`，跨平台，零依赖）。
2. **估算**素材总大小，按 `素材×2.2 + 200MB` 计算安全余量需求。
3. **选盘**：在 free 满足安全余量的盘中，选 **free 最大（最富裕）** 的盘作为工作 / 输出目录；若客户显式 `--out-dir` 且空间充足则尊重客户。
4. **把打包临时目录（TEMP）也指到该盘**，从根上避免写爆系统盘 Temp。
5. **先把"选盘决策"作为 `env_precheck` JSON 打印给终端客户（提示），再继续执行**打包上传。

终端客户可在该 JSON 中看到：`material_gb` / `need_gb` / `work_drive` / `drive_free_gb` / `auto_override` / `message`。
- 若客户指定盘空间不足，会自动改到最富裕盘并在 `message` 说明（`auto_override: true`）。
- `--no-auto-drive`：关闭自动降级，严格用客户指定 / 素材所在盘（空间不足仅警告）。
- `--confirm-drive`：手动场景打印预检后阻塞等待 `y/N` 确认（自动化请勿开启，否则无 stdin 会中止）。

## 上传协议（压缩包 + 分块可续传）

`batch` 流程：

1. **本地预检**：统计单元数（≤200）、单文件类型/大小、压缩包总大小（可选 `MAX_PACKAGE_SIZE_MB` 提示）。
2. **打包**：把每个子文件夹打成一个 zip，内含 `manifest.json`（单元数、总字节、每文件 sha256、HMAC 签名），作为"可验证信息"。
3. **服务端 precheck**：校验凭证、单元数、大小、签名；返回 `upload_token` 与（若支持）`supports_chunks` + `chunk_size`。
4. **上传**：
   - 服务端支持分块 → 按 `chunk_size`（默认 2MB）切片，**逐块 POST**，单块失败指数退避重试，支持断点续传（先查已收块跳过），全到齐后 `commit`（校验整包 sha256 重组打标）。这是应对 **1M 慢链路被反代整体 RST** 的关键——每块独立短连接，某块失败只重传那块。
   - 服务端不支持分块 → 回退**单次上传整包**（兜底）。

## 服务端强制的限制（客户端无法绕过）

- 单张图片 ≤ 50MB，单个视频 ≤ 500MB，仅允许指定扩展名
- 单次批量单元数 ≤ 200（图片组 + 视频段合计）
- 每凭证批量打标次数有限（用完返回 `quota_exceeded` 402）
- 一组图片上限三态：服务端可配置为无上限 / 禁止图片 / 限制张数

## 可选配置（.env 中，仅客户端预检提示，服务端为权威）

| 项 | 默认 | 说明 |
|---|---|---|
| `MAX_IMAGES_PER_GROUP` | 空 | 一组图片上限：空=无上限 / 0=禁止 / 正整数=上限张数 |
| `MAX_PACKAGE_SIZE_MB` | 0 | 压缩包本地预检上限(MB)，0=不限制 |
| `COMPRESS_BUDGET_MB` | 0 | 图片压缩预算(MB)，0=不压缩 |
| `FFMPEG_PATH` | 空 | 视频处理用 ffmpeg 路径 |
| `CHUNK_RETRY` | 5 | 单块上传最大重试次数 |
| `CHUNK_BACKOFF` | 1.5 | 单块重试指数退避基数(秒) |

## 输出

所有命令输出均为一行 JSON，便于程序解析：

```json
{"action":"batch_ok","units":2,"results":[
  {"unit_id":"g1","result":{"material_id":"g1","label":"穿搭精选(核心)","confidence":0.95,"reasoning":"..."}},
  {"unit_id":"g2","result":{"material_id":"g2","label":"穿搭精选(核心)","confidence":0.95,"reasoning":"..."}}
],"batches_left":0}
```
