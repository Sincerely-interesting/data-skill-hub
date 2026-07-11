#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自建LM Studio服务器连接测试脚本
用于验证 .env 配置是否正确
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

try:
    from ecommerce_processor.config import settings
    from ecommerce_processor.labeler import MaterialLabeler
    import httpx
except ImportError as e:
    print(f"❌ 导入失败: {e}")
    print("请先安装依赖: pip install -r requirements.txt")
    sys.exit(1)


async def test_connection():
    """测试与LM Studio服务器的连接"""
    
    print("=" * 60)
    print("🔧 LM Studio 服务器连接测试")
    print("=" * 60)
    print()
    
    # 1. 显示当前配置
    print("📋 当前配置:")
    print(f"  服务器URL: {settings.custom_minmax_url}")
    print(f"  API Key: {settings.custom_minmax_api_key[:20]}...{settings.custom_minmax_api_key[-10:]}")
    print(f"  模型名称: {settings.llm_model}")
    print(f"  超时时间: {settings.llm_timeout_ms/1000:.1f}秒")
    print(f"  温度参数: {settings.llm_temperature}")
    print(f"  最大Token: {settings.llm_max_tokens}")
    print(f"  并发数: {settings.llm_concurrency}")
    print()
    
    # 2. 验证必要配置
    if not settings.custom_minmax_url:
        print("❌ 错误: 未配置 CUSTOM_MINMAX_URL")
        return False
    
    if not settings.custom_minmax_api_key:
        print("❌ 错误: 未配置 CUSTOM_MINMAX_API_KEY")
        return False
    
    # 3. 测试HTTP连接
    print("🌐 测试网络连接...")
    try:
        base_url = settings.custom_minmax_url.rstrip("/")
        
        # 测试1: 健康检查 (GET /models)
        print(f"  [1/4] 检查服务器可达性: {base_url}/models")
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{base_url}/models",
                headers={"Authorization": f"Bearer {settings.custom_minmax_api_key}"}
            )
            
            if response.status_code == 200:
                models = response.json().get("data", [])
                model_ids = [m.get("id") for m in models]
                print(f"  ✅ 服务器响应正常 (状态码: {response.status_code})")
                print(f"  📦 可用模型列表 ({len(models)}个):")
                for mid in model_ids[:5]:  # 只显示前5个
                    print(f"     - {mid}")
                if len(model_ids) > 5:
                    print(f"     ... 还有 {len(model_ids)-5} 个模型")
                
                # 检查目标模型是否存在
                if settings.llm_model in model_ids:
                    print(f"  ✅ 目标模型 '{settings.llm_model}' 存在")
                else:
                    print(f"  ⚠️  警告: 目标模型 '{settings.llm_model}' 未在列表中找到")
                    print(f"     可用替代方案: {model_ids[0] if model_ids else '无'}")
            else:
                print(f"  ❌ 服务器返回错误 (状态码: {response.status_code})")
                print(f"  响应内容: {response.text[:200]}")
                return False
        
        # 测试2: 简单对话 (POST /chat/completions)
        print(f"\n  [2/4] 测试API调用: {base_url}/chat/completions")
        async with httpx.AsyncClient(timeout=settings.llm_timeout_ms/1000.0) as client:
            test_payload = {
                "model": settings.llm_model,
                "messages": [
                    {"role": "user", "content": "你好，请用一句话介绍你自己"}
                ],
                "temperature": settings.llm_temperature,
                "max_tokens": 100
            }
            
            response = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.custom_minmax_api_key}",
                    "Content-Type": "application/json"
                },
                json=test_payload
            )
            
            if response.status_code == 200:
                result = response.json()
                reply = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})
                
                print(f"  ✅ API调用成功!")
                print(f"  🤖 模型回复: {reply[:100]}...")
                print(f"  📊 Token使用: 输入={usage.get('prompt_tokens', '?')}, 输出={usage.get('completion_tokens', '?')}")
            else:
                print(f"  ❌ API调用失败 (状态码: {response.status_code})")
                print(f"  错误信息: {response.text[:300]}")
                return False
        
        # 测试3: 初始化MaterialLabeler
        print(f"\n  [3/4] 初始化MaterialLabeler...")
        try:
            labeler = MaterialLabeler(
                provider="custom_minmax",
                materials_dir="./test_images"  # 使用临时目录
            )
            print(f"  ✅ Labeler初始化成功")
            print(f"  📝 Provider: {labeler.provider}")
            print(f"  🔗 Base URL: {labeler.base_url}")
            print(f"  🤖 Model: {labeler.model}")
        except Exception as e:
            print(f"  ❌ Labeler初始化失败: {e}")
            return False
        
        # 测试4: 验证配置完整性
        print(f"\n  [4/4] 配置完整性检查...")
        issues = []
        
        if not Path(".env").exists():
            issues.append("❌ .env 文件不存在")
        
        if not settings.enable_fallback:
            issues.append("⚠️  故障回退已禁用 (ENABLE_FALLBACK=false)")
        
        if settings.llm_concurrency > 1:
            issues.append(f"⚠️  并发数={settings.llm_concurrency}, 本地模型建议设为1")
        
        if settings.llm_timeout_ms < 60000:
            issues.append(f"⚠️  超时时间={settings.llm_timeout_ms/1000:.0f}s, Gemma-4建议>=60s")
        
        if issues:
            for issue in issues:
                print(f"  {issue}")
        else:
            print(f"  ✅ 所有配置检查通过")
        
        return True
        
    except httpx.ConnectError:
        print(f"  ❌ 无法连接到服务器: {settings.custom_minmax_url}")
        print(f"  请检查:")
        print(f"     1. 服务器是否启动")
        print(f"     2. URL是否正确")
        print(f"     3. 网络防火墙设置")
        return False
    except httpx.TimeoutException:
        print(f"  ❌ 连接超时 (> {settings.llm_timeout_ms/1000:.0f}秒)")
        print(f"  建议: 对于本地大模型，超时时间应 >= 180秒")
        return False
    except Exception as e:
        print(f"  ❌ 测试过程中发生异常: {type(e).__name__}: {e}")
        return False


async def main():
    """主函数"""
    success = await test_connection()
    
    print()
    print("=" * 60)
    if success:
        print("🎉 所有测试通过！你的LM Studio服务器配置正确")
        print()
        print("下一步操作:")
        print("  1. 准备测试素材到 ./test_images/ 目录")
        print("  2. 运行标注命令:")
        print("     python run_pipeline.py download --local-dir ./test_images")
        print("     python run_pipeline.py label --provider custom_minmax")
        print("  3. 查看结果:")
        print("     python run_pipeline.py export --output-dir ./output")
    else:
        print("❌ 测试未通过，请检查上方错误信息并修正配置")
    print("=" * 60)
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
