"""
电商多模态素材处理 - REST API 服务（开发中）

> ⚠️ 此模块正在开发中，当前版本为占位实现。
> 完整功能预计在 v2.0 版本提供。

功能规划：
- POST /api/v1/label - 异步打标任务
- POST /api/v1/archive - 异步归档任务
- GET /api/v1/tasks/{task_id} - 查询任务状态
- GET /api/v1/health - 健康检查

依赖要求：
- fastapi>=0.104.0
- uvicorn[standard]>=0.24.0
- pydantic>=2.0.0

安装命令：pip install -r requirements.txt
"""

import sys
from pathlib import Path

# 确保能找到项目模块（支持多种运行方式）
_project_root = Path(__file__).parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


def _check_dependencies():
    """检查FastAPI等依赖是否已安装"""
    missing = []
    
    try:
        from fastapi import FastAPI
    except ImportError:
        missing.append('fastapi')
    
    try:
        from pydantic import BaseModel
    except ImportError:
        missing.append('pydantic')
    
    if missing:
        raise ImportError(
            f"缺少必要依赖: {', '.join(missing)}\n"
            f"请运行: pip install -r requirements.txt\n"
            f"或单独安装: pip install {' '.join(missing)}"
        )
    
    return True


try:
    _check_dependencies()
    
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    from typing import Optional
    import asyncio
    
    _DEPENDENCIES_AVAILABLE = True
    
except ImportError as e:
    _DEPENDENCIES_AVAILABLE = False
    _IMPORT_ERROR = str(e)


if _DEPENDENCIES_AVAILABLE:
    app = FastAPI(
        title="E-commerce Multimodal Material Processor API",
        version="0.1.0-dev",
        description="企业级电商多模态素材处理REST API服务（开发中）",
    )
    
    class HealthResponse(BaseModel):
        status: str
        version: str
        message: str
    
    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """健康检查端点"""
        return HealthResponse(
            status="development",
            version="0.1.0-dev",
            message="API service is under development. Please use CLI for now."
        )
    
    @app.get("/")
    async def root():
        """根路径"""
        return {
            "service": "E-commerce Multimodal Material Processor API",
            "status": "under_development",
            "version": "0.1.0-dev",
            "docs": "/docs",
            "message": "This API is currently under development. Use the CLI interface instead.",
            "cli_usage": "python run_pipeline.py --help"
        }
else:
    app = None


def get_app():
    """
    获取FastAPI应用实例（安全版本）
    
    Returns:
        FastAPI app or None: 如果依赖可用返回app实例，否则返回None
    """
    if not _DEPENDENCIES_AVAILABLE:
        print(f"⚠️  API Service 不可用: {_IMPORT_ERROR}")
        print("   请先安装依赖: pip install -r requirements.txt")
        return None
    return app


if __name__ == "__main__":
    if not _DEPENDENCIES_AVAILABLE:
        print("=" * 60)
        print("❌ API Service 无法启动")
        print(f"\n错误: {_IMPORT_ERROR}")
        print("\n解决方案:")
        print("  1. 安装所有依赖:")
        print("     pip install -r requirements.txt")
        print("\n  2. 或仅安装API相关依赖:")
        print("     pip install fastapi uvicorn pydantic pydantic_settings")
        print("\n  3. 使用CLI替代（推荐）:")
        print("     python run_pipeline.py --help")
        print("=" * 60)
        sys.exit(1)
    
    import uvicorn
    
    print("=" * 60)
    print("⚠️  API Service is UNDER DEVELOPMENT")
    print("   Current version: 0.1.0-dev")
    print("   For production use, please use the CLI interface:")
    print("   python run_pipeline.py --help")
    print("=" * 60)
    
    uvicorn.run(
        "src.ecommerce_processor.api_service:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )