# -*- coding: utf-8 -*-
# ctos/core/io/datafeed/example_usage.py
"""
DataPublisher 使用示例

展示如何使用 DataPublisher 和 EventBus 构建实时数据分发系统
"""
import time
import sys
import os

# 添加项目路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from ctos.core.kernel.event_bus import get_event_bus
from ctos.core.io.datafeed.DataPublisher import DataPublisher
from ctos.core.io.datafeed.AccountPublisher import AccountPublisher


def example_basic_usage():
    """基础使用示例 - 市场数据和账户数据分离"""
    print("=== 示例 1: 基础使用（市场数据 + 账户数据） ===\n")
    
    # 1. 获取事件总线
    bus = get_event_bus()
    
    # 2. 定义事件处理器
    def price_handler(topic, message, event):
        symbol = message.get('symbol')
        price = message.get('price')
        ts = event.get('timestamp', 0)
        print(f"[{time.strftime('%H:%M:%S', time.localtime(ts))}] 价格: {symbol} = ${price:.2f}")
    
    def position_handler(topic, message, event):
        pos = message.get('position', {})
        symbol = pos.get('symbol', 'N/A')
        side = pos.get('side', 'N/A')
        qty = pos.get('quantity', 0)
        if qty > 0:
            print(f"[持仓] {symbol}: {side} {qty:.4f}")
    
    # 3. 订阅事件
    bus.subscribe('market.price.ETH-USDT-SWAP', price_handler)
    bus.subscribe('account.position.*', position_handler, wildcard=True)
    
    # 4. 创建并启动市场数据发布器
    market_publisher = DataPublisher(
        symbols=['ETH-USDT-SWAP', 'BTC-USDT-SWAP'],
        account_id=0,
        price_interval=2.0,      # 2秒更新一次价格
        orderbook_interval=3.0,
        kline_interval=60.0
    )
    market_publisher.start()
    
    # 5. 创建并启动账户数据发布器
    account_publisher = AccountPublisher(
        account_id=0,
        symbols=['ETH-USDT-SWAP', 'BTC-USDT-SWAP'],
        balance_interval=10.0,     # 10秒更新一次余额
        position_interval=10.0,    # 10秒更新一次持仓
        order_interval=5.0
    )
    account_publisher.start()
    
    try:
        print("运行中... (按 Ctrl+C 停止)\n")
        time.sleep(30)
        
        # 打印统计信息
        print("\n=== 市场数据统计 ===")
        market_stats = market_publisher.get_stats()
        for key, value in market_stats.items():
            if key not in ['last_updates', 'error_counts', 'event_bus_stats']:
                print(f"{key}: {value}")
        
        print("\n=== 账户数据统计 ===")
        account_stats = account_publisher.get_stats()
        for key, value in account_stats.items():
            if key not in ['last_updates', 'error_counts', 'event_bus_stats']:
                print(f"{key}: {value}")
        
    except KeyboardInterrupt:
        print("\n正在停止...")
    finally:
        market_publisher.stop()
        account_publisher.stop()
        bus.stop()


