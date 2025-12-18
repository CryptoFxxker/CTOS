# AccountPublisher 账户数据发布器

账户数据发布系统，从OKX驱动获取账户数据，通过事件总线分发。

**注意**: 市场行情数据请使用 `DataPublisher`（参见 DataPublisher_README.md）

## 功能特性

1. **账户数据**
   - 账户余额
   - 持仓信息
   - 订单状态

2. **可配置性**
   - 支持多账户监控
   - 支持可配置的更新频率
   - 支持动态添加/移除监控交易对

## 事件主题规范

### 账户数据主题

```
account.balance.{currency}          # 账户余额，如 account.balance.USDT
account.position.{symbol}           # 单个持仓信息
account.position.all                # 所有持仓汇总
account.order.{symbol}              # 单个订单状态
account.order.{symbol}.list         # 订单列表
```

## 使用方法

### 基本使用

```python
from ctos.core.kernel.event_bus import get_event_bus
from ctos.core.io.datafeed.AccountPublisher import AccountPublisher
import time

# 1. 获取事件总线
bus = get_event_bus()

# 2. 定义事件处理器
def balance_handler(topic, message, event):
    account_id = message.get('account_id')
    balance = message.get('balance')
    print(f"余额更新 [账户{account_id}]: {balance}")

def position_handler(topic, message, event):
    pos = message.get('position', {})
    print(f"持仓: {pos.get('symbol')} {pos.get('side')} {pos.get('quantity')}")

# 3. 订阅事件
bus.subscribe('account.balance.USDT', balance_handler)
bus.subscribe('account.position.*', position_handler, wildcard=True)

# 4. 创建并启动账户数据发布器
publisher = AccountPublisher(
    account_id=0,
    symbols=['ETH-USDT-SWAP', 'BTC-USDT-SWAP'],  # 可选，用于订单监控
    balance_interval=5.0,      # 余额5秒更新一次
    position_interval=5.0,      # 持仓5秒更新一次
    order_interval=3.0         # 订单3秒更新一次
)

publisher.start()

try:
    # 运行
    time.sleep(60)
finally:
    publisher.stop()
```

### 动态添加交易对

```python
# 添加要监控订单的交易对
publisher.add_symbol('SOL-USDT-SWAP')

# 移除交易对
publisher.remove_symbol('BTC-USDT-SWAP')
```

### 多账户监控

```python
from ctos.drivers.okx.driver import OkxDriver

# 创建多个账户的发布器
bus = get_event_bus()

# 账户0
driver0 = OkxDriver(account_id=0)
publisher0 = AccountPublisher(driver=driver0, account_id=0, balance_interval=5.0)
publisher0.start()

# 账户1
driver1 = OkxDriver(account_id=1)
publisher1 = AccountPublisher(driver=driver1, account_id=1, balance_interval=5.0)
publisher1.start()

# 订阅时可以区分账户
def balance_handler0(topic, message, event):
    if message.get('account_id') == 0:
        print(f"账户0余额: {message.get('balance')}")

def balance_handler1(topic, message, event):
    if message.get('account_id') == 1:
        print(f"账户1余额: {message.get('balance')}")

bus.subscribe('account.balance.USDT', balance_handler0)
bus.subscribe('account.balance.USDT', balance_handler1)
```

## 配置参数

### AccountPublisher 初始化参数

- `driver`: OKX驱动实例（可选，默认自动创建）
- `event_bus`: 事件总线实例（可选，默认使用全局单例）
- `account_id`: 账户ID（必需）
- `symbols`: 要监控订单的交易对列表（可选，如果为None则从持仓中自动获取）
- `balance_interval`: 余额更新间隔（秒），默认5.0
- `position_interval`: 持仓更新间隔（秒），默认5.0
- `order_interval`: 订单状态更新间隔（秒），默认3.0

## 与 DataPublisher 配合使用

```python
from ctos.core.kernel.event_bus import get_event_bus
from ctos.core.io.datafeed.DataPublisher import DataPublisher
from ctos.core.io.datafeed.AccountPublisher import AccountPublisher

bus = get_event_bus()

# 启动市场数据发布器
market_publisher = DataPublisher(
    symbols=['ETH-USDT-SWAP', 'BTC-USDT-SWAP'],
    price_interval=1.0
)
market_publisher.start()

# 启动账户数据发布器
account_publisher = AccountPublisher(
    account_id=0,
    symbols=['ETH-USDT-SWAP', 'BTC-USDT-SWAP'],
    balance_interval=5.0
)
account_publisher.start()

try:
    # 同时监控市场和账户数据
    time.sleep(60)
finally:
    market_publisher.stop()
    account_publisher.stop()
```

## 统计信息

```python
stats = publisher.get_stats()
print(stats)
# {
#   'balance_published': 12,
#   'position_published': 12,
#   'order_published': 8,
#   'errors': 0,
#   'account_id': 0,
#   'symbols_count': 2,
#   'event_bus_stats': {...}
# }
```

## 注意事项

1. **账户权限**: 确保驱动使用的账户ID有相应的查询权限
2. **更新频率**: 账户数据更新频率建议不要设置太低，避免API限流
3. **交易对监控**: 如果不指定 `symbols`，系统会从持仓数据中自动获取交易对用于订单监控
4. **错误处理**: 系统会自动记录错误计数，定期检查统计信息
5. **线程安全**: 可以在多线程环境中使用，但每个账户建议使用独立的实例

## 扩展指南

### 添加新的账户数据源

1. 在 `AccountPublisher` 中添加新的循环方法（如 `_custom_data_loop`）
2. 在 `start()` 方法中启动对应的线程
3. 定义相应的事件主题并发布数据

### 与其他系统集成

```python
# 订阅账户数据并触发交易决策
class TradingDecisionEngine:
    def __init__(self, event_bus):
        self.bus = event_bus
        self.bus.subscribe('account.position.*', self.on_position_change, wildcard=True)
        self.bus.subscribe('account.balance.USDT', self.on_balance_change)
    
    def on_position_change(self, topic, message, event):
        # 持仓变化时的处理逻辑
        pass
    
    def on_balance_change(self, topic, message, event):
        # 余额变化时的处理逻辑
        pass
```

