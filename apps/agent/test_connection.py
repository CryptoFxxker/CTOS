"""
快速测试连接脚本
用于验证代理设置是否正确
"""

import sys
import os
from ollama_client import OllamaClient

def test_no_proxy():
    """测试不使用代理"""
    print("\n" + "=" * 60)
    print("测试 1: 不使用代理（强制禁用环境变量代理）")
    print("=" * 60)
    
    # 检查环境变量
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    
    print(f"环境变量中的代理:")
    print(f"  HTTP_PROXY={http_proxy}")
    print(f"  HTTPS_PROXY={https_proxy}")
    
    # 创建客户端（默认 use_proxy=False）
    print("\n创建客户端（use_proxy=False）...")
    client = OllamaClient(use_proxy=False)
    print(f"客户端配置: {client}")
    print(f"Session trust_env: {client.session.trust_env}")
    print(f"Session proxies: {client.session.proxies}")
    
    # 测试连接
    print("\n测试连接到 162.105.88.184:11434...")
    try:
        is_connected = client._check_connection()
        print(f"连接结果: {'✓ 成功' if is_connected else '✗ 失败'}")
        return is_connected
    except Exception as e:
        print(f"连接失败: {e}")
        return False

def test_with_proxy():
    """测试使用代理"""
    print("\n" + "=" * 60)
    print("测试 2: 使用代理")
    print("=" * 60)
    
    import os
    http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
    
    if not http_proxy:
        print("  环境中没有设置代理，跳过此测试")
        return None
    
    # 创建客户端（使用代理）
    print("\n创建客户端（use_proxy=True）...")
    client = OllamaClient(use_proxy=True)
    print(f"客户端配置: {client}")
    print(f"Session trust_env: {client.session.trust_env}")
    print(f"Session proxies: {client.session.proxies}")
    
    # 测试连接
    print("\n测试连接...")
    try:
        is_connected = client._check_connection()
        print(f"连接结果: {'✓ 成功' if is_connected else '✗ 失败'}")
        return is_connected
    except Exception as e:
        print(f"连接失败: {e}")
        return False

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("Ollama 连接测试 - 验证代理设置")
    print("=" * 80)
    
    # 测试 1: 不使用代理
    result1 = test_no_proxy()
    
    # 测试 2: 使用代理（可选）
    result2 = test_with_proxy()
    
    # 总结
    print("\n" + "=" * 80)
    print("测试结果总结")
    print("=" * 80)
    print(f"不使用代理: {'✓ 成功' if result1 else '✗ 失败'}")
    if result2 is not None:
        print(f"使用代理: {'✓ 成功' if result2 else '✗ 失败'}")
    print("=" * 80)
    
    # 根据结果返回退出码
    if result1:
        sys.exit(0)
    else:
        sys.exit(1)

