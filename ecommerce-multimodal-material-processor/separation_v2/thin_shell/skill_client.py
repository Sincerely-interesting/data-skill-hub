#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
薄壳客户端 —— 纯接口层（"对话与引用"），不含任何打标逻辑、密钥或提示词。

设计边界（对应需求）：
  - 本客户端**不持有**任何模型密钥（密钥只在后端服务端）。
  - 本客户端**不包含** VLM 调用、提示词或自研引擎代码。
  - 所有打标都在后端服务端完成；本客户端只负责：
        1) 鉴权（auth）
        2) 上传素材（upload，服务端强制类型/大小限制）
        3) 发起打标请求（label / batch，服务端执行）
        4) 取回结构化结果（report）
  - 严格限制由服务端强制；本客户端仅透传，无法绕过。

仅用 Python 标准库（urllib / argparse / json），无需 pip install。
"""
import os
import sys
import json
import uuid
import argparse
import urllib.request
import urllib.error
import mimetypes
from pathlib import Path

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


def die(reason, action="stop", message=None, **extra):
    out = {"action": action, "reason": reason}
    if message:
        out["message"] = message
    out.update(extra)
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(1 if action == "stop" else 0)


def _post_json(url, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode("utf-8")), r.status
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = {"raw": e.read().decode("utf-8", "ignore")[:300]}
        return body, e.code
    except Exception as e:
        return {"reason": "gateway_unreachable", "error": str(e)[:200]}, 0


def _mpost(url, fields, files):
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
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read().decode("utf-8")), r.status
    except urllib.error.HTTPError as e:
        try:
            b = json.loads(e.read().decode("utf-8"))
        except Exception:
            b = {"raw": e.read().decode("utf-8", "ignore")[:300]}
        return b, e.code
    except Exception as e:
        return {"reason": "gateway_unreachable", "error": str(e)[:200]}, 0


# ---------------- 子命令 ----------------
def _upload_file(path, unit_id):
    p = Path(path)
    if not p.exists():
        die("bad_file", message="文件不存在: %s" % path)
    data = p.read_bytes()
    mime = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    fields = {"credential": CREDENTIAL, "unit_id": unit_id}
    files = [{"name": "file", "filename": p.name, "data": data, "mime": mime}]
    return _mpost(GATEWAY_BASE_URL.rstrip("/") + "/api/v1/upload", fields, files)


def cmd_auth(args):
    if not GATEWAY_BASE_URL:
        die("no_gateway", message="未配置 GATEWAY_BASE_URL")
    if not CREDENTIAL:
        die("no_credential", message="未配置 CREDENTIAL")
    body, code = _post_json(GATEWAY_BASE_URL.rstrip("/") + "/api/v1/validate",
                              {"credential": CREDENTIAL})
    if code == 401:
        die("invalid_credential", message=str(body.get("reason", "")))
    if code != 200:
        die("auth_failed", action="continue_error", message=str(body)[:300])
    body["action"] = "auth_ok"
    print(json.dumps(body, ensure_ascii=False))


def cmd_upload(args):
    if not GATEWAY_BASE_URL:
        die("no_gateway", message="未配置 GATEWAY_BASE_URL")
    if not CREDENTIAL:
        die("no_credential", message="未配置 CREDENTIAL")
    unit = args.unit or ("u_" + uuid.uuid4().hex[:8])
    body, code = _upload_file(args.file, unit)
    if code == 401:
        die("invalid_credential")
    if code in (400, 413, 402):
        die(body.get("reason", "upload_failed"), action="continue_error",
            message=str(body)[:300])
    if code != 200:
        die("upload_failed", action="continue_error", message=str(body)[:300])
    body["action"] = "upload_ok"
    print(json.dumps(body, ensure_ascii=False))


def cmd_label(args):
    if not GATEWAY_BASE_URL:
        die("no_gateway", message="未配置 GATEWAY_BASE_URL")
    if not CREDENTIAL:
        die("no_credential", message="未配置 CREDENTIAL")
    unit = "u_" + uuid.uuid4().hex[:8]
    body, code = _upload_file(args.file, unit)
    if code != 200:
        die(body.get("reason", "upload_failed"), action="continue_error",
            message=str(body)[:300])
    body2, code2 = _post_json(GATEWAY_BASE_URL.rstrip("/") + "/api/v1/label",
                                 {"credential": CREDENTIAL, "unit_id": unit})
    if code2 == 401:
        die("invalid_credential")
    if code2 == 402:
        die("quota_exceeded", **{k: v for k, v in body2.items() if k not in ("action",)})
    if code2 != 200:
        die("label_failed", action="continue_error", message=str(body2)[:300])
    out = {"action": "label_ok", "unit_id": unit,
            "result": body2.get("result"),
            "batches_left": body2.get("batches_left")}
    print(json.dumps(out, ensure_ascii=False))


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
    if not GATEWAY_BASE_URL:
        die("no_gateway", message="未配置 GATEWAY_BASE_URL")
    if not CREDENTIAL:
        die("no_credential", message="未配置 CREDENTIAL")
    units = _discover_units(args.dir)

    # 客户端预检提示（服务端为权威强制方）
    if MAX_IMAGES_PER_GROUP not in ("", None):
        n = int(MAX_IMAGES_PER_GROUP)
        if n == 0:
            for uid, fs in units.items():
                if all(f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif") for f in fs):
                    die("images_forbidden_client", action="continue_error",
                        message="单元 %s 含图片但配置禁止图片" % uid)
        elif n > 0:
            for uid, fs in units.items():
                imgs = [f for f in fs if f.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif")]
                if len(imgs) > n:
                    print(json.dumps({"action": "continue_warn", "reason": "too_many_images",
                                     "unit": uid, "got": len(imgs), "max": n}, ensure_ascii=False))

    # 上传全部文件（服务端强制类型/大小）
    uploaded_units = []
    for uid, fs in units.items():
        for f in fs:
            body, code = _upload_file(f, uid)
            if code != 200:
                die(body.get("reason", "upload_failed"), action="continue_error",
                    message="单元 %s 上传失败: %s" % (uid, str(body)[:200]))
        uploaded_units.append(uid)

    # 发起批量打标（服务端执行）
    body2, code2 = _post_json(GATEWAY_BASE_URL.rstrip("/") + "/api/v1/batch",
                                 {"credential": CREDENTIAL, "units": uploaded_units})
    if code2 == 401:
        die("invalid_credential")
    if code2 == 402:
        die("quota_exceeded", **{k: v for k, v in body2.items() if k not in ("action",)})
    if code2 in (400,):
        die(body2.get("reason", "batch_failed"), action="continue_error",
            message=str(body2)[:300])
    if code2 != 200:
        die("batch_failed", action="continue_error", message=str(body2)[:300])
    out = {"action": "batch_ok", "units": len(uploaded_units),
            "results": body2.get("results"),
            "batches_left": body2.get("batches_left")}
    print(json.dumps(out, ensure_ascii=False))


def cmd_report(args):
    if not GATEWAY_BASE_URL:
        die("no_gateway", message="未配置 GATEWAY_BASE_URL")
    if not CREDENTIAL:
        die("no_credential", message="未配置 CREDENTIAL")
    body, code = _post_json(GATEWAY_BASE_URL.rstrip("/") + "/api/v1/report",
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
    p_up = sub.add_parser("upload")
    p_up.add_argument("--file", required=True)
    p_up.add_argument("--unit", default=None)
    p_la = sub.add_parser("label")
    p_la.add_argument("--file", required=True)
    p_ba = sub.add_parser("batch")
    p_ba.add_argument("--dir", required=True)
    sub.add_parser("report")

    args = ap.parse_args()
    {"auth": cmd_auth, "upload": cmd_upload, "label": cmd_label,
     "batch": cmd_batch, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
