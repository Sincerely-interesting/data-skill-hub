#!/bin/bash

# ============================================================
# 电商多模态素材处理系统 - 快速安装脚本 (Linux/macOS)
# E-commerce Multimodal Material Processor - Quick Install
# ============================================================

set -e

echo "============================================================"
echo "  电商多模态素材处理系统 - 快速安装脚本"
echo "  E-commerce Multimodal Material Processor - Quick Install"
echo "============================================================"
echo ""

# 检查Python
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "❌ 错误: 未检测到Python！"
        echo ""
        echo "请先安装Python 3.9或更高版本:"
        echo "  macOS: brew install python@3.11"
        echo "  Linux: sudo apt install python3.11"
        exit 1
    fi
    PYTHON_CMD="python"
else
    PYTHON_CMD="python3"
fi

echo "✅ 检测到Python: $($PYTHON_CMD --version)"
echo ""

# 检查pip
echo "[1/4] 检查pip..."
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo "❌ 错误: pip未安装或不可用"
    echo "请运行: $PYTHON_CMD -m ensurepip --upgrade"
    exit 1
fi
echo "✅ pip可用: $($PYTHON_CMD -m pip --version)"
echo ""

# 升级pip
echo "[2/4] 升级pip..."
$PYTHON_CMD -m pip install --upgrade pip -q
echo "✅ pip已升级至最新版本"
echo ""

# 安装依赖
echo "[3/4] 安装依赖包..."
echo "这可能需要5-10分钟，请耐心等待..."
echo ""

if $PYTHON_CMD -m pip install -r requirements.txt; then
    echo ""
    echo "✅ 所有依赖安装成功！"
else
    echo ""
    echo "❌ 安装失败！可能的原因："
    echo "  1. 网络连接问题 - 尝试使用镜像源"
    echo "  2. 权限不足 - 尝试 sudo 或使用虚拟环境"
    echo "  3. Python版本过低 - 需要Python >= 3.9"
    echo ""
    
    read -p "尝试使用清华镜像源？(Y/N): " MIRROR
    if [[ "$MIRROR" =~ ^[Yy]$ ]]; then
        echo "正在使用清华镜像源安装..."
        $PYTHON_CMD -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || {
            echo "❌ 安装仍然失败，请查看上方错误信息"
            exit 1
        }
    else
        exit 1
    fi
fi
echo ""

# 验证安装
echo "[4/4] 验证安装..."
if $PYTHON_CMD verify_installation.py; then
    echo "✅ 安装验证完全通过！"
else
    echo "⚠️  验证未完全通过，但核心功能应该可以使用"
fi
echo ""

echo "============================================================"
echo "🎉 安装完成！"
echo "============================================================"
echo ""
echo "下一步操作："
echo "  1. 配置API Key:"
echo "     cp .env.example .env"
echo "     然后编辑 .env 文件填入你的API Key"
echo ""
echo "  2. 环境检查:"
echo "     $PYTHON_CMD run_pipeline.py doctor"
echo ""
echo "  3. 开始使用:"
echo "     $PYTHON_CMD run_pipeline.py --help"
echo ""
echo "详细文档请查看: INSTALL_GUIDE.md"
echo ""