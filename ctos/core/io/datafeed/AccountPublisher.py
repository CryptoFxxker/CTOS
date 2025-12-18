# -*- coding: utf-8 -*-
# ctos/core/io/datafeed/AccountPublisher.py
"""
账户数据发布器 - 从OKX驱动获取账户数据，通过事件总线分发

专注于账户数据：
- 账户余额
- 持仓信息
- 订单状态
"""
import time
import threading
from typing import List, Dict, Optional, Callable
from collections import defaultdict

try:
    from ctos.core.kernel.event_bus import EventBus, get_event_bus
except ImportError:
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
    from ctos.core.kernel.event_bus import EventBus, get_event_bus

try:
    from ctos.drivers.okx.driver import OkxDriver
except ImportError:
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))
    from ctos.drivers.okx.driver import OkxDriver


class AccountPublisher:
    """
    账户数据发布器
    
    功能:
    1. 定期从OKX驱动获取账户数据（余额、持仓、订单状态）
    2. 通过事件总线分发账户数据
    3. 支持可配置的更新频率
    4. 支持多账户监控
    """
    
    def __init__(self, 
                 driver: Optional[OkxDriver] = None,
                 event_bus: Optional[EventBus] = None,
                 account_id: int = 0,
                 symbols: List[str] = None,
                 balance_interval: float = 5.0,
                 position_interval: float = 5.0,
                 order_interval: float = 3.0):
        """
        初始化账户数据发布器
        
        :param driver: OKX驱动实例，如果为None则自动创建
        :param event_bus: 事件总线实例，如果为None则使用全局单例
        :param account_id: 账户ID
        :param symbols: 要监控订单的交易对列表（可选），如果为None则监控所有持仓的交易对
        :param balance_interval: 余额更新间隔（秒）
        :param position_interval: 持仓更新间隔（秒）
        :param order_interval: 订单状态更新间隔（秒）
        """
        self.driver = driver or OkxDriver(account_id=account_id)
        self.event_bus = event_bus or get_event_bus()
        self.account_id = account_id
        
        # 默认交易对（用于订单监控，如果为None则在运行时动态获取）
        self.symbols = symbols
        if self.symbols is not None:
            self.symbols = [self._normalize_symbol(s) for s in self.symbols]
        
        # 更新间隔配置
        self.intervals = {
            'balance': balance_interval,
            'position': position_interval,
            'order': order_interval
        }
        
        # 运行状态
        self._running = False
        self._threads = []
        self._last_update = defaultdict(float)
        self._error_count = defaultdict(int)
        
        # 统计数据
        self._stats = {
            'balance_published': 0,
            'position_published': 0,
            'order_published': 0,
            'errors': 0
        }
        
        print(f"✓ AccountPublisher 初始化完成 (账户ID: {account_id})")
    
    def _normalize_symbol(self, symbol: str) -> str:
        """规范化交易对符号"""
        if isinstance(symbol, str):
            symbol = symbol.upper()
            if '-' not in symbol:
                symbol = f"{symbol}-USDT-SWAP"
            elif not symbol.endswith('-SWAP') and '-USDT' in symbol:
                symbol = symbol + '-SWAP'
        return symbol
    
    def start(self):
        """启动账户数据发布器"""
        if self._running:
            print("⚠ AccountPublisher 已在运行")
            return
        
        self._running = True
        
        # 启动各个账户数据源的发布线程
        self._threads = [
            threading.Thread(target=self._balance_loop, daemon=True, name="BalancePublisher"),
            threading.Thread(target=self._position_loop, daemon=True, name="PositionPublisher"),
            threading.Thread(target=self._order_loop, daemon=True, name="OrderPublisher"),
        ]
        
        for thread in self._threads:
            thread.start()
        
        print("✓ AccountPublisher 已启动，开始发布账户数据...")
    
    def stop(self):
        """停止账户数据发布器"""
        if not self._running:
            return
        
        self._running = False
        
        # 等待所有线程结束
        for thread in self._threads:
            thread.join(timeout=5)
        
        self._threads = []
        print("✓ AccountPublisher 已停止")
    
    # ========== 账户数据发布 ==========
    
    def _balance_loop(self):
        """账户余额数据发布循环"""
        while self._running:
            try:
                try:
                    balance = self.driver.fetch_balance('USDT')
                    
                    if balance:
                        data = {
                            'account_id': self.account_id,
                            'balance': balance,
                            'timestamp': time.time(),
                            'ts_ms': int(time.time() * 1000)
                        }
                        
                        # 发布到通用主题
                        self.event_bus.publish('account.balance.USDT', data)
                        
                        # 也发布到所有余额主题（如果有多个币种）
                        if isinstance(balance, dict) and 'currency' in balance:
                            currency = balance.get('currency', 'USDT')
                            topic = f"account.balance.{currency}"
                            self.event_bus.publish(topic, data)
                        else:
                            # 如果没有currency字段，默认发布到USDT
                            self.event_bus.publish('account.balance.USDT', data)
                        
                        self._stats['balance_published'] += 1
                        self._last_update['balance'] = time.time()
                
                except Exception as e:
                    self._handle_error('balance', 'USDT', e)
                
                time.sleep(self.intervals['balance'])
                
            except Exception as e:
                self._handle_error('balance', 'loop', e)
                time.sleep(self.intervals['balance'])
    
    def _position_loop(self):
        """持仓数据发布循环"""
        while self._running:
            try:
                try:
                    positions, err = self.driver.get_position(keep_origin=False)
                    
                    if not err and positions:
                        # 发布所有持仓
                        if isinstance(positions, list):
                            for pos in positions:
                                symbol = pos.get('symbol')
                                if symbol:
                                    topic = f"account.position.{symbol}"
                                    data = {
                                        'account_id': self.account_id,
                                        'position': pos,
                                        'timestamp': time.time(),
                                        'ts_ms': int(time.time() * 1000)
                                    }
                                    self.event_bus.publish(topic, data)
                                    self._stats['position_published'] += 1
                            
                            # 也发布汇总信息
                            self.event_bus.publish('account.position.all', {
                                'account_id': self.account_id,
                                'positions': positions,
                                'count': len(positions),
                                'timestamp': time.time(),
                                'ts_ms': int(time.time() * 1000)
                            })
                            
                            # 如果没有指定交易对列表，从持仓中获取用于订单监控
                            if self.symbols is None:
                                self.symbols = [pos.get('symbol') for pos in positions if pos.get('symbol')]
                        else:
                            # 单个持仓
                            symbol = positions.get('symbol') if isinstance(positions, dict) else None
                            if symbol:
                                topic = f"account.position.{symbol}"
                                self.event_bus.publish(topic, {
                                    'account_id': self.account_id,
                                    'position': positions,
                                    'timestamp': time.time(),
                                    'ts_ms': int(time.time() * 1000)
                                })
                                self._stats['position_published'] += 1
                                
                                # 如果没有指定交易对列表，使用当前持仓的交易对
                                if self.symbols is None:
                                    self.symbols = [symbol]
                        
                        self._last_update['position'] = time.time()
                
                except Exception as e:
                    self._handle_error('position', 'all', e)
                
                time.sleep(self.intervals['position'])
                
            except Exception as e:
                self._handle_error('position', 'loop', e)
                time.sleep(self.intervals['position'])
    
    def _order_loop(self):
        """订单状态数据发布循环"""
        while self._running:
            try:
                # 如果没有指定交易对，跳过订单监控（等待持仓数据更新）
                if self.symbols is None:
                    time.sleep(self.intervals['order'])
                    continue
                
                for symbol in self.symbols:
                    if not self._running:
                        break
                    
                    try:
                        orders, err = self.driver.get_open_orders(symbol=symbol, keep_origin=False)
                        
                        if not err and orders:
                            if isinstance(orders, list):
                                for order in orders:
                                    order_id = order.get('orderId')
                                    if order_id:
                                        topic = f"account.order.{symbol}"
                                        data = {
                                            'account_id': self.account_id,
                                            'order': order,
                                            'timestamp': time.time(),
                                            'ts_ms': int(time.time() * 1000)
                                        }
                                        self.event_bus.publish(topic, data)
                                        self._stats['order_published'] += 1
                            
                            # 发布订单列表
                            self.event_bus.publish(f"account.order.{symbol}.list", {
                                'account_id': self.account_id,
                                'symbol': symbol,
                                'orders': orders if isinstance(orders, list) else [orders],
                                'count': len(orders) if isinstance(orders, list) else 1,
                                'timestamp': time.time(),
                                'ts_ms': int(time.time() * 1000)
                            })
                            
                            self._last_update[f'order_{symbol}'] = time.time()
                    
                    except Exception as e:
                        self._handle_error('order', symbol, e)
                    
                    time.sleep(0.5)
                
                time.sleep(self.intervals['order'])
                
            except Exception as e:
                self._handle_error('order', 'loop', e)
                time.sleep(self.intervals['order'])
    
    # ========== 辅助方法 ==========
    
    def _handle_error(self, data_type: str, identifier: str, error: Exception):
        """处理错误"""
        self._error_count[f"{data_type}_{identifier}"] += 1
        self._stats['errors'] += 1
        
        # 错误计数超过阈值时打印警告
        if self._error_count[f"{data_type}_{identifier}"] % 10 == 0:
            print(f"⚠ [{data_type}:{identifier}] 错误计数: {self._error_count[f'{data_type}_{identifier}']}, 错误: {error}")
    
    def add_symbol(self, symbol: str):
        """添加要监控订单的交易对"""
        normalized = self._normalize_symbol(symbol)
        if self.symbols is None:
            self.symbols = []
        if normalized not in self.symbols:
            self.symbols.append(normalized)
            print(f"✓ 已添加交易对: {normalized}")
    
    def remove_symbol(self, symbol: str):
        """移除要监控订单的交易对"""
        normalized = self._normalize_symbol(symbol)
        if self.symbols and normalized in self.symbols:
            self.symbols.remove(normalized)
            print(f"✓ 已移除交易对: {normalized}")
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self._stats,
            'account_id': self.account_id,
            'symbols_count': len(self.symbols) if self.symbols else 0,
            'symbols': self.symbols,
            'last_updates': dict(self._last_update),
            'error_counts': dict(self._error_count),
            'event_bus_stats': self.event_bus.get_stats()
        }
    
    def publish_custom(self, topic: str, message: Dict):
        """发布自定义消息（用于扩展）"""
        data = {
            **message,
            'account_id': self.account_id,
            'timestamp': time.time(),
            'ts_ms': int(time.time() * 1000)
        }
        self.event_bus.publish(topic, data)


