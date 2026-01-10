"""
简单的聊天测试
"""

from ollama_client import OllamaClient

def test_simple_chat():
    """测试简单聊天"""
    print("\n" + "=" * 60)
    print("测试: 简单聊天")
    print("=" * 60)
    
    client = OllamaClient(use_proxy=False)
    
    try:
        print("发送消息: 你好，请用一句话介绍你自己。")
        response = client.chat(prompt="你好，请用一句话介绍你自己。", stream=False)
        content = response.get('message', {}).get('content', '')
        print(f"\n模型回答:\n{content}")
        return True
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_chat_with_system():
    """测试带系统提示词的聊天"""
    print("\n" + "=" * 60)
    print("测试: 带系统提示词的聊天")
    print("=" * 60)
    
    client = OllamaClient(use_proxy=False)
    
    try:
        print("系统提示: 你是一个专业的Python编程助手。")
        print("用户问题: 请用Python写一个简单的Hello World程序。")
        
        response = client.chat(
            system="你是一个专业的Python编程助手。",
            prompt="请用Python写一个简单的Hello World程序。",
            stream=False
        )
        
        content = response.get('message', {}).get('content', '')
        print(f"\n模型回答:\n{content}")
        return True
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("聊天功能测试")
    print("=" * 80)
    
    # 测试 1
    result1 = test_simple_chat()
    
    # 测试 2
    result2 = test_chat_with_system()
    
    # 总结
    print("\n" + "=" * 80)
    print("测试结果")
    print("=" * 80)
    print(f"简单聊天: {'✓ 成功' if result1 else '✗ 失败'}")
    print(f"带系统提示词: {'✓ 成功' if result2 else '✗ 失败'}")
    print("=" * 80)

