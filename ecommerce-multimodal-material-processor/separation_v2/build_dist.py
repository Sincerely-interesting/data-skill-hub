#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建两个分发包（全部从 separation_v2/ 生成，落进 separation_v2/dist/）：

  1) ecommerce-tagging-gateway-v2.zip  —— 后端（你侧部署，持有密钥 + 自研引擎）
       包含：gateway.py / gateway_config.yaml / requirements_server.txt / static/
             engine/（自研打标服务，受保护资产）/ prompts/ / .env（真实密钥，overlay）
  2) ecommerce-tagging-skill-v2.zip       —— 薄壳（给客户，零密钥）
       包含：skill_client.py / .env.example / SKILL.md / requirements.txt

排除：__pycache__ / *.pyc / .git / gateway_state.json / uploads/ / cache/ / *.log
"""
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
SHELL = ROOT / "thin_shell"
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)

EXCLUDE_DIRS = {"__pycache__", ".git", "uploads", "cache"}
EXCLUDE_FILES = {"gateway_state.json"}
EXCLUDE_SUFFIXES = {".pyc", ".log"}


def _walk(src: Path, prefix_base: Path, top_dir: str):
    """生成 (磁盘绝对路径, zip内相对路径) 列表，zip 顶层为 top_dir/。"""
    out = []
    for dp, dnames, fnames in os.walk(src):
        dnames[:] = [d for d in dnames if d not in EXCLUDE_DIRS]
        d = Path(dp)
        for fn in fnames:
            f = d / fn
            if fn in EXCLUDE_FILES or f.suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            rel = f.relative_to(prefix_base)
            out.append((f, f"{top_dir}/{rel.as_posix()}"))
    return out


def build(zip_name: str, src: Path, top_dir: str, exclude_names=frozenset()):
    zip_path = DIST / zip_name
    items = _walk(src, src, top_dir)
    if exclude_names:
        items = [(f, a) for f, a in items if f.name not in exclude_names]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f, arcname in items:
            z.write(f, arcname)
    size = zip_path.stat().st_size / 1024
    print(f"  ✔ {zip_name}  ({size:.1f} KB, {len(items)} files)")
    return zip_path


if __name__ == "__main__":
    print("构建分发包 ->", DIST)
    # 后端：保留 .env（真实密钥在服务端，这是设计意图）
    build("ecommerce-tagging-gateway-v2.zip", BACKEND, "ecommerce-tagging-gateway-v2")
    # 薄壳：排除 .env（只发 .env.example，绝不带任何凭证/密钥）
    build("ecommerce-tagging-skill-v2.zip", SHELL, "ecommerce-tagging-skill-v2",
          exclude_names={".env"})
    print("完成。后端包含 engine/(自研服务)+.env(密钥)；薄壳包零密钥。")
