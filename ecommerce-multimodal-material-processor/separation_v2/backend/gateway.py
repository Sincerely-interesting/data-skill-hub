#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后端网关 + 自研打标服务（服务端打标，密钥/提示词/高价值资产不出服务端）

设计要点（对应需求）：
  - 薄壳（客户侧）只做"对话与引用"：鉴权、上传素材、发起打标请求、取回结果。
  - 打标逻辑全部在服务端执行：本网关直接调用自研引擎 engine.labeler.MaterialLabeler，
    客户薄壳里**没有任何** VLM 调用、提示词或引擎代码。
  - 严格限制全部在服务端强制（类型 / 大小 / 单元数 / 批量次数 / 一组图片上限三态）。
"""
import sys
import os
import json
import uuid
import asyncio
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
# 使 `import engine` 可用（自研引擎仅存在于服务端）
sys.path.insert(0, str(ROOT))

# 0) 先把 .env 注入 os.environ（引擎 config 会读 .env / os.environ）
try:
    from dotenv import load_dotenv
    load_dotenv(str(ROOT / ".env"), override=False)
except Exception:
    pass

import yaml
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header
from fastapi.responses import JSONResponse

# 1) 引入自研打标引擎（仅服务端，客户薄壳不含此代码）
from engine.labeler import MaterialLabeler, normalize_label, STD_LABELS
from engine.config import settings

app = FastAPI(title="电商多模态打标网关(服务端打标)", version="2.0")

# ---------------- 配置 ----------------
CONFIG_PATH = ROOT / "gateway_config.yaml"


def load_config():
    if CONFIG_PATH.exists():
        try:
            return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    return {}


CONFIG = load_config()

ADMIN_SECRET = CONFIG.get("admin_secret", "CHANGE_ME_admin_secret")
PUBLIC_BASE_URL = CONFIG.get("public_base_url", "http://127.0.0.1:8080")
LIMITS = CONFIG.get("limits", {})

MAX_IMAGE_SIZE_MB = float(LIMITS.get("max_image_size_mb", 50))
MAX_VIDEO_SIZE_MB = float(LIMITS.get("max_video_size_mb", 500))
ALLOWED_IMAGE = set(LIMITS.get("allowed_image_types", ".jpg,.jpeg,.png,.webp,.gif").lower().split(","))
ALLOWED_VIDEO = set(LIMITS.get("allowed_video_types", ".mp4,.mov,.avi,.mkv").lower().split(","))
MAX_UNITS_PER_BATCH = int(LIMITS.get("max_units_per_batch", 200))
MAX_UPLOADS_PER_CRED = int(LIMITS.get("max_uploads_per_credential", 1000))

# 一组图片上限三态：None=无上限 / 0=禁止图片 / 正整数=上限张数
_mipg = LIMITS.get("max_images_per_group", None)
MAX_IMAGES_PER_GROUP = None if _mipg in (None, "", "null", "None") else int(_mipg)

DEFAULT_MAX_BATCHES = int(CONFIG.get("credentials", {}).get("default_max_batches", 2))

# ---------------- 状态持久化 ----------------
STATE_PATH = ROOT / "gateway_state.json"


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"credentials": {}}


def save_state(s):
    STATE_PATH.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


STATE = load_state()

UPLOADS = ROOT / "uploads"
UPLOADS.mkdir(exist_ok=True)

# ---------------- 引擎单例 ----------------
_labeler = None


def get_labeler():
    global _labeler
    if _labeler is None:
        # custom_minmax 直接复用 .env 的 VLM_BASE_URL / VLM_API_KEY / VLM_MODEL
        _labeler = MaterialLabeler(provider="custom_minmax")
    return _labeler


# ---------------- 公共辅助 ----------------
def _cred_ok(cred):
    """返回凭证记录；无效/已吊销返回 None"""
    c = STATE["credentials"].get(cred)
    if not c or c.get("revoked"):
        return None
    return c


def _apply_image_limit():
    """按三态把一组图片上限写进引擎 settings（服务端强制）。"""
    if MAX_IMAGES_PER_GROUP == 0:
        settings.max_images = 0
    elif MAX_IMAGES_PER_GROUP is None:
        settings.max_images = 99999
    else:
        settings.max_images = MAX_IMAGES_PER_GROUP


# ---------------- 接口 ----------------
@app.get("/health")
def health():
    return {"status": "ok", "public_base_url": PUBLIC_BASE_URL, "mode": "server_side_labeling"}


@app.post("/admin/issue")
def admin_issue(body: dict, admin_secret: str = Header(None)):
    if admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail={"reason": "admin_unauthorized"})
    cust = body.get("customer", "anon")
    max_b = int(body.get("max_batches", DEFAULT_MAX_BATCHES))
    cred = "sk_" + uuid.uuid4().hex
    STATE["credentials"][cred] = {
        "customer": cust,
        "max_batches": max_b,
        "batches_used": 0,
        "uploads": 0,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "revoked": False,
    }
    save_state(STATE)
    return {"credential": cred, "max_batches": max_b, "customer": cust}


@app.post("/admin/revoke")
def admin_revoke(body: dict, admin_secret: str = Header(None)):
    if admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail={"reason": "admin_unauthorized"})
    cred = body.get("credential")
    c = STATE["credentials"].get(cred)
    if not c:
        raise HTTPException(status_code=404, detail={"reason": "credential_not_found"})
    c["revoked"] = True
    save_state(STATE)
    return {"revoked": True, "credential": cred}


@app.post("/api/v1/validate")
def validate(body: dict):
    cred = body.get("credential")
    c = _cred_ok(cred)
    if not c:
        raise HTTPException(status_code=401, detail={"reason": "invalid_credential"})
    return {
        "valid": True,
        "max_batches": c["max_batches"],
        "batches_used": c["batches_used"],
        "batches_left": c["max_batches"] - c["batches_used"],
        "uploads": c.get("uploads", 0),
    }


@app.post("/api/v1/upload")
async def upload(credential: str = Form(...), unit_id: str = Form(...), file: UploadFile = File(...)):
    c = _cred_ok(credential)
    if not c:
        raise HTTPException(status_code=401, detail={"reason": "invalid_credential"})

    # 严格限制（服务端强制）：类型 + 大小 + 单凭证上传数
    ext = Path(file.filename).suffix.lower()
    is_img = ext in ALLOWED_IMAGE
    is_vid = ext in ALLOWED_VIDEO
    if not (is_img or is_vid):
        raise HTTPException(
            status_code=400,
            detail={"reason": "unsupported_type", "ext": ext,
                    "allowed": sorted(ALLOWED_IMAGE | ALLOWED_VIDEO)},
        )
    data = await file.read()
    size_mb = len(data) / (1024 * 1024)
    if is_img and size_mb > MAX_IMAGE_SIZE_MB:
        raise HTTPException(status_code=413, detail={
            "reason": "image_too_large", "size_mb": round(size_mb, 1), "max_mb": MAX_IMAGE_SIZE_MB})
    if is_vid and size_mb > MAX_VIDEO_SIZE_MB:
        raise HTTPException(status_code=413, detail={
            "reason": "video_too_large", "size_mb": round(size_mb, 1), "max_mb": MAX_VIDEO_SIZE_MB})
    if c.get("uploads", 0) >= MAX_UPLOADS_PER_CRED:
        raise HTTPException(status_code=402, detail={
            "reason": "upload_quota_exceeded", "max": MAX_UPLOADS_PER_CRED})

    # 存盘：uploads/{unit_id}/{filename}（防路径遍历，仅取文件名）
    udir = UPLOADS / unit_id
    udir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename).name
    (udir / safe_name).write_bytes(data)

    c["uploads"] = c.get("uploads", 0) + 1
    save_state(STATE)
    return {
        "unit_id": unit_id,
        "file": safe_name,
        "media_type": "image" if is_img else "video",
        "size_mb": round(size_mb, 2),
    }


async def _label_unit(unit_id: str):
    """服务端执行单个单元的打标（调用自研引擎）。返回 (ok, payload)。"""
    udir = UPLOADS / unit_id
    if not udir.exists() or not any(udir.iterdir()):
        return False, {"unit_id": unit_id, "error": "unit_not_found"}
    # 一组图片上限三态（服务端强制）
    if MAX_IMAGES_PER_GROUP == 0:
        imgs = [p for p in udir.iterdir() if p.suffix.lower() in ALLOWED_IMAGE]
        if imgs:
            return False, {"unit_id": unit_id, "error": "images_forbidden"}
    _apply_image_limit()
    try:
        # label_single_folder 本身是协程，直接 await（端点也是 async）
        result = await get_labeler().label_single_folder(udir)
        return True, {"unit_id": unit_id, "result": result}
    except Exception as e:
        return False, {"unit_id": unit_id, "error": str(e)[:300]}


@app.post("/api/v1/label")
async def label(body: dict):
    cred = body.get("credential")
    c = _cred_ok(cred)
    if not c:
        raise HTTPException(status_code=401, detail={"reason": "invalid_credential"})
    if c["batches_used"] >= c["max_batches"]:
        raise HTTPException(status_code=402, detail={
            "reason": "quota_exceeded", "max_batches": c["max_batches"], "used": c["batches_used"]})
    unit_id = body.get("unit_id")
    ok, payload = await _label_unit(unit_id)
    if not ok and "unit_not_found" in payload.get("error", ""):
        raise HTTPException(status_code=400, detail=payload)
    if not ok and payload.get("error") == "images_forbidden":
        raise HTTPException(status_code=400, detail=payload)
    c["batches_used"] += 1
    save_state(STATE)
    payload["batches_left"] = c["max_batches"] - c["batches_used"]
    return payload


@app.post("/api/v1/batch")
async def batch(body: dict):
    cred = body.get("credential")
    c = _cred_ok(cred)
    if not c:
        raise HTTPException(status_code=401, detail={"reason": "invalid_credential"})
    units = body.get("units") or []
    if not units:
        raise HTTPException(status_code=400, detail={"reason": "empty_batch"})
    if len(units) > MAX_UNITS_PER_BATCH:
        raise HTTPException(status_code=400, detail={
            "reason": "too_many_units", "got": len(units), "max": MAX_UNITS_PER_BATCH})
    if c["batches_used"] >= c["max_batches"]:
        raise HTTPException(status_code=402, detail={
            "reason": "quota_exceeded", "max_batches": c["max_batches"], "used": c["batches_used"]})

    results = []
    for uid in units:
        ok, payload = await _label_unit(uid)
        results.append(payload)

    c["batches_used"] += 1
    save_state(STATE)
    return {
        "units": len(units),
        "results": results,
        "batches_left": c["max_batches"] - c["batches_used"],
    }


@app.post("/api/v1/report")
def report(body: dict):
    cred = body.get("credential")
    c = _cred_ok(cred)
    if not c:
        raise HTTPException(status_code=401, detail={"reason": "invalid_credential"})
    return {
        "credential": cred[:8] + "...",
        "customer": c.get("customer"),
        "max_batches": c["max_batches"],
        "batches_used": c["batches_used"],
        "uploads": c.get("uploads", 0),
        "status": "ok",
    }


# ---------------- 启动 ----------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
