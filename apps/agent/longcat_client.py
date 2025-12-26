"""
Longcat 客户端类
用于与 Longcat API 交互，支持 OpenAI 和 Anthropic 两种 API 格式
"""

import json
import os
import requests
from typing import Optional, Dict, Any, Iterator
import logging
from pathlib import Path

# 导入配置读取器
try:
    from configs.config_reader import ConfigReader
except ImportError:
    # 如果无法导入，尝试添加路径
    import sys
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    from configs.config_reader import ConfigReader

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_BASE_URL = "https://api.longcat.chat"
DEFAULT_MODEL = "LongCat-Flash-Chat"
DEFAULT_API_FORMAT = "openai"  # openai 或 anthropic


def load_longcat_config() -> Dict[str, Any]:
    """
    从配置文件加载 Longcat 配置
    
    Returns:
        dict: Longcat 配置信息
    """
    config_reader = ConfigReader()
    config = config_reader.load_yaml('longcat.yaml')
    
    if config is None:
        logger.warning("无法加载 longcat.yaml 配置文件，使用默认配置")
        return {}
    
    return config.get('longcat', {})


class LongcatClient:
    """Longcat 客户端类，用于与 Longcat API 交互"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        api_format: Optional[str] = None
    ):
        """
        初始化 Longcat 客户端
        
        Args:
            api_key: API 密钥，默认从配置文件读取
            base_url: API 基础 URL，默认从配置文件读取
            model: 模型名称，默认从配置文件读取
            api_format: API 格式（openai 或 anthropic），默认从配置文件读取
        """
        # 从配置文件加载配置
        config = load_longcat_config()
        
        # 设置 API key（优先使用参数，其次配置文件，最后环境变量）
        self.api_key = api_key or config.get('api_key') or os.getenv('LONGCAT_API_KEY')
        if not self.api_key:
            raise ValueError("API key 未设置，请通过参数、配置文件或环境变量 LONGCAT_API_KEY 提供")
        
        # 设置其他配置
        self.base_url = (base_url or config.get('base_url') or DEFAULT_BASE_URL).rstrip('/')
        self.model = model or config.get('model') or DEFAULT_MODEL
        self.api_format = (api_format or config.get('api_format') or DEFAULT_API_FORMAT).lower()
        
        if self.api_format not in ['openai', 'anthropic']:
            raise ValueError(f"不支持的 API 格式: {self.api_format}，仅支持 'openai' 或 'anthropic'")
        
        # 创建 session
        self.session = requests.Session()
        
        # 设置默认请求头
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        })
        
        # 如果是 Anthropic 格式，添加额外的请求头
        if self.api_format == 'anthropic':
            self.session.headers.update({
                'anthropic-version': '2023-06-01'
            })
    
    def _check_connection(self) -> bool:
        """
        检查与 Longcat API 的连接
        通过发送一个简单的聊天请求来测试连接
        
        Returns:
            bool: 如果连接成功返回 True，否则返回 False
        """
        try:
            # 使用一个非常简单的聊天请求来测试连接（只生成很少的 token）
            if self.api_format == 'openai':
                url = f"{self.base_url}/openai/v1/chat/completions"
                data = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1
                }
            else:
                url = f"{self.base_url}/anthropic/v1/messages"
                data = {
                    "model": self.model,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1
                }
            
            response = self.session.post(url, json=data, timeout=10)
            if response.status_code == 200:
                return True
            else:
                error_msg = response.text[:500] if response.text else "无响应内容"
                logger.error(f"连接测试失败，状态码: {response.status_code}")
                logger.error(f"错误响应: {error_msg}")
                return False
        except requests.exceptions.Timeout:
            logger.error("连接超时，可能是网络问题或服务器响应慢")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"连接错误: {e}")
            logger.error("可能是网络问题、服务器不可达或需要代理")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"请求异常: {type(e).__name__}: {e}")
            return False
        except Exception as e:
            logger.error(f"无法连接到 Longcat API: {type(e).__name__}: {e}")
            return False
    
    def is_available(self) -> bool:
        """
        检查 API 是否可用
        
        Returns:
            bool: 如果 API 可用返回 True，否则返回 False
        """
        return self._check_connection()
    
    def chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        stream: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送聊天请求到模型
        
        Args:
            prompt: 用户消息
            system: 系统提示词（可选）
            stream: 是否使用流式响应
            max_tokens: 最大生成 token 数（可选）
            temperature: 温度参数（可选）
            **kwargs: 其他模型参数
        
        Returns:
            Dict[str, Any]: 模型响应
        """
        if self.api_format == 'openai':
            return self._chat_openai(prompt, system, stream, max_tokens, temperature, **kwargs)
        else:
            return self._chat_anthropic(prompt, system, stream, max_tokens, temperature, **kwargs)
    
    def _chat_openai(
        self,
        prompt: str,
        system: Optional[str] = None,
        stream: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """使用 OpenAI 格式发送聊天请求"""
        url = f"{self.base_url}/openai/v1/chat/completions"
        
        messages = []
        if system:
            messages.append({
                "role": "system",
                "content": system
            })
        messages.append({
            "role": "user",
            "content": prompt
        })
        
        data = {
            "model": self.model,
            "messages": messages,
            "stream": stream
        }
        
        if max_tokens is not None:
            data["max_tokens"] = max_tokens
        if temperature is not None:
            data["temperature"] = temperature
        
        # 添加其他参数
        data.update(kwargs)
        
        try:
            response = self.session.post(url, json=data, stream=stream, timeout=300)
            response.raise_for_status()
            
            if stream:
                # 处理流式响应
                full_content = ""
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            if 'choices' in chunk and len(chunk['choices']) > 0:
                                delta = chunk['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    full_content += content
                                if chunk['choices'][0].get('finish_reason'):
                                    break
                        except json.JSONDecodeError:
                            continue
                return {
                    "choices": [{
                        "message": {
                            "content": full_content
                        }
                    }]
                }
            else:
                return response.json()
        except requests.exceptions.Timeout:
            raise TimeoutError("请求超时，服务器响应时间过长")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"请求失败: {e}")
    
    def _chat_anthropic(
        self,
        prompt: str,
        system: Optional[str] = None,
        stream: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """使用 Anthropic 格式发送聊天请求"""
        url = f"{self.base_url}/anthropic/v1/messages"
        
        messages = [{
            "role": "user",
            "content": prompt
        }]
        
        data = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or 1000
        }
        
        if system:
            data["system"] = system
        if temperature is not None:
            data["temperature"] = temperature
        
        # 添加其他参数
        data.update(kwargs)
        
        try:
            response = self.session.post(url, json=data, stream=stream, timeout=300)
            response.raise_for_status()
            
            if stream:
                # 处理流式响应
                full_content = ""
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            if chunk.get('type') == 'content_block_delta':
                                delta = chunk.get('delta', {})
                                text = delta.get('text', '')
                                if text:
                                    full_content += text
                            elif chunk.get('type') == 'message_stop':
                                break
                        except json.JSONDecodeError:
                            continue
                return {
                    "content": [{
                        "type": "text",
                        "text": full_content
                    }]
                }
            else:
                return response.json()
        except requests.exceptions.Timeout:
            raise TimeoutError("请求超时，服务器响应时间过长")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"请求失败: {e}")
    
    def generate(
        self,
        prompt: str,
        context: Optional[str] = None,
        stream: bool = False,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> str:
        """
        生成文本（简化版本，使用 chat API）
        
        Args:
            prompt: 提示词
            context: 上下文信息（可选，作为 system 消息）
            stream: 是否使用流式响应
            max_tokens: 最大生成 token 数（可选）
            temperature: 温度参数（可选）
            **kwargs: 其他模型参数
        
        Returns:
            str: 生成的文本
        """
        response = self.chat(
            prompt=prompt,
            system=context,
            stream=stream,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )
        
        # 从响应中提取文本
        if self.api_format == 'openai':
            if 'choices' in response and len(response['choices']) > 0:
                return response['choices'][0]['message']['content']
        else:
            if 'content' in response and len(response['content']) > 0:
                return response['content'][0]['text']
        
        return ""
    
    def stream_chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        **kwargs
    ) -> Iterator[str]:
        """
        流式聊天，返回一个迭代器
        
        Args:
            prompt: 用户消息
            system: 系统提示词（可选）
            max_tokens: 最大生成 token 数（可选）
            temperature: 温度参数（可选）
            **kwargs: 其他模型参数
        
        Yields:
            str: 每个生成的文本片段
        """
        try:
            if self.api_format == 'openai':
                url = f"{self.base_url}/openai/v1/chat/completions"
                
                messages = []
                if system:
                    messages.append({
                        "role": "system",
                        "content": system
                    })
                messages.append({
                    "role": "user",
                    "content": prompt
                })
                
                data = {
                    "model": self.model,
                    "messages": messages,
                    "stream": True
                }
                
                if max_tokens is not None:
                    data["max_tokens"] = max_tokens
                if temperature is not None:
                    data["temperature"] = temperature
                data.update(kwargs)
                
                response = self.session.post(url, json=data, stream=True, timeout=300)
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            if 'choices' in chunk and len(chunk['choices']) > 0:
                                delta = chunk['choices'][0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    yield content
                                if chunk['choices'][0].get('finish_reason'):
                                    break
                        except json.JSONDecodeError:
                            continue
            else:
                # Anthropic 格式
                url = f"{self.base_url}/anthropic/v1/messages"
                
                messages = [{
                    "role": "user",
                    "content": prompt
                }]
                
                data = {
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens or 1000
                }
                
                if system:
                    data["system"] = system
                if temperature is not None:
                    data["temperature"] = temperature
                data.update(kwargs)
                
                response = self.session.post(url, json=data, stream=True, timeout=300)
                response.raise_for_status()
                
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line.decode('utf-8'))
                            if chunk.get('type') == 'content_block_delta':
                                delta = chunk.get('delta', {})
                                text = delta.get('text', '')
                                if text:
                                    yield text
                            elif chunk.get('type') == 'message_stop':
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"流式聊天出错: {e}")
            raise
    
    def __repr__(self):
        return f"LongcatClient(base_url={self.base_url}, model={self.model}, api_format={self.api_format})"


