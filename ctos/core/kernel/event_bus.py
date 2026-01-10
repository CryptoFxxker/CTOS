# -*- coding: utf-8 -*-
# ctos/core/kernel/event_bus.py
"""
可扩展的事件总线系统，支持发布/订阅模式。
用于实时市场数据、账户数据、因子分发、交易响应等场景。
"""
import threading
import time
import inspect
from collections import defaultdict
from typing import Callable, Dict, List, Any, Optional
import queue
import json


class EventBus:
    """
    事件总线 - 支持同步和异步事件分发
    
    主题命名规范:
    - market.price.{symbol}          - 实时价格数据
    - market.orderbook.{symbol}      - 订单簿数据
    - market.kline.{symbol}.{tf}     - K线数据
    - market.ticker.{symbol}         - 24小时行情数据
    - account.balance.{currency}     - 账户余额
    - account.position.{symbol}      - 持仓信息
    - account.order.{symbol}         - 订单状态更新
    - factor.{name}                  - 因子数据
    - trade.order.{action}           - 交易操作响应
    - system.error                   - 系统错误
    - system.status                  - 系统状态
    """
    
    def __init__(self, async_mode=True, max_queue_size=1000):
        """
        初始化事件总线
        
        :param async_mode: 是否启用异步模式（使用后台线程处理）
        :param max_queue_size: 异步队列最大大小
        """
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._wildcard_subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._lock = threading.RLock()
        self._async_mode = async_mode
        self._queue = queue.Queue(maxsize=max_queue_size) if async_mode else None
        self._worker_thread = None
        self._running = False
        self._stats = {
            'published': 0,
            'delivered': 0,
            'dropped': 0,
            'errors': 0
        }
    
    def start(self):
        """启动异步处理线程"""
        if self._async_mode and not self._running:
            self._running = True
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()
            print("✓ EventBus 异步工作线程已启动")
    
    def stop(self):
        """停止异步处理线程"""
        if self._running:
            self._running = False
            if self._queue:
                self._queue.put(None)  # 发送停止信号
            if self._worker_thread:
                self._worker_thread.join(timeout=2)
            print("✓ EventBus 已停止")
    
    def subscribe(self, topic: str, handler: Callable, wildcard: bool = False):
        """
        订阅主题
        
        :param topic: 主题名称，支持通配符如 'market.*' 或 'market.price.*'
        :param handler: 回调函数 handler(topic, message)
        :param wildcard: 是否启用通配符匹配（实验性功能）
        """
        with self._lock:
            if wildcard or '*' in topic:
                self._wildcard_subscribers[topic].append(handler)
            else:
                self._subscribers[topic].append(handler)
        print(f"✓ 已订阅主题: {topic}")
    
    def unsubscribe(self, topic: str, handler: Callable = None):
        """
        取消订阅
        
        :param topic: 主题名称
        :param handler: 要移除的处理器，如果为None则移除该主题所有订阅
        """
        with self._lock:
            if handler is None:
                if topic in self._subscribers:
                    del self._subscribers[topic]
                if topic in self._wildcard_subscribers:
                    del self._wildcard_subscribers[topic]
            else:
                if topic in self._subscribers:
                    try:
                        self._subscribers[topic].remove(handler)
                    except ValueError:
                        pass
                if topic in self._wildcard_subscribers:
                    try:
                        self._wildcard_subscribers[topic].remove(handler)
                    except ValueError:
                        pass
    
    def publish(self, topic: str, message: Any, sync: bool = False):
        """
        发布事件
        
        :param topic: 主题名称
        :param message: 消息内容（可以是字典、字符串等）
        :param sync: 是否同步发布（立即处理，不使用队列）
        """
        self._stats['published'] += 1
        
        # 添加元数据
        event = {
            'topic': topic,
            'message': message,
            'timestamp': time.time(),
            'ts_ms': int(time.time() * 1000)
        }
        
        if sync or not self._async_mode:
            self._deliver(topic, event)
        else:
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                self._stats['dropped'] += 1
                print(f"⚠ 事件队列已满，丢弃事件: {topic}")
    
    def _worker_loop(self):
        """异步工作线程循环"""
        while self._running:
            try:
                event = self._queue.get(timeout=1)
                if event is None:  # 停止信号
                    break
                self._deliver(event['topic'], event)
            except queue.Empty:
                continue
            except Exception as e:
                self._stats['errors'] += 1
                print(f"✗ EventBus 处理错误: {e}")
    
    def _deliver(self, topic: str, event: Dict):
        """分发事件到所有订阅者"""
        handlers = []
        
        with self._lock:
            # 精确匹配
            handlers.extend(self._subscribers.get(topic, []))
            
            # 通配符匹配
            topic_parts = topic.split('.')
            for pattern, pattern_handlers in self._wildcard_subscribers.items():
                if self._match_wildcard(pattern, topic):
                    handlers.extend(pattern_handlers)
        
        # 执行处理器
        for handler in handlers:
            try:
                # 支持不同的处理器签名：
                # - handler(topic, message)
                # - handler(topic, message, event)
                sig = inspect.signature(handler)
                param_count = len(sig.parameters)
                
                if param_count >= 3:
                    # 支持接收 event 参数的处理器
                    handler(topic, event['message'], event)
                elif param_count == 2:
                    # 只接收 topic 和 message 的处理器
                    handler(topic, event['message'])
                else:
                    # 兼容其他可能的签名
                    handler(topic, event['message'], event)
                
                self._stats['delivered'] += 1
            except Exception as e:
                self._stats['errors'] += 1
                print(f"✗ 处理器执行错误 [{topic}]: {e}")
    
    def _match_wildcard(self, pattern: str, topic: str) -> bool:
        """通配符匹配（简单实现）"""
        if pattern == topic:
            return True
        
        # 支持 'market.*' 和 'market.price.*' 等
        pattern_parts = pattern.split('.')
        topic_parts = topic.split('.')
        
        if len(pattern_parts) != len(topic_parts):
            return False
        
        for p, t in zip(pattern_parts, topic_parts):
            if p == '*' or p == t:
                continue
            return False
        return True
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self._stats.copy()
    
    def clear_stats(self):
        """清空统计信息"""
        self._stats = {
            'published': 0,
            'delivered': 0,
            'dropped': 0,
            'errors': 0
        }


# 全局单例（可选）
_global_event_bus: Optional[EventBus] = None


def get_event_bus(async_mode: bool = True) -> EventBus:
    """获取全局事件总线单例"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus(async_mode=async_mode)
        _global_event_bus.start()
    return _global_event_bus


def reset_event_bus():
    """重置全局事件总线（主要用于测试）"""
    global _global_event_bus
    if _global_event_bus:
        _global_event_bus.stop()
    _global_event_bus = None
