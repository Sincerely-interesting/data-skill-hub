---
name: 电商多模态素材打标（薄壳客户端）
description: 电商素材 8 类标签打标的**纯接口层**客户端。所有打标在服务端完成，本客户端不含任何模型密钥、提示词或打标引擎，仅负责鉴权、上传素材、发起打标请求、取回结构化结果。
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
| `python skill_client.py auth` | 鉴权 + 查看本凭证配额（剩余批量次数） |
| `python skill_client.py upload --file 图片.jpg [--unit 单元名]` | 上传单个素材（服务端强制类型/大小限制） |
| `python skill_client.py label --file 图片.jpg` | 上传并打标单个素材（服务端执行） |
| `python skill_client.py batch --dir 素材根目录` | 批量打标：子文件夹=图片组单元，顶层视频=视频单元（服务端执行） |
| `python skill_client.py report` | 查看本凭证使用回执 |

## 服务端强制的限制（客户端无法绕过）

- 单张图片 ≤ 50MB，单个视频 ≤ 500MB，仅允许指定扩展名
- 单次批量单元数 ≤ 200（图片组 + 视频段合计）
- 每凭证批量打标次数有限（默认 2 次，用完返回 `quota_exceeded` 402）
- 一组图片上限三态：服务端可配置为无上限 / 禁止图片 / 限制张数

## 输出

所有命令输出均为一行 JSON，便于程序解析：

```json
{"action":"batch_ok","units":2,"results":[
  {"unit_id":"g1","result":{"material_id":"g1","label":"穿搭精选(核心)","confidence":0.95,"reasoning":"..."}},
  {"unit_id":"g2","result":{"material_id":"g2","label":"穿搭精选(核心)","confidence":0.95,"reasoning":"..."}}
],"batches_left":0}
```