# ============================================================================
# 测试用例
# ============================================================================

def test_connection():
    """测试连接"""
    print("=" * 60)
    print("测试 1: 连接测试")
    print("=" * 60)
    
    try:
        client = LongcatClient()
        print(f"服务器地址: {client.base_url}")
        print(f"API 格式: {client.api_format}")
        print(f"模型名称: {client.model}")
        print(f"API Key: {client.api_key[:10]}...{client.api_key[-4:] if len(client.api_key) > 14 else '***'}")
        print("\n正在测试连接...")
        is_connected = client._check_connection()
        print(f"连接状态: {'✓ 成功' if is_connected else '✗ 失败'}")
        if not is_connected:
            print("提示: 请检查网络连接、API Key 是否正确、服务器地址是否可访问")
        return is_connected
    except Exception as e:
        print(f"连接测试失败: {type(e).__name__}: {e}")
        return False


def test_api_availability():
    """测试 API 可用性"""
    print("\n" + "=" * 60)
    print("测试 2: API 可用性")
    print("=" * 60)
    
    try:
        client = LongcatClient()
        print("正在检查 API 可用性...")
        is_available = client.is_available()
        print(f"API 可用性: {'✓ 可用' if is_available else '✗ 不可用'}")
        print(f"模型名称: {client.model}")
        if not is_available:
            print("提示: API 不可用，可能是网络问题、API Key 无效或服务器故障")
        return is_available
    except Exception as e:
        print(f"测试失败: {type(e).__name__}: {e}")
        return False


