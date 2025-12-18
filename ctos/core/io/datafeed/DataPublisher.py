# -*- coding: utf-8 -*-
# ctos/core/io/datafeed/DataPublisher.py
"""
实时市场数据发布器 - 从OKX驱动获取市场行情数据，通过事件总线分发

专注于市场行情数据：
- 实时价格
- 订单簿
- K线数据
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
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))
    from ctos.core.kernel.event_bus import EventBus, get_event_bus

try:
    from ctos.drivers.okx.driver import OkxDriver
except ImportError:
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))
    from ctos.drivers.okx.driver import OkxDriver


class DataPublisher:
    """
    实时市场数据发布器
    
    功能:
    1. 定期从OKX驱动获取市场行情数据（价格、订单簿、K线等）
    2. 通过事件总线分发市场数据
    3. 支持可配置的更新频率和符号列表
    
    注意: 账户数据请使用 AccountPublisher
    """
    
    def __init__(self, 
                 driver: Optional[OkxDriver] = None,
                 event_bus: Optional[EventBus] = None,
                 symbols: List[str] = None,
                 account_id: int = 0,
                 price_interval: float = 1.0,
                 orderbook_interval: float = 2.0,
                 kline_interval: float = 60.0):
        """
        初始化市场数据发布器
        
        :param driver: OKX驱动实例，如果为None则自动创建
        :param event_bus: 事件总线实例，如果为None则使用全局单例
        :param symbols: 要监控的交易对列表，如 ['ETH-USDT-SWAP', 'BTC-USDT-SWAP']
        :param account_id: 账户ID（仅用于创建驱动，不用于账户数据查询）
        :param price_interval: 价格更新间隔（秒）
        :param orderbook_interval: 订单簿更新间隔（秒）
        :param kline_interval: K线更新间隔（秒）
        """
        self.driver = driver or OkxDriver(account_id=account_id)
        self.event_bus = event_bus or get_event_bus()
        
        # 默认交易对
        if symbols is None:
            symbols = ['ETH-USDT-SWAP', 'BTC-USDT-SWAP']
        self.symbols = [self._normalize_symbol(s) for s in symbols]
        
        # 更新间隔配置
        self.intervals = {
            'price': price_interval,
            'orderbook': orderbook_interval,
            'kline': kline_interval
        }
        
        # 运行状态
        self._running = False
        self._threads = []
        self._last_update = defaultdict(float)
        self._error_count = defaultdict(int)
        
        # 统计数据
        self._stats = {
            'price_published': 0,
            'orderbook_published': 0,
            'kline_published': 0,
            'errors': 0
        }
        
        print(f"✓ DataPublisher 初始化完成 (监控 {len(self.symbols)} 个交易对)")
    
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
        """启动数据发布器"""
        if self._running:
            print("⚠ DataPublisher 已在运行")
            return
        
        self._running = True
        
        # 启动各个市场数据源的发布线程
        self._threads = [
            threading.Thread(target=self._price_loop, daemon=True, name="PricePublisher"),
            threading.Thread(target=self._orderbook_loop, daemon=True, name="OrderbookPublisher"),
            threading.Thread(target=self._kline_loop, daemon=True, name="KlinePublisher"),
        ]
        
        for thread in self._threads:
            thread.start()
        
        print("✓ DataPublisher 已启动，开始发布数据...")
    
    def stop(self):
        """停止数据发布器"""
        if not self._running:
            return
        
        self._running = False
        
        # 等待所有线程结束
        for thread in self._threads:
            thread.join(timeout=5)
        
        self._threads = []
        print("✓ DataPublisher 已停止")
    
    # ========== 市场数据发布 ==========
    
    def _price_loop(self):
        """价格数据发布循环"""
        while self._running:
            try:
                for symbol in self.symbols:
                    if not self._running:
                        break
                    
                    try:
                        price = self.driver.get_price_now(symbol)
                        
                        data = {
                            'symbol': symbol,
                            'price': price,
                            'timestamp': time.time(),
                            'ts_ms': int(time.time() * 1000)
                        }
                        
                        topic = f"market.price.{symbol}"
                        self.event_bus.publish(topic, data)
                        self._stats['price_published'] += 1
                        self._last_update[f'price_{symbol}'] = time.time()
                        
                    except Exception as e:
                        self._handle_error('price', symbol, e)
                    
                    # 短暂延迟，避免请求过快
                    time.sleep(0.1)
                
                time.sleep(self.intervals['price'])
                
            except Exception as e:
                self._handle_error('price', 'loop', e)
                time.sleep(self.intervals['price'])
    
    def _orderbook_loop(self):
        """订单簿数据发布循环"""
        while self._running:
            try:
                for symbol in self.symbols:
                    if not self._running:
                        break
                    
                    try:
                        orderbook = self.driver.get_orderbook(symbol, level=20)
                        
                        if orderbook and isinstance(orderbook, dict):
                            data = {
                                'symbol': symbol,
                                'bids': orderbook.get('bids', []),
                                'asks': orderbook.get('asks', []),
                                'timestamp': time.time(),
                                'ts_ms': int(time.time() * 1000)
                            }
                            
                            topic = f"market.orderbook.{symbol}"
                            self.event_bus.publish(topic, data)
                            self._stats['orderbook_published'] += 1
                            self._last_update[f'orderbook_{symbol}'] = time.time()
                    
                    except Exception as e:
                        self._handle_error('orderbook', symbol, e)
                    
                    time.sleep(0.2)
                
                time.sleep(self.intervals['orderbook'])
                
            except Exception as e:
                self._handle_error('orderbook', 'loop', e)
                time.sleep(self.intervals['orderbook'])
    
    def _kline_loop(self):
        """K线数据发布循环"""
        kline_timeframes = ['1m', '5m', '15m', '1h']  # 可根据需要调整
        
        while self._running:
            try:
                for symbol in self.symbols:
                    if not self._running:
                        break
                    
                    for tf in kline_timeframes:
                        if not self._running:
                            break
                        
                        try:
                            klines, err = self.driver.get_klines(symbol, timeframe=tf, limit=1)
                            
                            if not err and klines and len(klines) > 0:
                                latest_kline = klines[-1] if isinstance(klines, list) else klines
                                
                                data = {
                                    'symbol': symbol,
                                    'timeframe': tf,
                                    'kline': latest_kline,
                                    'timestamp': time.time(),
                                    'ts_ms': int(time.time() * 1000)
                                }
                                
                                topic = f"market.kline.{symbol}.{tf}"
                                self.event_bus.publish(topic, data)
                                self._stats['kline_published'] += 1
                                self._last_update[f'kline_{symbol}_{tf}'] = time.time()
                        
                        except Exception as e:
                            self._handle_error('kline', f"{symbol}.{tf}", e)
                        
                        time.sleep(0.3)
                    
                    time.sleep(0.5)
                
                time.sleep(self.intervals['kline'])
                
            except Exception as e:
                self._handle_error('kline', 'loop', e)
                time.sleep(self.intervals['kline'])
    
    # ========== 辅助方法 ==========
    
    def _handle_error(self, data_type: str, identifier: str, error: Exception):
        """处理错误"""
        self._error_count[f"{data_type}_{identifier}"] += 1
        self._stats['errors'] += 1
        
        # 错误计数超过阈值时打印警告
        if self._error_count[f"{data_type}_{identifier}"] % 10 == 0:
            print(f"⚠ [{data_type}:{identifier}] 错误计数: {self._error_count[f'{data_type}_{identifier}']}, 错误: {error}")
    
    def add_symbol(self, symbol: str):
        """添加要监控的交易对"""
        normalized = self._normalize_symbol(symbol)
        if normalized not in self.symbols:
            self.symbols.append(normalized)
            print(f"✓ 已添加交易对: {normalized}")
    
    def remove_symbol(self, symbol: str):
        """移除要监控的交易对"""
        normalized = self._normalize_symbol(symbol)
        if normalized in self.symbols:
            self.symbols.remove(normalized)
            print(f"✓ 已移除交易对: {normalized}")
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self._stats,
            'symbols_count': len(self.symbols),
            'symbols': self.symbols,
            'last_updates': dict(self._last_update),
            'error_counts': dict(self._error_count),
            'event_bus_stats': self.event_bus.get_stats()
        }
    
    def publish_custom(self, topic: str, message: Dict):
        """发布自定义消息（用于扩展，如因子数据等）"""
        data = {
            **message,
            'timestamp': time.time(),
            'ts_ms': int(time.time() * 1000)
        }
        self.event_bus.publish(topic, data)


# ========== 使用示例 ==========

if __name__ == "__main__":
    # 示例：如何使用 DataPublisher
    
    # 1. 创建事件处理器
    def price_handler(topic, message, event):
        print(f"[价格更新] {message.get('symbol')}: ${message.get('price')}")
    
    # 2. 获取事件总线并订阅
    bus = get_event_bus()
    bus.subscribe('market.price.ETH-USDT-SWAP', price_handler)
    
    # 3. 创建并启动市场数据发布器
    publisher = DataPublisher(
        symbols=['ETH-USDT-SWAP', 'BTC-USDT-SWAP'],
        account_id=0,
        price_interval=1.0
    )
    
    publisher.start()
    
    try:
        # 运行一段时间
        time.sleep(30)
        
        # 打印统计信息
        print("\n=== 统计信息 ===")
        stats = publisher.get_stats()
        for key, value in stats.items():
            print(f"{key}: {value}")
        
    finally:
        publisher.stop()
        bus.stop()

