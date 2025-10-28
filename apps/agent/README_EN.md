# Ollama Client - Interact with DeepSeek-R1 Model

[中文](README.md) | [English](README_EN.md)

## Features

- 🔒 **Smart Proxy Control** - Flexible proxy configuration for network issues
- 💬 **Chat Interface** - Support regular and streaming chat
- 🎯 **System Prompts** - Custom system prompt support
- 🤖 **Model Management** - List and pull models
- ⚡ **Efficient Connection** - Auto-handle JSON parsing errors

## Quick Start

### Basic Usage

```python
from ollama_client import OllamaClient

# Create client (default: no proxy)
client = OllamaClient()

# Simple chat
response = client.chat(prompt="Hello!")
print(response.get('message', {}).get('content', ''))
```

### Without Proxy (Access Local Network)

```python
# Default: no proxy
client = OllamaClient(use_proxy=False)

# Or explicitly specify
client = OllamaClient(use_proxy=False)
```

### With Proxy

```python
# Use environment proxy settings
client = OllamaClient(use_proxy=True)

# Or use custom proxy
proxies = {
    'http': 'http://proxy.example.com:8080',
    'https': 'http://proxy.example.com:8080'
}
client = OllamaClient(use_proxy=True, proxies=proxies)
```

## Main Methods

### `chat()` - Chat Conversation

```python
response = client.chat(
    prompt="What is Python?",
    system="You are a tech educator",  # optional
    stream=False,  # streaming output
    options={"temperature": 0.7}  # optional params
)
```

### `stream_chat()` - Streaming Chat

```python
for chunk in client.stream_chat(prompt="Write a poem"):
    print(chunk, end='', flush=True)
```

### `generate()` - Text Generation

```python
result = client.generate(
    prompt="Write a Hello World program",
    context="You are a Python expert"
)
```

### `list_models()` - List Models

```python
models = client.list_models()
for model in models:
    print(model)
```

## Configuration Options

```python
OllamaClient(
    base_url="http://162.105.88.184:11434",  # server address
    model="deepseek-r1:32b",                  # model name
    use_proxy=False,                          # use proxy
    proxies=None                              # custom proxy config
)
```

## Testing

```bash
# Run full test suite
python ollama_client.py

# Run connection test
python test_connection.py

# Run chat test
python test_chat.py
```

## Proxy Issue Resolution

By default, the client forces disabling all proxies (including environment variables) by setting `self.session.trust_env = False` to ensure direct connection to local network addresses.

## Technical Details

- Auto-handle Ollama API streaming response format
- Smart parsing of multi-line JSON responses
- Comprehensive error handling and timeout mechanisms

## Examples

Check `test_connection.py` and `test_chat.py` for more usage examples.

---

**Note**: Default connection to 162.105.88.184:11434, please modify server address according to your needs.

