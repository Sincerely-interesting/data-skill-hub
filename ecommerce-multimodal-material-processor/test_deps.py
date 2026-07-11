#!/usr/bin/env python
"""快速依赖检查"""
import sys

deps = [
    ('fastapi', 'FastAPI web framework'),
    ('uvicorn', 'ASGI server'),
    ('pydantic', 'Data validation'),
    ('pydantic_settings', 'Settings management'),
    ('httpx', 'HTTP client'),
    ('pandas', 'Data processing'),
    ('Pillow', 'Image processing'),
    ('loguru', 'Logging'),
    ('tqdm', 'Progress bars'),
]

print("=" * 60)
print("🔍 依赖检查")
print("=" * 60)

missing = []
for module, desc in deps:
    try:
        __import__(module)
        print(f"✅ {module:20s} - {desc}")
    except ImportError:
        print(f"❌ {module:20s} - {desc} (未安装)")
        missing.append(module)

print("=" * 60)
if missing:
    print(f"⚠️  缺少 {len(missing)} 个依赖:")
    for m in missing:
        print(f"   - {m}")
    print("\n安装命令: pip install -r requirements.txt")
    sys.exit(1)
else:
    print("✅ 所有依赖已安装")
    sys.exit(0)