def test_simple_chat():
    """测试简单聊天"""
    print("\n" + "=" * 60)
    print("测试 3: 简单聊天")
    print("=" * 60)
    
    try:
        client = LongcatClient()
        
        response = client.chat(
            prompt="你好，请用一句话介绍你自己。",
            stream=False,
            max_tokens=100
        )
        
        if client.api_format == 'openai':
            content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
        else:
            content = response.get('content', [{}])[0].get('text', '')
        
        print(f"用户问题: 你好，请用一句话介绍你自己。")
        print(f"\n模型回答:\n{content}")
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        return False


def test_chat_with_system():
    """测试带系统提示词的聊天"""
    print("\n" + "=" * 60)
    print("测试 4: 带系统提示词的聊天")
    print("=" * 60)
    
    try:
        client = LongcatClient()
        
        response = client.chat(
            system="你是一个专业的Python编程助手。",
            prompt="请用Python写一个简单的Hello World程序。",
            stream=False,
            max_tokens=200
        )
        
        if client.api_format == 'openai':
            content = response.get('choices', [{}])[0].get('message', {}).get('content', '')
        else:
            content = response.get('content', [{}])[0].get('text', '')
        
        print(f"系统提示: 你是一个专业的Python编程助手。")
        print(f"用户问题: 请用Python写一个简单的Hello World程序。")
        print(f"\n模型回答:\n{content}")
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        return False