def example_factor_calculator():
    """因子计算器示例 - 订阅价格并发布因子"""
    print("\n=== 示例 2: 因子计算器 ===\n")
    
    from collections import defaultdict
    
    bus = get_event_bus()
    
    class MomentumCalculator:
        def __init__(self):
            self.price_history = defaultdict(list)
            bus.subscribe('market.price.*', self.on_price, wildcard=True)
        
        def on_price(self, topic, message, event):
            symbol = message.get('symbol')
            price = message.get('price')
            
            # 记录价格历史
            self.price_history[symbol].append(price)
            
            # 保持最近50个价格点
            if len(self.price_history[symbol]) > 50:
                self.price_history[symbol].pop(0)
            
            # 计算动量因子（需要至少20个数据点）
            if len(self.price_history[symbol]) >= 20:
                prices = self.price_history[symbol][-20:]
                momentum = (prices[-1] - prices[0]) / prices[0] if prices[0] > 0 else 0
                
                # 发布因子
                bus.publish(f'factor.momentum.{symbol}', {
                    'symbol': symbol,
                    'momentum': momentum,
                    'signal': 'buy' if momentum > 0.02 else ('sell' if momentum < -0.02 else 'hold'),
                    'current_price': price
                })
    
    def momentum_handler(topic, message, event):
        symbol = message['symbol']
        momentum = message['momentum']
        signal = message['signal']
        print(f"[因子] {symbol}: 动量={momentum:.4f} -> 信号={signal}")
    
    # 创建因子计算器
    calc = MomentumCalculator()
    
    # 订阅因子数据
    bus.subscribe('factor.momentum.*', momentum_handler, wildcard=True)
    
    # 启动市场数据发布器
    publisher = DataPublisher(
        symbols=['ETH-USDT-SWAP'],
        price_interval=1.0
    )
    publisher.start()
    
    try:
        print("因子计算器运行中... (按 Ctrl+C 停止)\n")
        time.sleep(30)
    except KeyboardInterrupt:
        print("\n正在停止...")
    finally:
        publisher.stop()
        bus.stop()


def example_reactive_trading():
    """响应式交易示例 - 订阅因子信号并执行交易"""
    print("\n=== 示例 3: 响应式交易系统 ===\n")
    
    bus = get_event_bus()
    
    # 注意：这是一个示例，实际使用时需要谨慎处理交易逻辑
    class SimpleReactiveTrader:
        def __init__(self, driver):
            self.driver = driver
            self.trade_count = 0
            bus.subscribe('factor.momentum.*', self.on_signal, wildcard=True)
            bus.subscribe('trade.order.*', self.on_trade_order, wildcard=True)
        
        def on_signal(self, topic, message, event):
            symbol = message['symbol']
            signal = message['signal']
            momentum = message['momentum']
            
            # 只打印，不实际交易（示例）
            if signal in ['buy', 'sell']:
                print(f"[交易信号] {symbol}: {signal.upper()} (动量={momentum:.4f})")
                # 实际交易代码（注释掉，避免真实交易）
                # if signal == 'buy' and momentum > 0.05:
                #     order_id, err = self.driver.buy(symbol, size=0.1, order_type='market')
                #     if not err:
                #         bus.publish('trade.order.place', {
                #             'order_id': order_id,
                #             'symbol': symbol,
                #             'action': 'buy'
                #         })
        
        def on_trade_order(self, topic, message, event):
            print(f"[交易订单] {topic}: {message}")
    
    def momentum_handler(topic, message, event):
        # 简化的动量计算（实际应该从因子计算器获取）
        pass
    
    # 创建驱动（使用账户ID 0）
    try:
        from ctos.drivers.okx.driver import OkxDriver
        driver = OkxDriver(account_id=0)
        
        # 创建交易器
        trader = SimpleReactiveTrader(driver)
        
        # 启动市场数据发布器
        market_publisher = DataPublisher(
            symbols=['ETH-USDT-SWAP'],
            driver=driver,
            price_interval=2.0
        )
        market_publisher.start()
        
        # 启动账户数据发布器
        account_publisher = AccountPublisher(
            driver=driver,
            account_id=0,
            symbols=['ETH-USDT-SWAP'],
            balance_interval=10.0
        )
        account_publisher.start()
        
        try:
            print("响应式交易系统运行中... (按 Ctrl+C 停止)\n")
            print("注意: 此示例仅打印信号，不执行实际交易\n")
            time.sleep(30)
        except KeyboardInterrupt:
            print("\n正在停止...")
        finally:
            market_publisher.stop()
            account_publisher.stop()
            bus.stop()
    
    except Exception as e:
        print(f"初始化失败: {e}")
        print("提示: 请确保已正确配置 OKX 账户信息")


if __name__ == "__main__":
    print("DataPublisher 使用示例\n")
    print("=" * 50)
    
    try:
        # 运行基础示例
        example_basic_usage()
        
        # 取消注释以运行其他示例
        # example_factor_calculator()
        # example_reactive_trading()
        
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()

