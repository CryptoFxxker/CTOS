# Ollama Client - 与 DeepSeek-R1 模型交互

[English](README_EN.md) | [中文](README.md)

## 功能特性

- 🔒 **智能代理控制** - 可灵活控制是否使用代理，解决内网连接问题
- 💬 **对话聊天** - 支持普通聊天和流式输出
- 🎯 **系统提示词** - 支持自定义系统提示词
- 🤖 **模型管理** - 查看可用模型、拉取模型
- ⚡ **高效连接** - 自动处理 JSON 解析错误

## 快速开始

### 基本使用

```python
from ollama_client import OllamaClient

# 创建客户端（默认不走代理）
client = OllamaClient()

# 简单聊天
response = client.chat(prompt="你好！")
print(response.get('message', {}).get('content', ''))
```

### 不使用代理（访问内网服务器）

```python
# 默认就不走代理
client = OllamaClient(use_proxy=False)

# 或明确指定
client = OllamaClient(use_proxy=False)
```

### 使用代理

```python
# 使用环境变量的代理设置
client = OllamaClient(use_proxy=True)

# 或使用自定义代理
proxies = {
    'http': 'http://proxy.example.com:8080',
    'https': 'http://proxy.example.com:8080'
}
client = OllamaClient(use_proxy=True, proxies=proxies)
```

## 主要方法

### `chat()` - 对话聊天

```python
response = client.chat(
    prompt="什么是Python？",
    system="你是一个技术教育者",  # 可选
    stream=False,  # 是否流式输出
    options={"temperature": 0.7}  # 可选参数
)
```

### `stream_chat()` - 流式对话

```python
for chunk in client.stream_chat(prompt="写一首诗"):
    print(chunk, end='', flush=True)
```

### `generate()` - 文本生成

```python
result = client.generate(
    prompt="写一个Hello World程序",
    context="你是一个Python专家"
)
```

### `list_models()` - 列出模型

```python
models = client.list_models()
for model in models:
    print(model)
```

## 配置选项

```python
OllamaClient(
    base_url="http://162.105.88.184:11434",  # 服务器地址
    model="deepseek-r1:32b",                  # 模型名称
    use_proxy=False,                          # 是否使用代理
    proxies=None                              # 自定义代理配置
)
```

## 测试

```bash
# 运行完整测试套件
python ollama_client.py

# 运行连接测试
python test_connection.py

# 运行聊天测试
python test_chat.py
```

## 解决代理问题

默认情况下，客户端会强制禁用所有代理（包括环境变量中的代理），通过设置 `self.session.trust_env = False` 确保不走代理访问内网地址。

## 技术细节

- 自动处理 Ollama API 的流式响应格式
- 智能解析多行 JSON 响应
- 完善的错误处理和超时机制

## 示例项目

查看 `test_connection.py` 和 `test_chat.py` 获取更多使用示例。

---

**注意**：默认连接到 162.105.88.184:11434，请根据实际情况修改服务器地址。

