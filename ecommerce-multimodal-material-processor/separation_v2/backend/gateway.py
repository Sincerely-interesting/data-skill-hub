#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后端网关 + 自研打标服务（服务端打标，密钥/提示词/高价值资产不出服务端）

设计要点（对应需求）：
  - 薄壳（客户侧）只做"对话与引用"：鉴权、本地打包素材、预检后单次上传压缩包、取回结果。
  - 打标逻辑全部在服务端执行：本网关直接调用自研引擎 engine.labeler.MaterialLabeler，
    客户薄壳里**没有任何** VLM 调用、提示词或引擎代码。
  - 素材以压缩包（zip + manifest 签名）单次上传；服务端在接收前 precheck 合规，
    接收后复核签名与逐文件 sha256，再逐单元打标。
  - 严格限制全部在服务端强制（类型 / 单文件大小 / 单元数 / 批量次数 / 压缩包总大小 / 一组图片上限三态）。
"""
import sys
import os
import json
import uuid
import asyncio
import hmac
import hashlib
import tempfile
import zipfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

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
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse

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
# 压缩包（单请求上传）总大小上限（MB）。同时修 1Panel/nginx 的 client_max_body_size
MAX_PACKAGE_SIZE_MB = float(LIMITS.get("max_package_size_mb", 1024))
# 分块上传的块大小（字节）。客户端按此切块，单块独立重试，规避 1M 慢链路整体超时。
CHUNK_SIZE = int(LIMITS.get("chunk_size_bytes", 2_000_000))

# 一组图片上限三态：None=无上限 / 0=禁止图片 / 正整数=上限张数
_mipg = LIMITS.get("max_images_per_group", None)
MAX_IMAGES_PER_GROUP = None if _mipg in (None, "", "null", "None") else int(_mipg)

DEFAULT_MAX_BATCHES = int(CONFIG.get("credentials", {}).get("default_max_batches", 2))
# 新签发 token 的可用天数（公开接口与 admin 接口一致生效；配置文件可控制）。
DEFAULT_VALID_DAYS = int(CONFIG.get("credentials", {}).get("default_valid_days", 3))
# 公开签发接口：每日全局上限（无口令，防止被刷）。配置文件可控制。
PUBLIC_ISSUE_DAILY_LIMIT = int(CONFIG.get("credentials", {}).get("public_issue_daily_limit", 30))
# 公开签发接口：每 IP 每日上限（防单 IP 刷光全局配额）。
PUBLIC_ISSUE_PER_IP_LIMIT = int(CONFIG.get("credentials", {}).get("public_issue_per_ip_limit", 3))
# 跨域（CORS）：前端静态页（Cloudflare Pages）JS 跨域调用公开签发接口所需。
# 配置文件 cors_allowed_origins 可限制来源；缺省 ["*"]（公开接口本就无口令，可接受）。
CORS_ALLOWED_ORIGINS = CONFIG.get("cors_allowed_origins", ["*"])

# 跨域：允许前端静态页（不同源）JS 调用公开签发接口 /api/v1/issue。
# 必须在 CORS_ALLOWED_ORIGINS 定义之后注册，否则启动即 NameError。
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# 分块上传的暂存目录（按 upload_token 分桶）
PARTS_DIR = UPLOADS / ".parts"

# 压缩包上传令牌（precheck 签发，upload 消费）。内存态即可。
PACKAGE_TOKENS = {}  # token -> {"cred":..,"expires":ts,"used":bool}


def _manifest_sig(key: str, m: dict) -> str:
    """对 manifest 做 HMAC-SHA256（自动剔除 signature 字段，幂等）。"""
    m2 = {k: v for k, v in m.items() if k != "signature"}
    body = json.dumps(m2, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hmac.new(key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()


def _issue_pkg_token(cred: str) -> str:
    t = uuid.uuid4().hex
    PACKAGE_TOKENS[t] = {
        "cred": cred,
        "expires": datetime.now(timezone.utc).timestamp() + 600,
        "used": False,
    }
    return t


def _pkg_token_ok(t: str):
    r = PACKAGE_TOKENS.get(t)
    if not r or r["used"]:
        return None
    if datetime.now(timezone.utc).timestamp() > r["expires"]:
        return None
    return r


def _safe_unit_id(uid: str) -> bool:
    """防止压缩包内单元路径遍历。"""
    if not uid or "/" in uid or "\\" in uid or uid.startswith("."):
        return False
    return True

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
    """返回凭证记录；无效/已吊销/已过期返回 None"""
    c = STATE["credentials"].get(cred)
    if not c or c.get("revoked"):
        return None
    exp = c.get("expires_at")
    if exp:
        try:
            if datetime.fromisoformat(exp) < datetime.now(timezone.utc):
                return None  # 已超过可用天数
        except Exception:
            pass
    return c


def _apply_image_limit():
    """按三态把一组图片上限写进引擎 settings（服务端强制）。"""
    if MAX_IMAGES_PER_GROUP == 0:
        settings.max_images = 0
    elif MAX_IMAGES_PER_GROUP is None:
        settings.max_images = 99999
    else:
        settings.max_images = MAX_IMAGES_PER_GROUP


# ---------------- 公开签发每日限流（全局 30/天 + 每 IP 3/天） ----------------
def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _client_ip(request: Request) -> str:
    """取真实客户端 IP：优先 X-Forwarded-For（走代理/Cloudflare 时），否则取直连 peer。"""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _public_issue_state() -> dict:
    """返回今天的签发计数结构；非今天则重置（count=全局, by_ip=每 IP）。"""
    today = _today_utc()
    d = STATE.get("public_issue_daily") or {}
    if d.get("date") != today:
        d = {"date": today, "count": 0, "by_ip": {}}
    return d


def _public_issue_count_today() -> int:
    return int(_public_issue_state().get("count", 0))


def _public_issue_count_ip(ip: str) -> int:
    return int(_public_issue_state().get("by_ip", {}).get(ip, 0))


def _inc_public_issue(ip: str):
    d = _public_issue_state()
    d["count"] = int(d.get("count", 0)) + 1
    by_ip = d.setdefault("by_ip", {})
    by_ip[ip] = int(by_ip.get(ip, 0)) + 1
    STATE["public_issue_daily"] = d


def _issue_credential(customer: str, max_batches: int, valid_days: int) -> dict:
    """签发一个 token（admin 与公开接口共用）。返回给调用方的字段。"""
    cred = "sk_" + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    # valid_days<=0 视为不限制（向后兼容旧 admin token）
    expires_at = (now + timedelta(days=valid_days)).isoformat() if valid_days and valid_days > 0 else None
    STATE["credentials"][cred] = {
        "customer": customer,
        "max_batches": max_batches,
        "batches_used": 0,
        "uploads": 0,
        "issued_at": now.isoformat(),
        "revoked": False,
        "valid_days": valid_days,
        "expires_at": expires_at,
    }
    save_state(STATE)
    return {
        "credential": cred,
        "max_batches": max_batches,
        "customer": customer,
        "valid_days": valid_days,
        "expires_at": expires_at,
    }


# ---------------- 接口 ----------------
@app.get("/health")
def health():
    return {"status": "ok", "public_base_url": PUBLIC_BASE_URL, "mode": "server_side_labeling"}


# 技能包下载：对外提供 skill.zip 下载（前端"下载 Skill"按钮指向此接口）。
# 文件路径可在 gateway_config.yaml 用 skill_zip_path 配置；相对路径按 backend 目录解析，默认 backend/skill.zip。
def _resolve_skill_zip_path() -> Path:
    p = Path(CONFIG.get("skill_zip_path") or "skill.zip")
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p


@app.get("/api/v1/skill/download")
def skill_download():
    path = _resolve_skill_zip_path()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail={"reason": "skill_zip_not_found"})
    return FileResponse(
        path=str(path),
        media_type="application/zip",
        filename="skill.zip",
    )


@app.post("/admin/issue")
def admin_issue(body: dict, admin_secret: str = Header(None)):
    if admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail={"reason": "admin_unauthorized"})
    cust = body.get("customer", "anon")
    max_b = int(body.get("max_batches", DEFAULT_MAX_BATCHES))
    valid_days = int(body.get("valid_days", DEFAULT_VALID_DAYS))
    return _issue_credential(cust, max_b, valid_days)


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


@app.post("/api/v1/issue")
def public_issue(request: Request, body: dict = None):
    """公开签发 token：无口令。
    双层限流：① 每日全局上限 PUBLIC_ISSUE_DAILY_LIMIT（默认 30）；② 每 IP 每日上限 PUBLIC_ISSUE_PER_IP_LIMIT（默认 3）。
    customer / max_batches / valid_days 全部锁死走服务端配置，客户端不可覆盖。"""
    ip = _client_ip(request)
    if _public_issue_count_today() >= PUBLIC_ISSUE_DAILY_LIMIT:
        raise HTTPException(status_code=429, detail={
            "reason": "daily_limit_exceeded", "scope": "global", "limit": PUBLIC_ISSUE_DAILY_LIMIT})
    if _public_issue_count_ip(ip) >= PUBLIC_ISSUE_PER_IP_LIMIT:
        raise HTTPException(status_code=429, detail={
            "reason": "daily_limit_exceeded", "scope": "ip", "limit": PUBLIC_ISSUE_PER_IP_LIMIT})
    _inc_public_issue(ip)
    return _issue_credential("public", DEFAULT_MAX_BATCHES, DEFAULT_VALID_DAYS)


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
        "valid_days": c.get("valid_days"),
        "expires_at": c.get("expires_at"),
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


# ---------------- 压缩包协议（先验证合规，再接收） ----------------
# 客户端把整批素材打成 zip（含 manifest.json），本地预检后：
#   1) 先 POST manifest 到 /package/precheck（服务端在接收大包前先查合规）
#   2) 通过则拿到 upload_token，再单次上传 zip 到 /package/upload
# 压缩包内含可验证信息：manifest 的 HMAC 签名 + 每文件 sha256。
PKG_FORMAT = "ecom-tag-pkg/1"


@app.post("/api/v1/package/precheck")
async def package_precheck(body: dict):
    cred = body.get("credential")
    c = _cred_ok(cred)
    if not c:
        raise HTTPException(status_code=401, detail={"reason": "invalid_credential"})
    m = body.get("manifest") or {}
    if m.get("format") != PKG_FORMAT:
        raise HTTPException(status_code=400, detail={
            "reason": "unsupported_format", "got": m.get("format")})
    uc = int(m.get("unit_count", 0))
    if uc > MAX_UNITS_PER_BATCH:
        raise HTTPException(status_code=400, detail={
            "reason": "too_many_units", "got": uc, "max": MAX_UNITS_PER_BATCH})
    tb = int(m.get("total_bytes", 0))
    if tb > MAX_PACKAGE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail={
            "reason": "package_too_large", "got_mb": round(tb / 1048576, 1),
            "max_mb": MAX_PACKAGE_SIZE_MB})
    if c["batches_used"] >= c["max_batches"]:
        raise HTTPException(status_code=402, detail={
            "reason": "quota_exceeded", "max_batches": c["max_batches"], "used": c["batches_used"]})
    if _manifest_sig(cred, m) != m.get("signature"):
        raise HTTPException(status_code=400, detail={"reason": "signature_invalid"})
    token = _issue_pkg_token(cred)
    return {
        "accept": True,
        "upload_token": token,
        "max_bytes": int(MAX_PACKAGE_SIZE_MB * 1024 * 1024),
        "ttl": 600,
        "supports_chunks": True,
        "chunk_size": CHUNK_SIZE,
    }


async def _process_package_bytes(data: bytes, rt: dict) -> dict:
    """接收后复核（深度防御）+ 解包 + 逐文件 sha256/类型校验 + 逐单元打标。
    单次上传、分块 commit 两条路径共用此逻辑。返回与 /package/upload 一致的响应体。"""
    tmp = UPLOADS / ("pkg_%s.zip" % uuid.uuid4().hex[:8])
    tmp.write_bytes(data)
    try:
        # ---- 接收后复核（深度防御）----
        try:
            z = zipfile.ZipFile(tmp)
        except Exception:
            raise HTTPException(status_code=400, detail={"reason": "zip_invalid"})
        if z.testzip() is not None:
            raise HTTPException(status_code=400, detail={"reason": "zip_corrupt"})
        names = z.namelist()
        if "manifest.json" not in names:
            raise HTTPException(status_code=400, detail={"reason": "missing_manifest"})
        m = json.loads(z.read("manifest.json").decode("utf-8"))
        if _manifest_sig(rt["cred"], m) != m.get("signature"):
            raise HTTPException(status_code=400, detail={"reason": "signature_invalid"})
        if len(m.get("units", [])) > MAX_UNITS_PER_BATCH:
            raise HTTPException(status_code=400, detail={
                "reason": "too_many_units", "got": len(m.get("units", [])),
                "max": MAX_UNITS_PER_BATCH})
        # ---- 解包 + 逐文件校验 sha256 + 类型，落盘到 uploads/{unit_id} ----
        done = []
        for u in m["units"]:
            uid = u["unit_id"]
            if not _safe_unit_id(uid):
                raise HTTPException(status_code=400, detail={"reason": "bad_unit_id", "unit": uid})
            udir = UPLOADS / uid
            udir.mkdir(parents=True, exist_ok=True)
            manifest_files = {f["name"]: f for f in u["files"]}
            for zname in names:
                if not zname.startswith(uid + "/"):
                    continue
                fname = zname[len(uid) + 1:]
                if not fname or fname not in manifest_files:
                    raise HTTPException(status_code=400, detail={"reason": "unexpected_file", "file": zname})
                content = z.read(zname)
                if hashlib.sha256(content).hexdigest() != manifest_files[fname]["sha256"]:
                    raise HTTPException(status_code=400, detail={"reason": "file_hash_mismatch", "file": zname})
                ext = Path(fname).suffix.lower()
                if ext not in (ALLOWED_IMAGE | ALLOWED_VIDEO):
                    raise HTTPException(status_code=400, detail={"reason": "unsupported_type", "ext": ext})
                # 单文件大小上限（服务端强制，让"大小上限"在压缩包路径也生效）
                sz = manifest_files[fname]["bytes"]
                if ext in ALLOWED_IMAGE and sz > MAX_IMAGE_SIZE_MB * 1048576:
                    raise HTTPException(status_code=413, detail={
                        "reason": "image_too_large", "size_mb": round(sz / 1048576, 1), "max_mb": MAX_IMAGE_SIZE_MB})
                if ext in ALLOWED_VIDEO and sz > MAX_VIDEO_SIZE_MB * 1048576:
                    raise HTTPException(status_code=413, detail={
                        "reason": "video_too_large", "size_mb": round(sz / 1048576, 1), "max_mb": MAX_VIDEO_SIZE_MB})
                (udir / fname).write_bytes(content)
            done.append(uid)
        # ---- 逐单元打标（复用既有服务端引擎）----
        results = []
        for uid in done:
            ok, payload = await _label_unit(uid)
            results.append(payload)
        rt["used"] = True
        c = _cred_ok(rt["cred"])
        c["batches_used"] += 1
        c["uploads"] = c.get("uploads", 0) + sum(len(u["files"]) for u in m["units"])
        save_state(STATE)
        return {
            "units": len(done),
            "results": results,
            "batches_left": c["max_batches"] - c["batches_used"],
        }
    finally:
        try:
            tmp.unlink()
        except Exception:
            pass


@app.post("/api/v1/package/upload")
async def package_upload(token: str = Form(...), file: UploadFile = File(...)):
    """单次上传（小包 / 不支持分块的旧客户端兜底）。"""
    rt = _pkg_token_ok(token)
    if not rt:
        raise HTTPException(status_code=401, detail={"reason": "invalid_or_expired_token"})
    data = await file.read()
    return await _process_package_bytes(data, rt)


@app.post("/api/v1/package/chunk")
async def package_chunk(token: str = Form(...), index: int = Form(...),
                        file: UploadFile = File(...)):
    """接收分块（第 index 块，0-based）。按 token 暂存，幂等可重传（断点续传）。"""
    rt = _pkg_token_ok(token)
    if not rt:
        raise HTTPException(status_code=401, detail={"reason": "invalid_or_expired_token"})
    if index < 0 or index > 1_000_000:
        raise HTTPException(status_code=400, detail={"reason": "bad_chunk_index"})
    data = await file.read()
    part_dir = PARTS_DIR / token
    part_dir.mkdir(parents=True, exist_ok=True)
    (part_dir / ("%08d.part" % index)).write_bytes(data)
    total = sum(p.stat().st_size for p in part_dir.iterdir() if p.name.endswith(".part"))
    return {"ok": True, "index": index, "bytes": len(data), "received": total,
            "chunks": len([p for p in part_dir.iterdir() if p.name.endswith(".part")])}


@app.get("/api/v1/package/status")
def package_status(token: str):
    """查询已收到的分块（断点续传用）。"""
    rt = _pkg_token_ok(token)
    if not rt:
        raise HTTPException(status_code=401, detail={"reason": "invalid_or_expired_token"})
    part_dir = PARTS_DIR / token
    if not part_dir.exists():
        return {"received": 0, "chunks": 0, "indices": []}
    idx = sorted(int(p.name[:8]) for p in part_dir.iterdir() if p.name.endswith(".part"))
    total = sum(p.stat().st_size for p in part_dir.iterdir() if p.name.endswith(".part"))
    return {"received": total, "chunks": len(idx), "indices": idx}


@app.post("/api/v1/package/commit")
async def package_commit(body: dict):
    """全部分块到齐后提交：校验整包 sha256 -> 重组 -> 解包打标。"""
    token = body.get("token")
    rt = _pkg_token_ok(token)
    if not rt:
        raise HTTPException(status_code=401, detail={"reason": "invalid_or_expired_token"})
    package_sha256 = body.get("package_sha256", "")
    part_dir = PARTS_DIR / token
    parts = sorted(part_dir.iterdir(), key=lambda p: int(p.name[:8])) if part_dir.exists() else []
    if not parts:
        raise HTTPException(status_code=400, detail={"reason": "no_chunks"})
    buf = b"".join(p.read_bytes() for p in parts)
    if hashlib.sha256(buf).hexdigest() != package_sha256:
        raise HTTPException(status_code=400, detail={"reason": "package_hash_mismatch"})
    try:
        return await _process_package_bytes(buf, rt)
    finally:
        try:
            for p in parts:
                p.unlink()
            part_dir.rmdir()
        except Exception:
            pass


# ---------------- 启动 ----------------
if __name__ == "__main__":
    import uvicorn, os
    cert = os.getenv("SSL_CERTFILE", "/证书/fullchain.pem")
    key = os.getenv("SSL_KEYFILE", "/证书/privkey.pem")
    uvicorn.run(app, host="0.0.0.0", port=8080,
                ssl_certfile=cert, ssl_keyfile=key)
