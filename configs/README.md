# 配置文件读取器使用说明

## 概述
提供了两个配置文件读取器，用于读取和管理配置文件：

1. **`config_reader.py`** - 通用配置文件读取器，支持读取所有YAML配置文件
2. **`account_reader.py`** - 专门的账户配置读取器，专门用于读取`account.yaml`

## 账户配置读取器 (推荐使用)

### 基本用法

```python
from configs.account_reader import account_reader, get_account, get_okx_credentials

# 方法1: 使用全局实例
accounts = account_reader.get_all_accounts()

# 方法2: 使用便捷函数
okx_creds = get_okx_credentials('main')
```

### 主要功能

#### 1. 获取所有账户配置
```python
from configs.account_reader import get_all_accounts

# 获取所有交易所的所有账户
all_accounts = account_reader.get_all_accounts()
print(all_accounts)
# 输出: {'okx': {'main': {...}, 'sub1': {...}}, 'backpack': {'main': {...}}}
```

#### 2. 获取指定交易所的账户
```python
from configs.account_reader import get_exchange_accounts

# 获取OKX的所有账户
okx_accounts = account_reader.get_exchange_accounts('okx')
print(okx_accounts)
# 输出: {'main': {'api_key': '...', ...}, 'sub1': {'api_key': '...', ...}}
```

#### 3. 获取特定账户配置
```python
from configs.account_reader import get_account

# 获取OKX主账户配置
okx_main = get_account('okx', 'main')
print(okx_main)
# 输出: {'api_key': '...', 'api_secret': '...', 'passphrase': '...'}
```

#### 4. 获取交易所特定的认证信息
```python
from configs.account_reader import get_okx_credentials, get_backpack_credentials

# 获取OKX认证信息
okx_creds = get_okx_credentials('main')
print(okx_creds)
# 输出: {'api_key': '...', 'api_secret': '...', 'passphrase': '...'}

# 获取Backpack认证信息
bp_creds = get_backpack_credentials('main')
print(bp_creds)
# 输出: {'public_key': '...', 'secret_key': '...'}
```

#### 5. 获取适合driver使用的认证信息
```python
from configs.account_reader import get_credentials_for_driver

# 自动根据交易所类型返回相应的认证信息
okx_creds = get_credentials_for_driver('okx', 'main')
bp_creds = get_credentials_for_driver('backpack', 'main')
```

#### 6. 列出可用的交易所和账户
```python
from configs.account_reader import list_exchanges, list_accounts

# 获取所有交易所
exchanges = list_exchanges()
print(exchanges)  # ['okx', 'backpack']

# 获取OKX的所有账户
okx_accounts = list_accounts('okx')
print(okx_accounts)  # ['main', 'sub1']
```

#### 7. 验证账户配置
```python
from configs.account_reader import is_account_valid

# 检查账户配置是否有效
is_valid = is_account_valid('okx', 'main')
print(is_valid)  # True 或 False
```

### 在Driver中使用

```python
from configs.account_reader import get_credentials_for_driver

# 在Driver初始化时使用
def init_driver(exchange: str, account: str = 'main'):
    credentials = get_credentials_for_driver(exchange, account)
    
    if exchange == 'okx':
        from ctos.drivers.okx.driver import OkxDriver
        return OkxDriver(
            api_key=credentials['api_key'],
            api_secret=credentials['api_secret'],
            passphrase=credentials['passphrase']
        )
    elif exchange == 'backpack':
        from ctos.drivers.backpack.driver import BackpackDriver
        return BackpackDriver(
            public_key=credentials['public_key'],
            secret_key=credentials['secret_key']
        )
```

### 在ExecutionEngine中使用

```python
from configs.account_reader import get_credentials_for_driver

class ExecutionEngine:
    def __init__(self, exchange: str, account: str = 'main'):
        # 获取认证信息
        credentials = get_credentials_for_driver(exchange, account)
        
        # 根据交易所类型创建driver
        if exchange == 'okx':
            self.driver = OkxDriver(**credentials)
        elif exchange == 'backpack':
            self.driver = BackpackDriver(**credentials)
```

## 通用配置读取器

### 基本用法

```python
from configs.config_reader import config_reader

# 加载配置文件
ctos_config = config_reader.load_yaml('ctos.yaml')
account_config = config_reader.load_yaml('account.yaml')

# 获取特定值
default_exchange = config_reader.get_config('ctos.yaml', 'default_exchange')
api_key = config_reader.get_config('account.yaml', 'accounts.okx.main.api_key')
```

## 配置文件格式

### account.yaml
```yaml
accounts:
  okx:
    main:
      api_key: "your_api_key"
      api_secret: "your_api_secret"
      passphrase: "your_passphrase"
    sub1:
      api_key: "sub_account_api_key"
      api_secret: "sub_account_api_secret"
      passphrase: "sub_account_passphrase"
  backpack:
    main:
      public_key: "your_public_key"
      secret_key: "your_secret_key"
    arb_bot:
      public_key: "bot_public_key"
      secret_key: "bot_secret_key"
```

### ctos.yaml
```yaml
mode: paper
default_exchange: okx
log_level: INFO
data:
  store: parquet
  path: data/
risk:
  max_notional_usd: 10000
  max_leverage: 3
  price_band_bps: 200
  kill_switch: true
```

## 错误处理

```python
from configs.account_reader import account_reader

try:
    credentials = account_reader.get_okx_credentials('main')
    if not credentials['api_key']:
        print("警告: API密钥未配置")
except FileNotFoundError:
    print("错误: 配置文件不存在")
except Exception as e:
    print(f"错误: {e}")
```

## 最佳实践

1. **使用便捷函数**: 优先使用`account_reader.py`中的便捷函数
2. **错误处理**: 始终检查配置是否有效
3. **安全性**: 不要将包含真实密钥的配置文件提交到版本控制
4. **环境变量**: 考虑使用环境变量覆盖配置文件中的值
5. **验证配置**: 在应用启动时验证所有必需的配置

## 扩展性

### 添加新的交易所支持

```python
# 在account_reader.py中添加新方法
def get_binance_credentials(self, account: str = 'main') -> Dict[str, str]:
    account_config = self.get_account('binance', account)
    return {
        'api_key': account_config.get('api_key', ''),
        'api_secret': account_config.get('api_secret', '')
    }
```

### 添加配置验证

```python
def validate_okx_config(self, account: str) -> bool:
    credentials = self.get_okx_credentials(account)
    required_fields = ['api_key', 'api_secret', 'passphrase']
    return all(credentials.get(field) for field in required_fields)
```

这样，您就可以方便地读取和管理配置文件，同时保持代码的简洁性和可维护性。
