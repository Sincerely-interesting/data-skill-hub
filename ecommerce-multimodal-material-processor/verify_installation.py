"""
快速验证脚本 - 检查项目是否可独立运行
"""
import sys
from pathlib import Path

def check_file_exists(filepath: str, description: str) -> bool:
    """检查文件是否存在"""
    path = Path(filepath)
    if path.exists():
        print(f"✅ {description}: {filepath}")
        return True
    else:
        print(f"❌ 缺失: {description} - {filepath}")
        return False

def main():
    print("\n" + "=" * 60)
    print("🔍 项目独立性验证")
    print("=" * 60 + "\n")
    
    checks = [
        ("SKILL.md", "主Skill文件"),
        ("README.md", "项目说明文档"),
        ("requirements.txt", "Python依赖列表"),
        ("setup.py", "安装配置"),
        (".env.example", "环境变量模板"),
        (".gitignore", "Git忽略规则"),
        
        # 核心源码
        ("src/ecommerce_processor/__init__.py", "包初始化"),
        ("src/ecommerce_processor/config.py", "配置管理模块"),
        ("src/ecommerce_processor/deps_checker.py", "环境检查器"),
        ("src/ecommerce_processor/video_utils.py", "视频抽帧工具"),
        ("src/ecommerce_processor/mcp_client.py", "MCP协议客户端(完整实现)"),
        ("src/ecommerce_processor/labeler.py", "打标引擎(含MCP支持)"),
        ("src/ecommerce_processor/archiver.py", "归档报告生成器"),
        ("src/ecommerce_processor/downloader.py", "素材下载器"),
        ("src/ecommerce_processor/exporter.py", "Excel导出器"),
        ("src/ecommerce_processor/api_service.py", "API服务模块(开发中)"),
        
        # CLI入口
        ("run_pipeline.py", "统一CLI入口(根目录)"),
        
        # 参考文档
        ("references/architecture-guide.md", "架构技术文档"),
        ("references/labeling-criteria.md", "标签判定标准"),
        ("references/auto-collection-roadmap.md", "自动采集路线图"),
        
        # 示例和工具
        ("examples/demo-conversation.md", "示例对话"),
    ]
    
    passed = 0
    failed = 0
    
    for filepath, description in checks:
        if check_file_exists(filepath, description):
            passed += 1
        else:
            failed += 1
    
    print("\n" + "-" * 60)
    print(f"验证结果: {passed}/{len(checks)} 通过")
    
    if failed == 0:
        print("✅ 项目结构完整，可以独立运行！\n")
        print("下一步操作:")
        print("  1. pip install -r requirements.txt")
        print("  2. cp .env.example .env && 编辑 .env 配置API Key")
        print("  3. python run_pipeline.py doctor\n")
        return 0
    else:
        print(f"\n❌ 有 {failed} 个文件缺失，请检查！\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())