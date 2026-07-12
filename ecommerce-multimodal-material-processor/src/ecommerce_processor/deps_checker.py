"""
环境依赖检查器 - 验证运行环境和依赖
"""
import sys
import subprocess
from pathlib import Path
from typing import Tuple, List, Dict, Optional
from loguru import logger

from .config import settings

class DependencyChecker:
    """依赖检查类"""

    REQUIRED_PACKAGES = [
        "openai",
        "pandas",
        "tqdm",
        "Pillow",
        "opencv-python",
        "python-dotenv",
        "pydantic",
        "loguru",
    ]

    OPTIONAL_PACKAGES = {
        "sentence-transformers": "向量检索（Embedding生成）",
        "lance": "向量数据库（LanceDB）",
        "fastapi": "检索服务（FastAPI）",
        "uvicorn": "检索服务（ASGI服务器）",

    }

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.results: Dict[str, bool] = {}

    def check_python_version(self) -> bool:
        """检查Python版本（需要3.10+）"""
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 10):
            error_msg = f"Python版本过低: {version.major}.{version.minor}.{version.micro}，需要 >= 3.10"
            self.errors.append(error_msg)
            logger.error(error_msg)
            return False

        logger.success(f"✅ Python版本: {version.major}.{version.minor}.{version.micro}")
        self.results["python_version"] = True
        return True

    # 包名(发行版) → 模块名(可导入) 映射表
    PACKAGE_TO_MODULE = {
        "Pillow": "PIL",
        "opencv-python": "cv2",
        "opencv-python-headless": "cv2",
        "python-dotenv": "dotenv",
        "openai-whisper": "whisper",
    }
    
    def check_package(self, package_name: str) -> bool:
        """检查单个包是否已安装"""
        try:
            module_name = self.PACKAGE_TO_MODULE.get(package_name, package_name.replace("-", "_"))
            logger.success(f"✅ {package_name}")
            return True
        except ImportError:
            logger.error(f"❌ {package_name} 未安装")
            return False

    def check_required_packages(self) -> bool:
        """检查必需的Python包"""
        all_ok = True
        for package in self.REQUIRED_PACKAGES:
            if not self.check_package(package):
                self.errors.append(f"缺少必需包: {package}，请执行 `pip install {package}`")
                all_ok = False
                self.results[package] = False
            else:
                self.results[package] = True

        return all_ok

    def check_optional_packages(self) -> None:
        """检查可选的Python包（缺失时仅警告）"""
        for package, description in self.OPTIONAL_PACKAGES.items():
            if not self.check_package(package):
                warning_msg = f"可选包未安装: {package} ({description})"
                self.warnings.append(warning_msg)
                logger.warning(f"⚠️  {warning_msg}")
                self.results[package] = False
            else:
                self.results[package] = True

    def check_ffmpeg(self) -> bool:
        """检查ffmpeg是否可用"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # 提取版本号
                first_line = result.stdout.split("\n")[0]
                logger.success(f"✅ ffmpeg: {first_line}")
                self.results["ffmpeg"] = True
                return True
            else:
                raise RuntimeError("ffmpeg返回错误")
        except FileNotFoundError:
            error_msg = "ffmpeg 未安装或不在PATH中"
            self.errors.append(error_msg + "（视频处理功能将不可用）")
            logger.error(f"❌ {error_msg}")
            self.results["ffmpeg"] = False
            return False
        except Exception as e:
            error_msg = f"ffmpeg 检查失败: {e}"
            self.warnings.append(error_msg)
            logger.warning(f"⚠️  {error_msg}")
            self.results["ffmpeg"] = False
            return False

    def check_env_config(self) -> bool:
        """
        检查 .env 配置文件和API Key
        
        Returns:
            bool: 配置是否有效
        """
        try:
            configured_providers = settings.validate_provider_config()
            provider_list = ", ".join(configured_providers)
            logger.success(f"✅ 已配置Provider: {provider_list}")
            self.results["env_config"] = True
            return True
        except ValueError as e:
            error_msg = f".env配置错误: {e}"
            self.errors.append(error_msg)
            logger.error(f"❌ {error_msg}")
            self.results["env_config"] = False
            return False

    def check_output_directories(self) -> bool:
        """创建输出目录（如果不存在）"""
        dirs_to_check = [
            settings.archive_output_dir,
            settings.excel_export_dir,
            settings.cache_dir,
        ]

        all_ok = True
        for dir_path in dirs_to_check:
            try:
                Path(dir_path).mkdir(parents=True, exist_ok=True)
                logger.success(f"✅ 输出目录: {dir_path}/")
                self.results[str(dir_path)] = True
            except Exception as e:
                error_msg = f"无法创建目录 {dir_path}: {e}"
                self.errors.append(error_msg)
                logger.error(f"❌ {error_msg}")
                self.results[str(dir_path)] = False
                all_ok = False

        return all_ok

    def run_full_check(self) -> Tuple[bool, List[str], List[str]]:
        """
        执行完整的环境检查
        
        Returns:
            Tuple[bool, List[str], List[str]]: (是否通过, 错误列表, 警告列表)
        """
        logger.info("🔧 开始环境预检...")

        checks = [
            ("Python版本", self.check_python_version),
            ("必需包", self.check_required_packages),
            ("可选包", self.check_optional_packages),
            ("ffmpeg", self.check_ffmpeg),
            (".env配置", self.check_env_config),
            ("输出目录", self.check_output_directories),
        ]

        for name, check_func in checks:
            logger.info(f"\n--- 检查 {name} ---")
            check_func()

        # 输出汇总
        logger.info("\n" + "=" * 60)
        if not self.errors:
            logger.success("🎉 环境检查全部通过！可以开始处理。")
            return True, [], self.warnings
        else:
            logger.error(f"❌ 环境检查发现 {len(self.errors)} 个问题：")
            for i, error in enumerate(self.errors, 1):
                logger.error(f"  {i}. {error}")

            if self.warnings:
                logger.warning(f"\n⚠️  另有 {len(self.warnings)} 个警告：")
                for i, warning in enumerate(self.warnings, 1):
                    logger.warning(f"  {i}. {warning}")

            return False, self.errors, self.warnings

def check_dependencies() -> bool:
    """
    便捷函数：执行完整的环境检查
        
    Returns:
        bool: 环境是否就绪
    """
    checker = DependencyChecker()
    passed, errors, warnings = checker.run_full_check()
    return passed

if __name__ == "__main__":
    success = check_dependencies()
    sys.exit(0 if success else 1)

