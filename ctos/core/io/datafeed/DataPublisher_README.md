# DataPublisher 实时市场数据发布器

实时市场数据发布系统，从OKX驱动获取市场行情数据，通过事件总线分发。

**注意**: 账户数据请使用 `AccountPublisher`（参见 AccountPublisher_README.md）

## 功能特性

1. **实时市场数据**
   - 价格数据
   - 订单簿数据
   - K线数据

2. **可扩展架构**
   - 支持自定义数据发布
   - 支持因子分发
   - 支持交易操作响应

**账户数据功能**（余额、持仓、订单）已移至 `AccountPublisher`，请参考 AccountPublisher_README.md

## 事件主题规范

### 市场数据主题

```
market.price.{symbol}              # 实时价格，如 market.price.ETH-USDT-SWAP
market.orderbook.{symbol}           # 订单簿数据
market.kline.{symbol}.{timeframe}  # K线数据，如 market.kline.ETH-USDT-SWAP.1m
market.ticker.{symbol}              # 24小时行情数据（预留）
```

### 账户数据主题（由 AccountPublisher 提供）

```
account.balance.{currency}          # 账户余额，如 account.balance.USDT
account.position.{symbol}           # 单个持仓信息
account.position.all                # 所有持仓汇总
account.order.{symbol}              # 单个订单状态
account.order.{symbol}.list         # 订单列表
```

**注意**: 这些主题由 `AccountPublisher` 发布，不是 `DataPublisher`

### 因子数据主题（扩展）

```
factor.{name}                      # 因子数据，如 factor.momentum.ETH-USDT-SWAP
factor.{name}.{symbol}             # 指定交易对的因子
factor.composite.{name}             # 复合因子
```

### 交易操作主题（扩展）

```
trade.order.place                  # 下单操作
trade.order.cancel                 # 撤单操作
trade.order.amend                  # 改单操作
trade.position.close               # 平仓操作
trade.response.success             # 交易成功响应
trade.response.error               # 交易错误响应
```

### 系统主题

```
system.error                       # 系统错误
system.status                      # 系统状态
system.warning                     # 系统警告
```

## 使用方法

### 基本使用

```python
from ctos.core.kernel.event_bus import get_event_bus
from ctos.core.io.datafeed.DataPublisher import DataPublisher
import time

# 1. 获取事件总线
bus = get_event_bus()

# 2. 定义事件处理器
def price_handler(topic, message, event):
    symbol = message.get('symbol')
    price = message.get('price')
    print(f"价格更新: {symbol} = ${price}")

# 3. 订阅事件
bus.subscribe('market.price.ETH-USDT-SWAP', price_handler)

    # 4. 创建并启动市场数据发布器
    publisher = DataPublisher(
        symbols=['ETH-USDT-SWAP', 'BTC-USDT-SWAP'],
        account_id=0,
        price_interval=1.0,      # 价格1秒更新一次
        orderbook_interval=2.0,   # 订单簿2秒更新一次
        kline_interval=60.0      # K线60秒更新一次
    )

publisher.start()

try:
    # 运行
    time.sleep(60)
finally:
    publisher.stop()
```

### 高级使用：自定义数据发布

```python
# 发布自定义因子数据
publisher.publish_custom('factor.momentum.ETH-USDT-SWAP', {
    'value': 0.85,
    'signal': 'buy'
})

# 发布交易响应
bus.publish('trade.response.success', {
    'order_id': '12345',
    'symbol': 'ETH-USDT-SWAP',
    'action': 'buy',
    'quantity': 1.0
})
```

### 扩展：因子计算器订阅价格并发布因子