def test_stream_chat():
    """测试流式聊天"""
    print("\n" + "=" * 60)
    print("测试 5: 流式聊天")
    print("=" * 60)
    
    try:
        client = LongcatClient()
        
        print("用户问题: 请写一首关于Python编程的短诗（不超过4行）")
        print("\n模型回答（流式输出）:")
        print("-" * 60)
        
        full_response = ""
        for chunk in client.stream_chat(
            prompt="请写一首关于Python编程的短诗（不超过4行）",
            max_tokens=200
        ):
            print(chunk, end='', flush=True)
            full_response += chunk
        
        print("\n" + "-" * 60)
        print(f"\n完整回答长度: {len(full_response)} 字符")
        return True
    except Exception as e:
        print(f"\n测试失败: {e}")
        return False


def test_generate():
    """测试文本生成"""
    print("\n" + "=" * 60)
    print("测试 6: 文本生成")
    print("=" * 60)
    
    try:
        client = LongcatClient()
        
        response = client.generate(
            prompt="什么是Python？用一句话回答。",
            context="你是一个技术教育者。",
            max_tokens=100
        )
        
        print(f"用户问题: 什么是Python？用一句话回答。")
        print(f"\n模型回答: {response}")
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        return False


def test_api_formats():
    """测试不同的 API 格式"""
    print("\n" + "=" * 60)
    print("测试 8: API 格式测试")
    print("=" * 60)
    
    try:
        # 测试 OpenAI 格式
        print("\n1. OpenAI 格式")
        client_openai = LongcatClient(api_format='openai')
        print(f"   {client_openai}")
        
        # 测试 Anthropic 格式
        print("\n2. Anthropic 格式")
        client_anthropic = LongcatClient(api_format='anthropic')
        print(f"   {client_anthropic}")
        
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("开始运行 Longcat 客户端测试套件")
    print("=" * 80)
    
    results = []
    
    # 测试 1: 连接测试
    results.append(("连接测试", test_connection()))
    
    # 测试 2: API 可用性
    results.append(("API 可用性", test_api_availability()))
    
    # 测试 API 格式
    results.append(("API 格式", test_api_formats()))
    
    # 只有在 API 可用时才进行以下测试
    if results[1][1]:  # 如果 API 可用
        results.append(("简单聊天", test_simple_chat()))
        results.append(("带系统提示词的聊天", test_chat_with_system()))
        # results.append(("流式聊天", test_stream_chat()))  # 可以取消注释来测试
        results.append(("文本生成", test_generate()))
    
    # 打印总结
    print("\n" + "=" * 80)
    print("测试结果总结")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name}: {status}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    print("=" * 80)
    
    return results


if __name__ == "__main__":
    # 配置日志
	
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 运行所有测试
    run_all_tests()

