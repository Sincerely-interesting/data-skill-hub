#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
薄壳客户端 —— 纯接口层（"对话与引用"），不含任何打标逻辑、密钥或提示词。

设计边界（对应需求）：
  - 本客户端**不持有**任何模型密钥（密钥只在后端服务端）。
  - 本客户端**不包含** VLM 调用、提示词或自研引擎代码。
  - 所有打标都在后端服务端完成；本客户端只负责：
        1) 鉴权（auth，查询配额/有效期）
        2) 把整批素材本地打包成 zip（含 manifest 的 HMAC 签名与逐文件 sha256）
        3) 本地预检 -> 服务端 precheck -> 分块可续传上传压缩包（batch）
           （precheck 返回 supports_chunks 时走分块：单块独立重试+断点续传；
            不支持时回退单次上传。分块是应对 1M 慢链路被反代整体 RST 的关键）
        4) 打标成功后把服务端随响应返回的结构化结果落地为本地
           labeling_result.json，并（可选）本地生成 PDF 分析报告
        5) 取回配额回执（report）
  - 严格限制由服务端强制；本客户端仅透传，无法绕过。

核心（鉴权/打包/上传/落地 JSON）仅用 Python 标准库，无需 pip install。
PDF 生成是**可选辅助**：同目录 reporter.py 需要 reportlab；缺失时自动跳过
（只落地 JSON），不影响打标本身。
"""
import os
import sys
import json
import time
import uuid
import hmac
import hashlib
import zipfile
import tempfile
import argparse
import subprocess
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
import shutil
from datetime import datetime, timezone

# ---------------- 配置（只填两个必填，其余可选） ----------------
ENV = {}


def _load_env():
    p = Path(__file__).resolve().parent / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            ENV[k.strip()] = v.strip()


_load_env()

GATEWAY_BASE_URL = os.environ.get("GATEWAY_BASE_URL") or ENV.get("GATEWAY_BASE_URL", "")
CREDENTIAL = os.environ.get("CREDENTIAL") or ENV.get("CREDENTIAL", "")
# 以下仅为客户端预检提示；服务端为权威强制方
MAX_IMAGES_PER_GROUP = ENV.get("MAX_IMAGES_PER_GROUP", "")
COMPRESS_BUDGET_MB = float(ENV.get("COMPRESS_BUDGET_MB", "0") or 0)
FFMPEG_PATH = ENV.get("FFMPEG_PATH", "") or "ffmpeg"
# 压缩包本地预检上限（MB）；0 = 不限制。服务端另有强制上限。
MAX_PACKAGE_SIZE_MB = float(ENV.get("MAX_PACKAGE_SIZE_MB", "0") or 0)
# 单元数上限（与服务端 MAX_UNITS_PER_BATCH 对齐；仅客户端预检提示，服务端为权威强制方）。
MAX_UNITS_PER_BATCH = int(ENV.get("MAX_UNITS_PER_BATCH", "200") or 200)
# 分块上传参数（应对 1M 慢链路整体超时被反代 RST）：
#   单块重试次数 + 指数退避基数（秒）。服务端 precheck 返回 chunk_size 为准。
CHUNK_RETRY = int(ENV.get("CHUNK_RETRY", "5") or 5)
CHUNK_BACKOFF = float(ENV.get("CHUNK_BACKOFF", "1.5") or 1.5)
# commit 阶段服务端要重组整包 + 逐单元打标，大包（数十单元/含视频）耗时可达数分钟，
# 故 commit 超时默认 7200s（2小时，可用环境变量覆盖），远大于普通请求的 120s。
COMMIT_TIMEOUT = int(ENV.get("COMMIT_TIMEOUT", "7200") or 7200)

# ---------------- 后端接口路径（唯一事实源，镜像 backend/gateway.py 的路由定义） ----------------
# 说明：本客户端所有请求路径统一在此集中维护，与后端 gateway.py 的 @app.post/@app.get
#       路由一一对应；后端若调整路径，只需改这里一处。功能不变，仅消除散落的硬编码字面量。
#       （对齐 gateway.py 行号：validate@332, report@368, precheck@392, upload@503,
#         chunk@513, status@531, commit@545）
API_PATHS = {
    "validate":         "/api/v1/validate",          # 鉴权/校验凭证
    "report":           "/api/v1/report",            # 取回配额回执
    "package_precheck": "/api/v1/package/precheck",  # 服务端合规预检 + 下发 upload_token
    "package_upload":   "/api/v1/package/upload",    # 旧服务端单次整包上传（兜底）
    "package_chunk":    "/api/v1/package/chunk",     # 分块上传单块
    "package_status":   "/api/v1/package/status",    # 断点续传：查询已收块
    "package_commit":   "/api/v1/package/commit",    # 全部块到齐后提交重组打标
}


def _api_url(base, key):
    """拼接后端接口完整 URL。base=GATEWAY_BASE_URL；key=API_PATHS 键名。"""
    return base.rstrip("/") + API_PATHS[key]


def _unwrap_detail(b):
    """FastAPI 的 HTTPException(detail={...}) 会被包成 {"detail": {...}}。
    这里把 detail 内的字段提到顶层，保证 resp.get("reason") 等取值正常。"""
    if isinstance(b, dict) and isinstance(b.get("detail"), dict):
        out = dict(b)
        for k, v in b["detail"].items():
            out.setdefault(k, v)
        return out
    return b


def die(reason, action="stop", message=None, **extra):
    out = {"action": action, "reason": reason}
    if message:
        out["message"] = message
    out.update(extra)
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(1 if action == "stop" else 0)


def _post_json(url, payload, timeout=120):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), r.status
    except urllib.error.HTTPError as e:
        try:
            body = _unwrap_detail(json.loads(e.read().decode("utf-8")))
        except Exception:
            body = {"raw": e.read().decode("utf-8", "ignore")[:300]}
        return body, e.code
    except Exception as e:
        return {"reason": "gateway_unreachable", "error": str(e)[:200]}, 0


def _mpost(url, fields, files, timeout=300):
    """multipart/form-data POST（纯标准库实现）"""
    boundary = "----wb%s" % uuid.uuid4().hex
    CRLF = b"\r\n"
    parts = []
    for k, v in fields.items():
        parts.append(b"--" + boundary.encode() + CRLF)
        parts.append(('Content-Disposition: form-data; name="%s"' % k).encode() + CRLF + CRLF)
        parts.append(("%s" % v).encode() + CRLF)
    for f in files:
        name, filename, fdata, mime = f["name"], f["filename"], f["data"], f["mime"]
        parts.append(b"--" + boundary.encode() + CRLF)
        parts.append(('Content-Disposition: form-data; name="%s"; filename="%s"'
                     % (name, filename)).encode() + CRLF)
        parts.append(("Content-Type: %s" % mime).encode() + CRLF + CRLF)
        parts.append(fdata)
        parts.append(CRLF)
    parts.append(b"--" + boundary.encode() + b"--" + CRLF)
    body = b"".join(parts)
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), r.status
    except urllib.error.HTTPError as e:
        try:
            b = _unwrap_detail(json.loads(e.read().decode("utf-8")))
        except Exception:
            b = {"raw": e.read().decode("utf-8", "ignore")[:300]}
        return b, e.code
    except Exception as e:
        return {"reason": "gateway_unreachable", "error": str(e)[:200]}, 0


def _get_json(url, timeout=60):
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), r.status
    except urllib.error.HTTPError as e:
        try:
            body = _unwrap_detail(json.loads(e.read().decode("utf-8")))
        except Exception:
            body = {"raw": e.read().decode("utf-8", "ignore")[:300]}
        return body, e.code
    except Exception as e:
        return {"reason": "gateway_unreachable", "error": str(e)[:200]}, 0


def _upload_in_chunks(base, token, data, chunk_size):
    """分块上传：断点续传（先查已收块）+ 单块指数退避重试 + 整包 sha256 commit。
    这是应对 1M 慢链路整体超时被反向代理 RST 的关键：每块单独短连接，
    即便某块失败也只重传那一块，不会前功尽弃。返回 (resp, code)。"""
    total = len(data)
    nchunks = (total + chunk_size - 1) // chunk_size
    pkg_sha = hashlib.sha256(data).hexdigest()
    # 1) 断点续传：查服务端已收到哪些块
    st, sc = _get_json(_api_url(base, "package_status") + "?token=" + urllib.parse.quote(token))
    have = set(st.get("indices", [])) if sc == 200 else set()
    # 2) 逐块上传，跳过已收，失败指数退避重试
    for i in range(nchunks):
        if i in have:
            continue
        piece = data[i * chunk_size:(i + 1) * chunk_size]
        last_err = None
        for attempt in range(CHUNK_RETRY):
            resp, code = _mpost(
                _api_url(base, "package_chunk"),
                {"token": token, "index": i},
                [{"name": "file", "filename": "chunk_%d.bin" % i,
                  "data": piece, "mime": "application/octet-stream"}],
                timeout=300,
            )
            if code == 200:
                break
            last_err = (resp, code)
            # 401=token失效/被误判则不再重试
            if code == 401:
                return resp, code
            time.sleep(CHUNK_BACKOFF * (2 ** attempt))
        else:
            r = last_err[0] if last_err else {"reason": "chunk_upload_failed"}
            r.setdefault("reason", "chunk_upload_failed")
            r["chunk_index"] = i
            return r, (last_err[1] if last_err else 0)
    # 3) 全部块到齐 -> commit（服务端校验整包 sha256 后重组打标）
    #    大包（数十单元、含视频）服务端重组+打标可达数分钟，commit 必须用长超时，
    #    否则 120s 就断连导致整批静默失败（小包几秒可过、故早期冒烟测不出）。
    return _post_json(_api_url(base, "package_commit"),
                      {"token": token, "package_sha256": pkg_sha},
                      timeout=COMMIT_TIMEOUT)


# ---------------- 压缩包协议（先本地预检 -> 服务端 precheck -> 单次传包） ----------------
PKG_FORMAT = "ecom-tag-pkg/1"
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".mov", ".avi", ".mkv"}


def _canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sig(key, m):
    """HMAC-SHA256（自动剔除 signature 字段，幂等）。key=凭证字符串（客户端/服务端共有）。"""
    m2 = {k: v for k, v in m.items() if k != "signature"}
    return hmac.new(key.encode("utf-8"), _canonical(m2).encode("utf-8"),
                 hashlib.sha256).hexdigest()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_package(root):
    """把 root 打成 zip（临时文件），内含 manifest.json（可验证信息）。返回 (zip_path, manifest)。"""
    root = Path(root)
    units = _discover_units(root)
    manifest_units, total, folders = [], 0, []
    for uid in sorted(units):
        fs = units[uid]
        files = []
        for f in sorted(fs, key=lambda p: p.name):
            ext = f.suffix.lower()
            if ext not in ALLOWED_EXT:
                die("unsupported_type_client", action="continue_error",
                     message="单元 %s 含不支持类型 %s" % (uid, ext))
            b = f.stat().st_size
            files.append({"name": f.name, "bytes": b, "sha256": _sha256_file(f)})
            total += b
        manifest_units.append({"unit_id": uid, "files": files})
        folders.append((uid, fs))
    manifest = {
        "format": PKG_FORMAT,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "unit_count": len(manifest_units),
        "total_bytes": total,
        "units": manifest_units,
    }
    manifest["signature"] = _sig(CREDENTIAL, manifest)  # 先签名（不含 signature），再序列化
    tmp = Path(tempfile.gettempdir()) / ("pkg_%s.zip" % uuid.uuid4().hex[:8])
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", _canonical(manifest))
        for uid, fs in folders:
            for f in sorted(fs, key=lambda p: p.name):
                z.writestr("%s/%s" % (uid, f.name), f.read_bytes())
    return tmp, manifest


def _package_precheck_local(pkg, manifest):
    """上传前本地预检（合规）。不通过则直接 die。"""
    try:
        with zipfile.ZipFile(pkg) as z:
            if z.testzip() is not None:
                die("zip_corrupt", action="continue_error",
                     message="zip 损坏: %s" % z.testzip())
    except Exception as e:
        die("zip_invalid", action="continue_error", message=str(e)[:200])
    size_mb = pkg.stat().st_size / (1024 * 1024)
    if MAX_PACKAGE_SIZE_MB and size_mb > MAX_PACKAGE_SIZE_MB:
        die("package_too_large_client", action="continue_error",
             message="压缩包 %.1fMB 超过客户端上限 %.1fMB" % (size_mb, MAX_PACKAGE_SIZE_MB))
    if manifest["unit_count"] > MAX_UNITS_PER_BATCH:
        die("too_many_units", action="continue_error",
            message=("素材单元数 %d 已超过规定上限 %d。后端不会接收执行（单包最多 %d 个单元）。"
                     "建议：把素材按子文件夹拆分为多个 ≤%d 单元的批次，分别运行 batch --dir 打标；"
                     "或仅对其中一部分文件夹打标。"
                     % (manifest["unit_count"], MAX_UNITS_PER_BATCH,
                        MAX_UNITS_PER_BATCH, MAX_UNITS_PER_BATCH)))
    if _sig(CREDENTIAL, manifest) != manifest.get("signature"):
        die("signature_invalid_client", action="continue_error", message="manifest 签名不符")
    return True


# ---------------- 环境预检：扫描磁盘，自动选最富裕且够用的盘 ----------------
# 目的：避免客户把大素材放在系统盘（如 C:）时，打包临时文件/输出把磁盘写爆，
#        导致整批失败（真实踩坑：C 盘沙箱满 -> WinError 112 / No space left on device）。
# 薄壳客户端零依赖，仅用标准库 shutil.disk_usage 跨平台扫描。
# 行为：扫描所有盘 -> 选 free 最大且满足安全余量的盘作为工作/输出目录 -> 把打包临时
#        目录也指到该盘 -> 先把"预检决策"print 给终端客户（提示）-> 再执行打包上传。
# 终端客户可用 --no-auto-drive 关闭自动降级（严格用其指定/素材所在盘），
#        或 --confirm-drive 在手动场景阻塞等待确认。

def _scan_drives():
    """扫描所有挂载盘，返回 [(path, free_bytes, total_bytes), ...]，跨平台。"""
    drives = []
    if os.name == "nt":
        for d in range(ord("A"), ord("Z") + 1):
            p = "%s:/" % chr(d)
            try:
                u = shutil.disk_usage(p)
                drives.append((p, u.free, u.total))
            except Exception:
                pass
    else:
        cand = ["/", "/data", "/mnt", "/media"]
        mtab = "/proc/mounts"
        if os.path.exists(mtab):
            try:
                for line in open(mtab, encoding="utf-8", errors="ignore"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1].startswith("/") and parts[0].startswith("/dev"):
                        cand.append(parts[1])
            except Exception:
                pass
        seen = set()
        for p in cand:
            if p in seen:
                continue
            seen.add(p)
            try:
                u = shutil.disk_usage(p)
                drives.append((p, u.free, u.total))
            except Exception:
                pass
    return drives


def _material_size(dir_path):
    """估算素材目录总字节（标准库 walk）。"""
    total = 0
    try:
        for root, _, files in os.walk(dir_path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
    except Exception:
        pass
    return total


def _drive_free_of(path, drives):
    """返回 path 所在盘的 free（扫描遗漏时实时补查该盘根；仍不行返回 0）。"""
    p = str(Path(path).resolve())
    low = p.lower()
    best, bl = 0, -1
    for (dp, free, _) in drives:
        if low.startswith(dp.lower()) and len(dp) > bl:
            best, bl = free, len(dp)
    if best > 0:
        return best
    # 扫描遗漏（网络盘/特殊盘/未就绪等）：实时补查该盘根
    try:
        drive = os.path.splitdrive(p)[0]
        if drive:
            return shutil.disk_usage(drive + "\\").free
    except Exception:
        pass
    return 0


def _plan_work(args):
    """环境预检核心：扫描 -> 选盘 -> 决定工作/输出目录 -> 设 TEMP。
    返回 (plan_dict, out_dir:Path, tmp_dir:Path)。"""
    mat = Path(args.dir).resolve()
    mat_size = _material_size(mat)
    # 安全余量：打包临时(≈素材) + 整包 + 输出PDF(≈素材*0.1) + 缓冲 200MB
    need = int(mat_size * 2.2) + 200 * 1024 * 1024
    drives = _scan_drives()

    auto_override = False
    reason = ""
    work_drive = None
    explicit = getattr(args, "out_dir", None) or ""
    no_auto = getattr(args, "no_auto_drive", False)

    if explicit and not no_auto:
        ef = _drive_free_of(explicit, drives)
        if ef > need:
            work_drive = Path(explicit).resolve()
            reason = "使用客户指定输出目录 %s（空间充足 %.1fGB）" % (explicit, ef / 1e9)
        else:
            auto_override = True  # 落到下方"自动选盘"分支

    if work_drive is None:
        cands = [(p, free, tot) for (p, free, tot) in drives if free > need]
        cands.sort(key=lambda x: -x[1])
        if cands:
            wp, wf, _ = cands[0]
            if explicit:
                reason = ("客户指定盘空间不足（余 %.1fGB < 需求 %.1fGB），已自动改到最富裕盘 %s（余 %.1fGB）"
                          % (ef / 1e9, need / 1e9, wp, wf / 1e9))
            else:
                reason = "自动选最富裕盘 %s（余 %.1fGB）作为工作/输出目录" % (wp, wf / 1e9)
            work_drive = Path(wp) / "ecom_tag_out" / (mat.name or "out")
        else:
            drives.sort(key=lambda x: -x[1])
            wp, wf, _ = drives[0] if drives else ("(none)", 0, 0)
            auto_override = True
            work_drive = Path(wp) / "ecom_tag_out" / (mat.name or "out")
            reason = ("警告：所有盘空间均不足预估需求 %.1fGB，已用最富裕盘 %s（余 %.1fGB），可能失败"
                      % (need / 1e9, wp, wf / 1e9))

    work_drive.mkdir(parents=True, exist_ok=True)
    # 打包临时目录放到工作盘，避免写爆系统盘 Temp（关键防护点）
    tmp_dir = work_drive.parent / ("_ecom_tmp_%d" % os.getpid())
    try:
        tmp_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        tmp_dir = work_drive
    os.environ["TEMP"] = str(tmp_dir)
    os.environ["TMPDIR"] = str(tmp_dir)
    os.environ["TMP"] = str(tmp_dir)

    out_dir = work_drive if not explicit else Path(explicit).resolve()
    plan = {
        "action": "env_precheck",
        "material_dir": str(mat),
        "material_gb": round(mat_size / 1e9, 2),
        "need_gb": round(need / 1e9, 2),
        "work_drive": str(work_drive),
        "temp_dir": str(tmp_dir),
        "drive_free_gb": round(_drive_free_of(work_drive, drives) / 1e9, 2),
        "auto_override": auto_override,
        "message": reason,
    }
    return plan, out_dir, tmp_dir


# ---------------- 子命令 ----------------
def cmd_auth(args):
    if not GATEWAY_BASE_URL:
        die("no_gateway", message="未配置 GATEWAY_BASE_URL")
    if not CREDENTIAL:
        die("no_credential", message="未配置 CREDENTIAL")
    body, code = _post_json(_api_url(GATEWAY_BASE_URL, "validate"),
                              {"credential": CREDENTIAL})
    if code == 401:
        die("invalid_credential", message=str(body.get("reason", "")))
    if code != 200:
        die("auth_failed", action="continue_error", message=str(body)[:300])
    body["action"] = "auth_ok"
    print(json.dumps(body, ensure_ascii=False))


def _discover_units(root):
    root = Path(root)
    if not root.is_dir():
        die("bad_dir", message="目录不存在: %s" % root)
    units = {}  # unit_id -> [file paths]
    # 子文件夹 = 图片组单元
    for sub in sorted(p for p in root.iterdir() if p.is_dir()):
        files = [f for f in sub.iterdir() if f.is_file()]
        if files:
            units[sub.name] = files
    # 顶层视频文件 = 视频单元
    for f in sorted(root.iterdir()):
        if f.is_file() and f.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv"):
            units[f.stem] = [f]
    if not units:
        die("empty_batch", message="未发现任何合规单元（子文件夹图片组 / 顶层视频）")
    return units


def cmd_batch(args):
    """整批素材 -> 本地打成压缩包 -> 本地预检 -> 服务端 precheck -> 单次传包。"""
    if not GATEWAY_BASE_URL:
        die("no_gateway", message="未配置 GATEWAY_BASE_URL")
    if not CREDENTIAL:
        die("no_credential", message="未配置 CREDENTIAL")
    # ---- 环境预检：扫描磁盘，自动选最富裕且够用的盘作为工作/输出目录 ----
    plan, out_dir, tmp_dir = _plan_work(args)
    print(json.dumps(plan, ensure_ascii=False))  # 先把"选盘决策"提示给终端客户，再执行
    if getattr(args, "confirm_drive", False):
        try:
            ans = input("将使用工作盘 %s（余 %.1fGB）。确认继续? [y/N] "
                        % (plan["work_drive"], plan["drive_free_gb"])).strip().lower()
        except Exception:
            ans = ""
        if ans not in ("y", "yes"):
            die("drive_unconfirmed", action="continue_error", message="客户未确认工作盘")
    if not getattr(args, "out_dir", None):
        args.out_dir = str(out_dir)
    # 友好预检：单元数超限时尽早提示（避免先把超大目录整体打包才发现被后端拒绝）
    _early_units = _discover_units(Path(args.dir).resolve())
    if len(_early_units) > MAX_UNITS_PER_BATCH:
        die("too_many_units", action="continue_error",
            message=("素材单元数 %d 已超过规定上限 %d。后端不会接收执行（单包最多 %d 个单元）。"
                     "建议：把素材按子文件夹拆分为多个 ≤%d 单元的批次，分别运行 batch --dir 打标；"
                     "或仅对其中一部分文件夹打标。"
                     % (len(_early_units), MAX_UNITS_PER_BATCH,
                        MAX_UNITS_PER_BATCH, MAX_UNITS_PER_BATCH)))
    pkg, manifest = _build_package(args.dir)
    _package_precheck_local(pkg, manifest)
    # 1) 服务端在接收大包前先查合规
    body, code = _post_json(_api_url(GATEWAY_BASE_URL, "package_precheck"),
                             {"credential": CREDENTIAL, "manifest": manifest})
    if code == 401:
        die("invalid_credential")
    if code != 200:
        if body.get("reason") == "quota_exceeded":
            die("quota_exceeded", action="continue_error",
                message=("当前 Token 的打标额度已用完（已用 %s / 上限 %s），后端拒绝接收。"
                         "请重新申请试用 Token，或用新的 Token 重试。"
                         % (body.get("used"), body.get("max_batches"))))
        die(body.get("reason", "precheck_failed"), action="continue_error",
            message=str(body)[:300])
    token = body.get("upload_token")
    base = GATEWAY_BASE_URL.rstrip("/")
    data = pkg.read_bytes()
    # 2) 上传压缩包（含可验证信息：manifest 签名 + 每文件 sha256）
    #    优先分块上传（服务端支持时）：单块短连接 + 断点续传 + 指数退避，
    #    规避 1M 慢链路整体上传耗时超过反向代理超时被 RST 的问题。
    if body.get("supports_chunks"):
        chunk_size = int(body.get("chunk_size") or 2_000_000)
        resp, code2 = _upload_in_chunks(base, token, data, chunk_size)
    else:
        # 旧服务端兜底：单次上传
        resp, code2 = _mpost(_api_url(base, "package_upload"),
                             {"token": token},
                             [{"name": "file", "filename": pkg.name,
                               "data": data, "mime": "application/zip"}],
                             timeout=3600)
    try:
        pkg.unlink()
    except Exception:
        pass
    if code2 == 401:
        die("invalid_credential")
    if code2 in (400, 402, 413):
        if resp.get("reason") == "quota_exceeded":
            die("quota_exceeded", action="continue_error",
                message=("当前 Token 的打标额度已用完（已用 %s / 上限 %s），后端拒绝接收。"
                         "请重新申请试用 Token，或用新的 Token 重试。"
                         % (resp.get("used"), resp.get("max_batches"))))
        die(resp.get("reason", "package_upload_failed"), action="continue_error",
            message=str(resp)[:300])
    if code2 != 200:
        die("package_upload_failed", action="continue_error", message=str(resp)[:300])

    results = resp.get("results") or []
    out = {"action": "batch_ok", "units": manifest["unit_count"],
            "results": results,
            "batches_left": resp.get("batches_left")}

    # ---- 打标成功：把服务端返回的结构化结果落地本地（服务端不留缓存）----
    out_dir = Path(args.out_dir) if getattr(args, "out_dir", None) else Path(args.dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = {}
    for item in results:
        r = item.get("result") or {}
        mid = r.get("material_id") or item.get("unit_id")
        if mid and isinstance(r, dict) and r:
            r.setdefault("material_id", mid)
            cache[mid] = r
    json_path = out_dir / "labeling_result.json"
    try:
        json_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        out["result_json"] = str(json_path)
    except Exception as e:
        out["result_json_error"] = str(e)[:200]

    # ---- 可选：本地生成 PDF 分析报告（reporter.py + reportlab）----
    if cache and not getattr(args, "no_pdf", False):
        pdf_path = out_dir / "素材分析报告.pdf"
        pdf_ok, pdf_msg = _make_pdf(json_path, pdf_path)
        if pdf_ok:
            out["report_pdf"] = str(pdf_path)
        else:
            out["report_pdf_skipped"] = pdf_msg

    print(json.dumps(out, ensure_ascii=False))


def _ensure_reportlab():
    """确保 reportlab 可用：已装直接返回；否则尝试自动 pip 安装一次，失败返回 False。
    受环境变量 AUTO_INSTALL_DEPS（默认 1）控制，设为 0 可关闭自动安装。"""
    try:
        import reportlab  # noqa: F401
        return True
    except Exception:
        pass
    if os.environ.get("AUTO_INSTALL_DEPS", "1") == "0":
        return False
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "reportlab"],
                       capture_output=True, text=True, timeout=300)
        import reportlab  # noqa: F401
        return True
    except Exception:
        return False


def _make_pdf(cache_json: Path, pdf_out: Path):
    """调用同目录 reporter.py 生成 PDF；返回 (ok, message)。
    PDF 是可选辅助：reportlab 缺失时自动尝试安装，装不上则优雅跳过，不影响打标。"""
    if not _ensure_reportlab():
        return False, "未安装 reportlab 且自动安装失败，已跳过 PDF（手动 pip install reportlab 后重跑即可）"
    reporter = Path(__file__).resolve().parent / "reporter.py"
    if not reporter.exists():
        return False, "reporter.py 不存在（PDF 辅助脚本未随包分发）"
    try:
        proc = subprocess.run(
            [sys.executable, str(reporter), "-c", str(cache_json), "-o", str(pdf_out)],
            capture_output=True, text=True, timeout=300)
    except Exception as e:
        return False, "调用 reporter 失败: %s" % (str(e)[:150])
    if proc.returncode == 0 and pdf_out.exists():
        return True, "ok"
    err = (proc.stderr or proc.stdout or "").strip()
    if "reportlab" in err.lower() or "No module named" in err:
        return False, "未安装 reportlab，已跳过 PDF（pip install reportlab 后重跑即可）"
    return False, "PDF 生成失败: %s" % (err[-200:] if err else "unknown")


def cmd_pack(args):
    """仅本地打包 + 预检 + 打印 manifest（不上传），用于自查素材是否合规。"""
    if not CREDENTIAL:
        die("no_credential", message="未配置 CREDENTIAL")
    # 仍做环境预检（把打包临时目录放到最富裕盘，避免写爆系统盘）
    plan, _, _ = _plan_work(args)
    print(json.dumps(plan, ensure_ascii=False))
    pkg, manifest = _build_package(args.dir)
    _package_precheck_local(pkg, manifest)
    size_mb = pkg.stat().st_size / (1024 * 1024)
    manifest["_package_bytes"] = pkg.stat().st_size
    manifest["_package_mb"] = round(size_mb, 2)
    try:
        pkg.unlink()
    except Exception:
        pass
    out = {"action": "pack_ok", "package_mb": round(size_mb, 2),
            "manifest": manifest}
    print(json.dumps(out, ensure_ascii=False))


def cmd_report(args):
    if not GATEWAY_BASE_URL:
        die("no_gateway", message="未配置 GATEWAY_BASE_URL")
    if not CREDENTIAL:
        die("no_credential", message="未配置 CREDENTIAL")
    body, code = _post_json(_api_url(GATEWAY_BASE_URL, "report"),
                              {"credential": CREDENTIAL})
    if code == 401:
        die("invalid_credential")
    if code != 200:
        die("report_failed", action="continue_error", message=str(body)[:300])
    body["action"] = "report_ok"
    print(json.dumps(body, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="电商打标薄壳客户端（纯接口层）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth")
    p_ba = sub.add_parser("batch")
    p_ba.add_argument("--dir", required=True)
    p_ba.add_argument("--out-dir", dest="out_dir", default="",
                      help="结果 JSON / PDF 输出目录（默认为最富裕且够用的盘）")
    p_ba.add_argument("--no-pdf", dest="no_pdf", action="store_true",
                      help="只落地 labeling_result.json，不生成 PDF")
    p_ba.add_argument("--no-auto-drive", dest="no_auto_drive", action="store_true",
                      help="禁用自动选盘（严格用 --out-dir 指定或素材所在盘，空间不足仅警告）")
    p_ba.add_argument("--confirm-drive", dest="confirm_drive", action="store_true",
                      help="打印预检后阻塞等待客户确认（手动场景；自动化请勿开启）")
    p_pk = sub.add_parser("pack")
    p_pk.add_argument("--dir", required=True)
    p_pk.add_argument("--no-auto-drive", dest="no_auto_drive", action="store_true",
                      help="禁用自动选盘（空间不足仅警告）")
    p_pk.add_argument("--confirm-drive", dest="confirm_drive", action="store_true",
                      help="打印预检后阻塞等待确认（手动场景）")
    sub.add_parser("report")

    args = ap.parse_args()
    {"auth": cmd_auth, "batch": cmd_batch, "pack": cmd_pack,
     "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