```python
class FactorCalculator:
    def __init__(self, event_bus):
        self.bus = event_bus
        self.price_history = defaultdict(list)
        
        # 订阅价格数据
        self.bus.subscribe('market.price.*', self.on_price, wildcard=True)
    
    def on_price(self, topic, message, event):
        symbol = message.get('symbol')
        price = message.get('price')
        
        # 记录价格历史
        self.price_history[symbol].append({
            'price': price,
            'ts': message.get('ts_ms')
        })
        
        # 保持最近100个价格点
        if len(self.price_history[symbol]) > 100:
            self.price_history[symbol].pop(0)
        
        # 计算动量因子
        if len(self.price_history[symbol]) >= 20:
            prices = [p['price'] for p in self.price_history[symbol][-20:]]
            momentum = (prices[-1] - prices[0]) / prices[0]
            
            # 发布因子
            self.bus.publish(f'factor.momentum.{symbol}', {
                'symbol': symbol,
                'momentum': momentum,
                'signal': 'buy' if momentum > 0.02 else 'sell' if momentum < -0.02 else 'hold'
            })

# 使用
bus = get_event_bus()
factor_calc = FactorCalculator(bus)

# 订阅因子数据
def momentum_handler(topic, message, event):
    print(f"动量因子 [{message['symbol']}]: {message['momentum']:.4f} -> {message['signal']}")

bus.subscribe('factor.momentum.*', momentum_handler, wildcard=True)
```

### 扩展：响应式交易系统

```python
class ReactiveTrader:
    def __init__(self, event_bus, driver):
        self.bus = event_bus
        self.driver = driver
        
        # 订阅因子信号
        self.bus.subscribe('factor.momentum.*', self.on_momentum_signal, wildcard=True)
        self.bus.subscribe('trade.response.*', self.on_trade_response, wildcard=True)
    
    def on_momentum_signal(self, topic, message, event):
        symbol = message['symbol']
        signal = message['signal']
        momentum = message['momentum']
        
        if signal == 'buy' and momentum > 0.05:
            # 下单
            order_id, err = self.driver.buy(symbol, size=0.1, order_type='market')
            if not err:
                self.bus.publish('trade.order.place', {
                    'order_id': order_id,
                    'symbol': symbol,
                    'action': 'buy',
                    'size': 0.1
                })
    
    def on_trade_response(self, topic, message, event):
        if 'success' in topic:
            print(f"✓ 交易成功: {message}")
        elif 'error' in topic:
            print(f"✗ 交易失败: {message}")
```

## 配置参数

### DataPublisher 初始化参数

- `driver`: OKX驱动实例（可选，默认自动创建）
- `event_bus`: 事件总线实例（可选，默认使用全局单例）
- `symbols`: 要监控的交易对列表
- `account_id`: 账户ID（仅用于创建驱动，不用于账户数据查询）
- `price_interval`: 价格更新间隔（秒），默认1.0
- `orderbook_interval`: 订单簿更新间隔（秒），默认2.0
- `kline_interval`: K线更新间隔（秒），默认60.0

**注意**: 账户数据相关参数已移除，请使用 `AccountPublisher`

## 性能建议

1. **更新频率调整**：根据需求调整各数据源的更新频率，避免API限流
2. **交易对数量**：监控的交易对数量会影响性能，建议不超过20个
3. **异步处理**：EventBus默认使用异步模式，确保处理器执行时间不要太长
4. **错误处理**：系统会自动记录错误计数，定期检查统计信息

## 统计信息

```python
stats = publisher.get_stats()
print(stats)
# {
#   'price_published': 120,
#   'orderbook_published': 60,
#   'kline_published': 12,
#   'errors': 0,
#   'symbols_count': 2,
#   'event_bus_stats': {...}
# }
```

## 扩展指南

### 添加新的数据源

1. 在 `DataPublisher` 中添加新的循环方法（如 `_custom_data_loop`）
2. 在 `start()` 方法中启动对应的线程
3. 定义相应的事件主题并发布数据

### 添加因子分发

1. 创建一个因子计算类，订阅市场数据
2. 计算因子值后发布到 `factor.*` 主题
3. 其他组件可以订阅因子数据做出决策

### 添加交易响应

1. 在交易操作后发布 `trade.order.*` 事件
2. 订阅交易响应主题处理结果
3. 可以构建完整的响应式交易系统

## 注意事项

1. **线程安全**：EventBus 是线程安全的，可以在多线程环境中使用
2. **资源清理**：使用完毕后记得调用 `stop()` 方法
3. **错误处理**：建议在处理器中添加异常处理，避免影响其他订阅者
4. **性能监控**：定期查看统计信息，监控系统健康状态