# ========== 使用示例 ==========

if __name__ == "__main__":
    # 示例：如何使用 AccountPublisher
    
    # 1. 创建事件处理器
    def balance_handler(topic, message, event):
        print(f"[余额更新] 账户ID {message.get('account_id')}: {message.get('balance')}")
    
    def position_handler(topic, message, event):
        pos = message.get('position', {})
        print(f"[持仓更新] {pos.get('symbol')}: {pos.get('side')} {pos.get('quantity')}")
    
    # 2. 获取事件总线并订阅
    bus = get_event_bus()
    bus.subscribe('account.balance.USDT', balance_handler)
    bus.subscribe('account.position.*', position_handler, wildcard=True)
    
    # 3. 创建并启动账户数据发布器
    publisher = AccountPublisher(
        account_id=0,
        symbols=['ETH-USDT-SWAP', 'BTC-USDT-SWAP'],  # 可选，用于订单监控
        balance_interval=5.0,
        position_interval=5.0,
        order_interval=3.0
    )
    
    publisher.start()
    
    try:
        # 运行一段时间
        time.sleep(30)
        
        # 打印统计信息
        print("\n=== 统计信息 ===")
        stats = publisher.get_stats()
        for key, value in stats.items():
            if key not in ['last_updates', 'error_counts']:
                print(f"{key}: {value}")
        
    finally:
        publisher.stop()
        bus.stop()

