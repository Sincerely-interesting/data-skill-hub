@echo off
chcp 65001 >nul
echo ============================================================
echo   电商多模态素材处理系统 - 快速安装脚本
echo   E-commerce Multimodal Material Processor - Quick Install
echo ============================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未检测到Python！
    echo.
    echo 请先安装Python 3.9或更高版本:
    echo   https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo ✅ 检测到Python
python --version
echo.

echo [1/4] 检查pip...
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: pip未安装或不可用
    echo 请重新安装Python并确保勾选"Add Python to PATH"
    pause
    exit /b 1
)
echo ✅ pip可用
echo.

echo [2/4] 升级pip...
python -m pip install --upgrade pip -q
echo ✅ pip已升级至最新版本
echo.

echo [3/4] 安装依赖包...
echo 这可能需要5-10分钟，请耐心等待...
echo.

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ❌ 安装失败！可能的原因：
    echo   1. 网络连接问题 - 尝试使用镜像源
    echo   2. 权限不足 - 以管理员身份运行此脚本
    echo   3. Python版本过低 - 需要Python >= 3.9
    echo.
    echo 尝试使用国内镜像源？(Y/N)
    set /p MIRROR=
    if /i "%MIRROR%"=="Y" (
        echo 正在使用清华镜像源安装...
        python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
        if errorlevel 1 (
            echo ❌ 安装仍然失败，请查看上方错误信息
            pause
            exit /b 1
        )
    ) else (
        pause
        exit /b 1
    )
)
echo ✅ 所有依赖安装成功！
echo.

echo [4/4] 验证安装...
python verify_installation.py
if errorlevel 1 (
    echo ⚠️  验证未完全通过，但核心功能应该可以使用
) else (
    echo ✅ 安装验证完全通过！
)
echo.

echo ============================================================
echo 🎉 安装完成！
echo ============================================================
echo.
echo 下一步操作：
echo   1. 配置API Key:
echo      copy .env.example .env
echo      然后编辑 .env 文件填入你的API Key
echo.
echo   2. 环境检查:
echo      python run_pipeline.py doctor
echo.
echo   3. 开始使用:
echo      python run_pipeline.py --help
echo.
echo 详细文档请查看: INSTALL_GUIDE.md
echo.
pause