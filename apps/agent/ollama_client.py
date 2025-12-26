"""
Ollama 客户端类
用于与远程 ollama 服务器上的 deepseek-r1:32b 模型交互
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

# 从环境变量读取配置，如果没有设置则使用默认值
DEFAULT_OLLAMA_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
DEFAULT_MODEL = os.getenv('OLLAMA_MODEL', 'deepseek-r1:32b')


def load_ollama_config() -> Dict[str, Any]:
    """
    从配置文件加载 Ollama 配置
    
    Returns:
        dict: Ollama 配置信息
    """
    config_reader = ConfigReader()
    config = config_reader.load_yaml('ollama.yaml')
    
    if config is None:
        logger.warning("无法加载 ollama.yaml 配置文件，使用默认配置或环境变量")
        return {}
    
    return config.get('ollama', {})


def validate_and_fix_url(url: str) -> str:
    """
    验证和修复 URL，确保有协议前缀
    
    Args:
        url: 输入的 URL
    
    Returns:
        str: 修复后的 URL
    """
    url = url.strip()
    
    # 如果没有协议前缀，添加 http://
    if not url.startswith(('http://', 'https://')):
        # 检查是否包含端口号
        if ':' in url and '/' not in url.split(':')[1]:
            # 有端口号，添加 http://
            url = f"http://{url}"
        elif '/' not in url and ':' in url:
            # 有端口号但格式不对，添加 http://
            url = f"http://{url}"
        else:
            # 没有端口号，添加 http:// 和默认端口
            url = f"http://{url}"
    
    return url


def get_default_url() -> str:
    """
    获取默认 URL，带验证和修复
    优先级：环境变量 > 配置文件 > 默认值
    
    Returns:
        str: 验证后的默认 URL
    """
    # 优先从环境变量读取
    url = os.getenv('OLLAMA_BASE_URL')
    if url:
        return validate_and_fix_url(url)
    
    # 其次从配置文件读取
    config = load_ollama_config()
    url = config.get('base_url')
    if url:
        return validate_and_fix_url(url)
    
    return DEFAULT_OLLAMA_URL


def get_default_model() -> str:
    """
    获取默认模型名称
    优先级：环境变量 > 配置文件 > 默认值
    
    Returns:
        str: 默认模型名称
    """
    # 优先从环境变量读取
    model = os.getenv('OLLAMA_MODEL')
    if model:
        return model
    
    # 其次从配置文件读取
    config = load_ollama_config()
    model = config.get('model')
    if model:
        return model
    
    return DEFAULT_MODEL

class OllamaClient:
    """Ollama 客户端类，用于与 ollama 服务器交互"""
    
    def __init__(
        self, 
        base_url: Optional[str] = None, 
        model: Optional[str] = None,
        use_proxy: bool = False,
        proxies: Optional[Dict[str, str]] = None
    ):
        """
        初始化 Ollama 客户端
        
        Args:
            base_url: Ollama 服务器的基础 URL，默认从环境变量 OLLAMA_BASE_URL 读取
            model: 要使用的模型名称，默认从环境变量 OLLAMA_MODEL 读取
            use_proxy: 是否使用代理，默认 False（不走代理）
            proxies: 代理配置字典，格式如 {"http": "http://proxy:port", "https": "https://proxy:port"}
                     如果为 None 且 use_proxy=True，将使用系统环境变量中的代理设置
        """
        # 验证和修复 URL
        # 优先级：参数 > 环境变量 > 配置文件 > 默认值
        if base_url:
            base_url = validate_and_fix_url(base_url)
        else:
            base_url = get_default_url()
        
        self.base_url = base_url.rstrip('/')
        
        # 优先级：参数 > 环境变量 > 配置文件 > 默认值
        self.model = model or get_default_model()
        self.use_proxy = use_proxy
        
        self.session = requests.Session()
        
        # 设置代理
        if use_proxy:
            if proxies is None:
                # 使用环境变量中的代理设置
                import os
                http_proxy = os.environ.get('HTTP_PROXY') or os.environ.get('http_proxy')
                https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
                
                if http_proxy or https_proxy:
                    self.proxies = {
                        'http': http_proxy,
                        'https': https_proxy
                    }
                else:
                    # 如果环境变量也没有，尝试使用常用代理设置
                    # 这里可以设置你的默认代理
                    self.proxies = None
            else:
                self.proxies = proxies
        else:
            # 明确设置不使用代理，强制禁用所有代理（包括环境变量中的代理）
            self.proxies = {"http": None, "https": None, "no_proxy": "*"}
            # 清除 session 默认的代理环境变量读取行为
            self.session.trust_env = False
        
        # 应用代理设置
        if self.proxies is not None:
            self.session.proxies.update(self.proxies)
        
        self.session.headers.update({
            'Content-Type': 'application/json'
        })
        
    def _check_connection(self) -> bool:
        """
        检查与 ollama 服务器的连接
        
        Returns:
            bool: 如果连接成功返回 True，否则返回 False
        """
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"无法连接到 ollama 服务器: {e}")
            return False
    
    def is_available(self) -> bool:
        """
        检查模型是否可用
        
        Returns:
            bool: 如果模型可用返回 True，否则返回 False
        """
        if not self._check_connection():
            return False
        
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=10)
            if response.status_code == 200:
                data = response.json()
                models = [model['name'] for model in data.get('models', [])]
                return self.model in models
        except Exception as e:
            logger.error(f"检查模型可用性时出错: {e}")
        
        return False
    
    def chat(
        self, 
        prompt: str, 
        system: Optional[str] = None,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        发送聊天请求到模型
        
        Args:
            prompt: 用户消息
            system: 系统提示词（可选）
            stream: 是否使用流式响应
            options: 模型配置选项（可选）
        
        Returns:
            Dict[str, Any]: 模型响应
        """
        if not self.is_available():
            raise ConnectionError(f"模型 {self.model} 不可用")
        
        # 构建请求数据
        data = {
            "model": self.model,
            "messages": []
        }
        
        if system:
            data["messages"].append({
                "role": "system",
                "content": system
            })
        
        data["messages"].append({
            "role": "user",
            "content": prompt
        })
        
        data["stream"] = stream
        
        if options:
            data["options"] = options
        
        try:
            # ollama API 总是返回流式响应，我们需要使用 stream=True 来处理
            response = self.session.post(
                f"{self.base_url}/api/chat",
                json=data,
                stream=True,  # 必须使用 stream=True 来处理多行 JSON
                timeout=300
            )
            response.raise_for_status()
            
            # 解析多行 JSON 响应
            full_content = ""
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode('utf-8'))
                        content = chunk.get('message', {}).get('content', '')
                        if content:
                            full_content += content
                        if chunk.get('done', False):
                            break
                    except json.JSONDecodeError:
                        continue
            return {"message": {"content": full_content}}
                    
        except requests.exceptions.Timeout:
            raise TimeoutError("请求超时，服务器响应时间过长")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"请求失败: {e}")
    
    def generate(
        self,
        prompt: str,
        context: Optional[str] = None,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        生成文本（简化版本，使用 chat API）
        
        Args:
            prompt: 提示词
            context: 上下文信息（可选）
            stream: 是否使用流式响应
            options: 模型配置选项（可选）
        
        Returns:
            str: 生成的文本
        """
        system_prompt = context if context else None
        
        response = self.chat(
            prompt=prompt,
            system=system_prompt,
            stream=stream,
            options=options
        )
        
        # 从响应中提取文本
        if stream:
            # 如果是流式响应，返回完整的文本内容
            return response.get('message', {}).get('content', '')
        else:
            return response.get('message', {}).get('content', '')
    
    def stream_chat(
        self,
        prompt: str,
        system: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None
    ) -> Iterator[str]:
        """
        流式聊天，返回一个迭代器
        
        Args:
            prompt: 用户消息
            system: 系统提示词（可选）
            options: 模型配置选项（可选）
        
        Yields:
            str: 每个生成的文本片段
        """
        try:
            data = {
                "model": self.model,
                "messages": []
            }
            
            if system:
                data["messages"].append({
                    "role": "system",
                    "content": system
                })
            
            data["messages"].append({
                "role": "user",
                "content": prompt
            })
            
            data["stream"] = True
            
            if options:
                data["options"] = options
            
            response = self.session.post(
                f"{self.base_url}/api/chat",
                json=data,
                stream=True,
                timeout=300
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode('utf-8'))
                        content = chunk.get('message', {}).get('content', '')
                        if content:
                            yield content
                        if chunk.get('done', False):
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"流式聊天出错: {e}")
            raise
    
    def list_models(self) -> list:
        """
        列出所有可用的模型
        
        Returns:
            list: 可用模型列表
        """
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
        except Exception as e:
            logger.error(f"获取模型列表失败: {e}")
            return []
    
    def pull_model(self, model_name: Optional[str] = None) -> bool:
        """
        拉取指定模型（如果不存在）
        
        Args:
            model_name: 要拉取的模型名称，默认使用当前模型
        
        Returns:
            bool: 如果成功返回 True
        """
        model = model_name or self.model
        
        try:
            response = self.session.post(
                f"{self.base_url}/api/pull",
                json={"name": model},
                stream=True,
                timeout=600  # 10分钟超时
            )
            response.raise_for_status()
            
            # 监听拉取进度
            for line in response.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode('utf-8'))
                        logger.info(f"拉取进度: {chunk.get('status', '')}")
                        if chunk.get('status') == 'success':
                            return True
                    except json.JSONDecodeError:
                        continue
            
            return False
        except Exception as e:
            logger.error(f"拉取模型失败: {e}")
            return False
    
    def __repr__(self):
        proxy_info = "使用代理" if self.use_proxy else "不使用代理"
        return f"OllamaClient(base_url={self.base_url}, model={self.model}, proxy={proxy_info})"


# ============================================================================
# 测试用例
# ============================================================================

def test_connection():
    """测试连接"""
    print("=" * 60)
    print("测试 1: 连接测试")
    print("=" * 60)
    
    client = OllamaClient()
    is_connected = client._check_connection()
    print(f"连接状态: {'✓ 成功' if is_connected else '✗ 失败'}")
    print(f"服务器地址: {client.base_url}")
    return is_connected


def test_model_availability():
    """测试模型可用性"""
    print("\n" + "=" * 60)
    print("测试 2: 模型可用性")
    print("=" * 60)
    
    client = OllamaClient()
    is_available = client.is_available()
    print(f"模型可用性: {'✓ 可用' if is_available else '✗ 不可用'}")
    print(f"模型名称: {client.model}")
    return is_available


def test_list_models():
    """测试列出所有模型"""
    print("\n" + "=" * 60)
    print("测试 3: 列出所有模型")
    print("=" * 60)
    
    client = OllamaClient()
    models = client.list_models()
    print(f"可用模型数量: {len(models)}")
    for model in models:
        print(f"  - {model}")
    return models


def test_simple_chat():
    """测试简单聊天"""
    print("\n" + "=" * 60)
    print("测试 4: 简单聊天")
    print("=" * 60)
    
    client = OllamaClient()
    
    try:
        response = client.chat(
            prompt="你好，请用一句话介绍你自己。",
            stream=False
        )
        
        content = response.get('message', {}).get('content', '')
        print(f"用户问题: 你好，请用一句话介绍你自己。")
        print(f"\n模型回答:\n{content}")
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        return False


def test_chat_with_system():
    """测试带系统提示词的聊天"""
    print("\n" + "=" * 60)
    print("测试 5: 带系统提示词的聊天")
    print("=" * 60)
    
    client = OllamaClient()
    
    try:
        response = client.chat(
            system="你是一个专业的Python编程助手。",
            prompt="请用Python写一个简单的Hello World程序。",
            stream=False
        )
        
        content = response.get('message', {}).get('content', '')
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
    print("测试 6: 流式聊天")
    print("=" * 60)
    
    client = OllamaClient()
    
    try:
        print("用户问题: 请写一首关于Python编程的短诗（不超过4行）")
        print("\n模型回答（流式输出）:")
        print("-" * 60)
        
        full_response = ""
        for chunk in client.stream_chat(
            prompt="请写一首关于Python编程的短诗（不超过4行）"
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
    print("测试 7: 文本生成")
    print("=" * 60)
    
    client = OllamaClient()
    
    try:
        response = client.generate(
            prompt="什么是Python？用一句话回答。",
            context="你是一个技术教育者。"
        )
        
        print(f"用户问题: 什么是Python？用一句话回答。")
        print(f"\n模型回答: {response}")
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        return False


def test_multi_turn_chat():
    """测试多轮对话"""
    print("\n" + "=" * 60)
    print("测试 8: 多轮对话")
    print("=" * 60)
    
    client = OllamaClient()
    
    try:
        # 第一轮
        response1 = client.chat(prompt="我的名字是张三")
        content1 = response1.get('message', {}).get('content', '')
        print(f"用户: 我的名字是张三")
        print(f"模型: {content1}")
        
        # 注意：实际的多轮对话需要在 requests 中维护消息历史
        # 这里只是模拟
        print(f"\n用户: 我刚刚告诉你的名字是什么？")
        print(f"模型: [需要在实际使用中维护对话历史]")
        
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        return False


def test_proxy_settings():
    """测试代理设置"""
    print("\n" + "=" * 60)
    print("测试: 代理设置")
    print("=" * 60)
    
    # 测试 1: 不使用代理（默认）
    print("\n1. 不使用代理（默认）")
    client1 = OllamaClient()
    print(f"   {client1}")
    
    # 测试 2: 明确指定不使用代理
    print("\n2. 明确指定不使用代理")
    client2 = OllamaClient(use_proxy=False)
    print(f"   {client2}")
    
    # 测试 3: 使用环境变量的代理
    print("\n3. 使用环境变量的代理设置")
    import os
    original_http = os.environ.get('HTTP_PROXY')
    original_https = os.environ.get('HTTPS_PROXY')
    
    # 临时设置环境变量
    os.environ['HTTP_PROXY'] = 'http://proxy.example.com:8080'
    os.environ['HTTPS_PROXY'] = 'http://proxy.example.com:8080'
    
    client3 = OllamaClient(use_proxy=True)
    print(f"   {client3}")
    
    # 恢复环境变量
    if original_http:
        os.environ['HTTP_PROXY'] = original_http
    else:
        os.environ.pop('HTTP_PROXY', None)
    
    if original_https:
        os.environ['HTTPS_PROXY'] = original_https
    else:
        os.environ.pop('HTTPS_PROXY', None)
    
    # 测试 4: 使用自定义代理
    print("\n4. 使用自定义代理配置")
    custom_proxies = {
        'http': 'http://proxy.example.com:8080',
        'https': 'http://proxy.example.com:8080'
    }
    client4 = OllamaClient(use_proxy=True, proxies=custom_proxies)
    print(f"   {client4}")
    print(f"   代理配置: {custom_proxies}")
    
    return True


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 80)
    print("开始运行 Ollama 客户端测试套件")
    print("=" * 80)
    
    results = []
    
    # 测试 1: 连接测试
    results.append(("连接测试", test_connection()))
    
    # 测试 2: 模型可用性
    results.append(("模型可用性", test_model_availability()))
    
    # 测试 3: 列出所有模型
    results.append(("列出所有模型", test_list_models()))
    
    # 测试代理设置
    results.append(("代理设置", test_proxy_settings()))
    
    # 只有在模型可用时才进行以下测试
    if results[1][1]:  # 如果模型可用
        results.append(("简单聊天", test_simple_chat()))
        results.append(("带系统提示词的聊天", test_chat_with_system()))
        # results.append(("流式聊天", test_stream_chat()))  # 可以取消注释来测试
        results.append(("文本生成", test_generate()))
        # results.append(("多轮对话", test_multi_turn_chat()))  # 可以取消注释来测试
    
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

