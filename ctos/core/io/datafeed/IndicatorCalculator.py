# -*- coding: utf-8 -*-
# ctos/core/io/datafeed/IndicatorCalculator.py
"""
技术指标计算器 - 支持从DataHandler和事件总线获取数据，计算技术指标并发布因子
"""
import pandas as pd
import time
import threading
import uuid
from collections import defaultdict
from typing import Optional, Dict, List, Callable

# 兼容原有导入
try:
    from Config import ACCESS_KEY, SECRET_KEY, PASSPHRASE, HOST_IP, HOST_USER, HOST_PASSWD, HOST_IP_1
    from DataHandler import DataHandler
except ImportError:
    # 如果无法导入，使用备用方案
    pass

try:
    from ctos.core.kernel.event_bus import EventBus, get_event_bus
except ImportError:
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))
    from ctos.core.kernel.event_bus import EventBus, get_event_bus


class IndicatorCalculator:
    def __init__(self, data_handler=None, event_bus=None, enable_event_bus=False, max_history_size=500):
        """
        Initialize IndicatorCalculator class.
        
        :param data_handler: An instance of DataHandler class for fetching trading data (可选)
        :param event_bus: EventBus instance (可选，默认使用全局单例)
        :param enable_event_bus: 是否启用事件总线模式
        :param max_history_size: 最大历史数据条数（用于事件总线模式）
        """
        self.data_handler = data_handler
        self.enable_event_bus = enable_event_bus
        self.max_history_size = max_history_size
        
        # 事件总线相关
        if enable_event_bus:
            self.event_bus = event_bus or get_event_bus()
            # 为每个symbol+timeframe维护一个DataFrame历史
            self.data_history = defaultdict(lambda: pd.DataFrame())
            # 订阅的symbols和timeframes（用于持续订阅模式）
            self.subscribed_symbols = set()
            self.subscribed_timeframes = set()
            # 请求处理相关
            self.pending_requests = {}  # {request_id: RequestContext}
            self.request_lock = threading.RLock()
            # 订阅请求主题
            self.event_bus.subscribe('factor.request', self._handle_factor_request)
            self.event_bus.subscribe('factor.request.*', self._handle_factor_request, wildcard=True)
            
            print('✓ IndicatorCalculator 已启用事件总线模式（支持请求-响应）')
        else:
            self.event_bus = None
            self.data_history = {}
            self.pending_requests = {}
            print('✓ IndicatorCalculator 初始化成功（DataHandler模式）')

    def add_sma(self, df, column='close', window=14):
        sma_column_name = f'ma{window}'
        if sma_column_name not in df.columns:
            df[sma_column_name] = df[column].rolling(window=window).mean()
        return df

    def add_ema(self, df, column='close', span=14):
        ema_column_name = f'ema{span}'
        if ema_column_name not in df.columns:
            df[ema_column_name] = df[column].ewm(span=span, adjust=False).mean()
        return df

    def add_ma_v(self, df, column='vol', window=14):
        sma_column_name = f'ma_v_{window}'
        if sma_column_name not in df.columns:
            df[sma_column_name] = df[column].rolling(window=window).mean()
        return df

    def add_rsi(self, df, column='close', window=14):
        rsi_column_name = f'rsi_{window}'
        if rsi_column_name not in df.columns:
            delta = df[column].diff()
            gain = (delta.where(delta > 0, 0)).fillna(0)
            loss = (-delta.where(delta < 0, 0)).fillna(0)
            avg_gain = gain.rolling(window=window).mean()
            avg_loss = loss.rolling(window=window).mean()
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            df[rsi_column_name] = rsi
        return df

    def add_bollinger_bands(self, df, column='close', window=20):
        upper_band_name = f'bollinger_upper'
        lower_band_name = f'bollinger_lower'
        sma = df[column].rolling(window=window).mean()
        if upper_band_name not in df.columns or lower_band_name not in df.columns:
            std = df[column].rolling(window=window).std()
            df[upper_band_name] = sma + (std * 2)
            df[lower_band_name] = sma - (std * 2)
        df['bollinger_middle'] = sma
        return df

    def add_macd(self, df, column='close', fast=12, slow=26, signal=9):
        macd_name = 'macd'
        signal_name = 'signal'
        if macd_name not in df.columns or signal_name not in df.columns:
            exp1 = df[column].ewm(span=fast, adjust=False).mean()
            exp2 = df[column].ewm(span=slow, adjust=False).mean()
            macd = exp1 - exp2
            df[macd_name] = macd
            df[signal_name] = macd.ewm(span=signal, adjust=False).mean()
        return df

    def add_stochastic_oscillator(self, df, high_col='high', low_col='low', close_col='close', k_window=14, d_window=3):
        k_name = 'stochastic_k'
        d_name = 'stochastic_d'
        if k_name not in df.columns or d_name not in df.columns:
            df[high_col] = df[high_col].astype(float)
            df[low_col] = df[low_col].astype(float)
            df[close_col] = df[close_col].astype(float)
            low_min = df[low_col].rolling(window=k_window).min()
            high_max = df[high_col].rolling(window=k_window).max()
            k = 100 * ((df[close_col] - low_min) / (high_max - low_min))
            df[k_name] = k
            df[d_name] = k.rolling(window=d_window).mean()
        return df

    def update_indicators(self, df):
        df = self.add_sma(df, window=7)
        df = self.add_sma(df, window=20)
        df = self.add_sma(df, window=30)
        df = self.add_ma_v(df, window=5)
        df = self.add_ma_v(df, window=10)
        df = self.add_ma_v(df, window=20)
        df = self.add_ema(df, span=7)
        df = self.add_ema(df, span=20)
        df = self.add_ema(df, span=30)
        df = self.add_rsi(df)
        df = self.add_bollinger_bands(df)
        df = self.add_macd(df)
        df = self.add_stochastic_oscillator(df)
        return df
    
    # ========== 事件总线相关方法 ==========
    
    def start_event_bus_mode(self, symbols: List[str], timeframes: List[str] = None):
        """
        启动事件总线模式，订阅K线数据
        
        :param symbols: 要订阅的交易对列表，如 ['ETH-USDT-SWAP', 'BTC-USDT-SWAP']
        :param timeframes: 要订阅的时间周期列表，如 ['1m', '5m', '1h']，如果为None则订阅所有
        """
        if not self.enable_event_bus:
            print("⚠ 事件总线模式未启用，请在初始化时设置 enable_event_bus=True")
            return
        
        if timeframes is None:
            timeframes = ['1m', '5m', '15m', '1h']
        
        self.subscribed_symbols = set(symbols)
        self.subscribed_timeframes = set(timeframes)
        
        # 订阅所有symbol和timeframe的组合
        for symbol in symbols:
            for tf in timeframes:
                topic = f"market.kline.{symbol}.{tf}"
                self.event_bus.subscribe(topic, self._on_kline_update)
                print(f"✓ 已订阅K线数据: {topic}")
        
        print(f"✓ IndicatorCalculator 事件总线模式已启动，监控 {len(symbols)} 个交易对")
    
    def _on_kline_update(self, topic, message, event):
        """处理K线数据更新"""
        try:
            symbol = message.get('symbol')
            timeframe = message.get('timeframe')
            kline_data = message.get('kline')
            
            if not all([symbol, timeframe, kline_data]):
                return
            
            key = f"{symbol}_{timeframe}"
            
            # 解析K线数据
            if isinstance(kline_data, dict):
                # 如果kline是字典，转换为DataFrame行
                new_row = self._kline_dict_to_row(kline_data, symbol, timeframe)
            elif isinstance(kline_data, list):
                # 如果是列表，取最后一个
                if len(kline_data) > 0:
                    kline = kline_data[-1]
                    new_row = self._kline_dict_to_row(kline, symbol, timeframe)
                else:
                    return
            else:
                return
            
            # 更新历史数据
            if key in self.data_history and not self.data_history[key].empty:
                df = self.data_history[key]
                # 检查是否是新数据（基于时间戳）
                new_ts = new_row.get('ts', 0) if isinstance(new_row, dict) else new_row.get('trade_date', None)
                last_ts = df.iloc[-1].get('ts', 0) if 'ts' in df.columns else None
                
                if new_ts and last_ts and new_ts > last_ts:
                    # 追加新数据
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                elif new_ts and last_ts and new_ts == last_ts:
                    # 更新最后一行数据
                    df.iloc[-1] = new_row
                else:
                    # 追加新数据
                    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            else:
                # 初始化
                df = pd.DataFrame([new_row])
            
            # 限制历史数据大小
            if len(df) > self.max_history_size:
                df = df.tail(self.max_history_size).reset_index(drop=True)
            
            self.data_history[key] = df
            
            # 计算指标并发布因子
            if len(df) >= 30:  # 至少需要30条数据才能计算大部分指标
                self._calculate_and_publish_factors(symbol, timeframe, df)
        
        except Exception as e:
            print(f"✗ 处理K线数据错误 [{topic}]: {e}")
    
    def _kline_dict_to_row(self, kline: Dict, symbol: str, timeframe: str) -> Dict:
        """将K线字典转换为DataFrame行格式"""
        # 标准化K线数据格式（兼容不同格式）
        if isinstance(kline, dict):
            row = {
                'trade_date': pd.to_datetime(kline.get('ts', kline.get('time', time.time() * 1000)), unit='ms'),
                'open': float(kline.get('open', kline.get('Open', 0))),
                'high': float(kline.get('high', kline.get('High', 0))),
                'low': float(kline.get('low', kline.get('Low', 0))),
                'close': float(kline.get('close', kline.get('Close', 0))),
                'vol': float(kline.get('volume', kline.get('vol', kline.get('vol1', 0)))),
                'vol1': float(kline.get('vol1', kline.get('volume', 0))),
                'symbol': symbol,
                'timeframe': timeframe,
                'ts': kline.get('ts', kline.get('time', int(time.time() * 1000)))
            }
        else:
            row = {
                'trade_date': pd.Timestamp.now(),
                'open': 0, 'high': 0, 'low': 0, 'close': 0, 'vol': 0, 'vol1': 0,
                'symbol': symbol, 'timeframe': timeframe, 'ts': int(time.time() * 1000)
            }
        return row
    
    def _calculate_and_publish_factors(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """计算指标并发布因子"""
        try:
            # 确保数据类型正确
            for col in ['open', 'high', 'low', 'close', 'vol']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 计算所有指标
            df_with_indicators = self.update_indicators(df.copy())
            
            # 获取最新一行的指标值
            if len(df_with_indicators) == 0:
                return
            
            latest = df_with_indicators.iloc[-1]
            
            # 构建因子数据
            factors = {
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': time.time(),
                'ts_ms': int(time.time() * 1000),
                'price': float(latest.get('close', 0)),
                
                # 移动平均线
                'ma7': float(latest.get('ma7', 0)) if 'ma7' in latest else None,
                'ma20': float(latest.get('ma20', 0)) if 'ma20' in latest else None,
                'ma30': float(latest.get('ma30', 0)) if 'ma30' in latest else None,
                
                # 指数移动平均线
                'ema7': float(latest.get('ema7', 0)) if 'ema7' in latest else None,
                'ema20': float(latest.get('ema20', 0)) if 'ema20' in latest else None,
                'ema30': float(latest.get('ema30', 0)) if 'ema30' in latest else None,
                
                # 成交量移动平均
                'ma_v_5': float(latest.get('ma_v_5', 0)) if 'ma_v_5' in latest else None,
                'ma_v_10': float(latest.get('ma_v_10', 0)) if 'ma_v_10' in latest else None,
                'ma_v_20': float(latest.get('ma_v_20', 0)) if 'ma_v_20' in latest else None,
                
                # RSI
                'rsi_14': float(latest.get('rsi_14', 0)) if 'rsi_14' in latest else None,
                
                # 布林带
                'bollinger_upper': float(latest.get('bollinger_upper', 0)) if 'bollinger_upper' in latest else None,
                'bollinger_middle': float(latest.get('bollinger_middle', 0)) if 'bollinger_middle' in latest else None,
                'bollinger_lower': float(latest.get('bollinger_lower', 0)) if 'bollinger_lower' in latest else None,
                
                # MACD
                'macd': float(latest.get('macd', 0)) if 'macd' in latest else None,
                'macd_signal': float(latest.get('signal', 0)) if 'signal' in latest else None,
                
                # 随机指标
                'stochastic_k': float(latest.get('stochastic_k', 0)) if 'stochastic_k' in latest else None,
                'stochastic_d': float(latest.get('stochastic_d', 0)) if 'stochastic_d' in latest else None,
            }
            
            # 计算交易信号（基于指标）
            signals = self._calculate_signals(factors, latest, df_with_indicators)
            factors['signals'] = signals
            
            # 发布到事件总线
            topic = f"factor.indicators.{symbol}.{timeframe}"
            self.event_bus.publish(topic, factors)
            
        except Exception as e:
            print(f"✗ 计算因子错误 [{symbol}.{timeframe}]: {e}")
    
    def _calculate_signals(self, factors: Dict, latest: pd.Series, df: pd.DataFrame) -> Dict:
        """基于指标计算交易信号"""
        signals = {}
        
        try:
            # MA信号
            if factors['ma7'] and factors['ma20']:
                if factors['ma7'] > factors['ma20']:
                    signals['ma_trend'] = 'bullish'
                else:
                    signals['ma_trend'] = 'bearish'
            
            # RSI信号
            if factors['rsi_14']:
                if factors['rsi_14'] > 70:
                    signals['rsi'] = 'overbought'
                elif factors['rsi_14'] < 30:
                    signals['rsi'] = 'oversold'
                else:
                    signals['rsi'] = 'neutral'
            
            # 布林带信号
            if all([factors['bollinger_upper'], factors['bollinger_lower'], factors['price']]):
                price = factors['price']
                upper = factors['bollinger_upper']
                lower = factors['bollinger_lower']
                if price > upper:
                    signals['bollinger'] = 'above_upper'
                elif price < lower:
                    signals['bollinger'] = 'below_lower'
                else:
                    signals['bollinger'] = 'in_band'
            
            # MACD信号
            if factors['macd'] and factors['macd_signal']:
                if factors['macd'] > factors['macd_signal']:
                    signals['macd'] = 'bullish'
                else:
                    signals['macd'] = 'bearish'
            
        except Exception as e:
            print(f"✗ 计算信号错误: {e}")
        
        return signals
    
    def get_latest_factors(self, symbol: str, timeframe: str) -> Optional[Dict]:
        """获取最新的因子数据（用于查询）"""
        key = f"{symbol}_{timeframe}"
        if key in self.data_history and len(self.data_history[key]) > 0:
            df = self.data_history[key]
            if len(df) >= 30:
                df_with_indicators = self.update_indicators(df.copy())
                latest = df_with_indicators.iloc[-1]
                # 返回与发布时相同的格式
                factors = {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'price': float(latest.get('close', 0)),
                    'ma7': float(latest.get('ma7', 0)) if 'ma7' in latest else None,
                    'ma20': float(latest.get('ma20', 0)) if 'ma20' in latest else None,
                    'rsi_14': float(latest.get('rsi_14', 0)) if 'rsi_14' in latest else None,
                    # ... 其他指标
                }
                return factors
        return None
    
    # ========== 请求-响应模式 ==========
    
    def request_factors(self, 
                       symbol: str, 
                       timeframe: str, 
                       min_data_points: int = 30,
                       timeout: float = 30.0,
                       response_topic: str = None) -> Dict:
        """
        请求因子计算（同步方式）
        
        :param symbol: 交易对，如 'ETH-USDT-SWAP'
        :param timeframe: 时间周期，如 '1m', '5m', '1h'
        :param min_data_points: 需要的最少数据点数
        :param timeout: 超时时间（秒）
        :param response_topic: 响应主题（用于异步响应，如果为None则同步返回）
        :return: 因子数据或错误信息
        """
        if not self.enable_event_bus:
            return {
                'success': False,
                'error': '事件总线模式未启用'
            }
        
        request_id = str(uuid.uuid4())
        key = f"{symbol}_{timeframe}"
        
        # 检查是否已有足够数据
        if key in self.data_history and len(self.data_history[key]) >= min_data_points:
            # 直接计算并返回
            df = self.data_history[key]
            factors = self._calculate_factors_from_df(symbol, timeframe, df)
            return {
                'success': True,
                'request_id': request_id,
                'data': factors
            }
        
        # 需要订阅数据并等待
        request_context = {
            'request_id': request_id,
            'symbol': symbol,
            'timeframe': timeframe,
            'min_data_points': min_data_points,
            'timeout': timeout,
            'start_time': time.time(),
            'response_topic': response_topic,
            'event': threading.Event(),
            'result': None,
            'subscriptions': []
        }
        
        with self.request_lock:
            self.pending_requests[request_id] = request_context
        
        # 尝试订阅K线数据
        subscription_success = self._subscribe_for_request(symbol, timeframe, request_id)
        
        if not subscription_success:
            with self.request_lock:
                self.pending_requests.pop(request_id, None)
            return {
                'success': False,
                'request_id': request_id,
                'error': f'无法订阅K线数据: market.kline.{symbol}.{timeframe}'
            }
        
        # 等待数据积累（如果是同步模式）
        if response_topic is None:
            # 同步等待
            if request_context['event'].wait(timeout=timeout):
                result = request_context['result']
                with self.request_lock:
                    self.pending_requests.pop(request_id, None)
                return result
            else:
                # 超时
                self._cleanup_request(request_id)
                return {
                    'success': False,
                    'request_id': request_id,
                    'error': f'请求超时（{timeout}秒）'
                }
        else:
            # 异步模式，返回请求ID
            return {
                'success': True,
                'request_id': request_id,
                'message': '请求已提交，响应将通过事件总线返回',
                'response_topic': response_topic
            }
    
    def _handle_factor_request(self, topic: str, message: Dict, event: Dict = None):
        """处理通过事件总线发送的因子请求"""
        try:
            symbol = message.get('symbol')
            timeframe = message.get('timeframe')
            request_id = message.get('request_id', str(uuid.uuid4()))
            min_data_points = message.get('min_data_points', 30)
            timeout = message.get('timeout', 30.0)
            response_topic = message.get('response_topic', f'factor.response.{request_id}')
            
            if not symbol or not timeframe:
                self._send_response(response_topic, {
                    'success': False,
                    'request_id': request_id,
                    'error': '缺少必要参数: symbol 和 timeframe'
                })
                return
            
            # 调用请求方法（异步模式）
            result = self.request_factors(
                symbol=symbol,
                timeframe=timeframe,
                min_data_points=min_data_points,
                timeout=timeout,
                response_topic=response_topic
            )
            
            # 如果直接有结果（已有足够数据），立即返回
            if result.get('success') and 'data' in result:
                self._send_response(response_topic, result)
        
        except Exception as e:
            print(f"✗ 处理因子请求错误: {e}")
            response_topic = message.get('response_topic', f'factor.response.{message.get("request_id", "unknown")}')
            self._send_response(response_topic, {
                'success': False,
                'request_id': message.get('request_id', 'unknown'),
                'error': f'处理请求时发生错误: {str(e)}'
            })
    
    def _subscribe_for_request(self, symbol: str, timeframe: str, request_id: str) -> bool:
        """为请求订阅K线数据"""
        try:
            topic = f"market.kline.{symbol}.{timeframe}"
            handler = lambda t, m, e: self._on_kline_update_for_request(t, m, e, request_id)
            
            self.event_bus.subscribe(topic, handler)
            
            with self.request_lock:
                if request_id in self.pending_requests:
                    self.pending_requests[request_id]['subscriptions'].append((topic, handler))
            
            return True
        except Exception as e:
            print(f"✗ 订阅失败 [{topic}]: {e}")
            return False
    
    def _on_kline_update_for_request(self, topic: str, message: Dict, event: Dict, request_id: str):
        """为特定请求处理K线数据更新"""
        try:
            with self.request_lock:
                if request_id not in self.pending_requests:
                    return
                
                request_context = self.pending_requests[request_id]
                symbol = request_context['symbol']
                timeframe = request_context['timeframe']
            
            # 更新历史数据（使用原有方法）
            self._on_kline_update(topic, message, event)
            
            key = f"{symbol}_{timeframe}"
            if key in self.data_history:
                df = self.data_history[key]
                
                # 检查数据是否足够
                if len(df) >= request_context['min_data_points']:
                    # 计算因子
                    factors = self._calculate_factors_from_df(symbol, timeframe, df)
                    
                    # 发送响应
                    response = {
                        'success': True,
                        'request_id': request_id,
                        'data': factors
                    }
                    
                    if request_context['response_topic']:
                        self._send_response(request_context['response_topic'], response)
                    
                    # 触发事件（同步模式）
                    request_context['result'] = response
                    request_context['event'].set()
                    
                    # 清理请求和订阅
                    self._cleanup_request(request_id)
                
                # 检查超时
                elif time.time() - request_context['start_time'] > request_context['timeout']:
                    response = {
                        'success': False,
                        'request_id': request_id,
                        'error': f'数据积累超时（{request_context["timeout"]}秒），当前数据点数: {len(df)}'
                    }
                    
                    if request_context['response_topic']:
                        self._send_response(request_context['response_topic'], response)
                    
                    request_context['result'] = response
                    request_context['event'].set()
                    self._cleanup_request(request_id)
        
        except Exception as e:
            print(f"✗ 处理请求K线数据错误 [{request_id}]: {e}")
    
    def _calculate_factors_from_df(self, symbol: str, timeframe: str, df: pd.DataFrame) -> Dict:
        """从DataFrame计算因子"""
        try:
            # 确保数据类型正确
            for col in ['open', 'high', 'low', 'close', 'vol']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # 计算所有指标
            df_with_indicators = self.update_indicators(df.copy())
            
            if len(df_with_indicators) == 0:
                return {}
            
            latest = df_with_indicators.iloc[-1]
            
            # 构建因子数据（与_calculate_and_publish_factors相同的格式）
            factors = {
                'symbol': symbol,
                'timeframe': timeframe,
                'timestamp': time.time(),
                'ts_ms': int(time.time() * 1000),
                'price': float(latest.get('close', 0)),
                
                'ma7': float(latest.get('ma7', 0)) if 'ma7' in latest else None,
                'ma20': float(latest.get('ma20', 0)) if 'ma20' in latest else None,
                'ma30': float(latest.get('ma30', 0)) if 'ma30' in latest else None,
                
                'ema7': float(latest.get('ema7', 0)) if 'ema7' in latest else None,
                'ema20': float(latest.get('ema20', 0)) if 'ema20' in latest else None,
                'ema30': float(latest.get('ema30', 0)) if 'ema30' in latest else None,
                
                'ma_v_5': float(latest.get('ma_v_5', 0)) if 'ma_v_5' in latest else None,
                'ma_v_10': float(latest.get('ma_v_10', 0)) if 'ma_v_10' in latest else None,
                'ma_v_20': float(latest.get('ma_v_20', 0)) if 'ma_v_20' in latest else None,
                
                'rsi_14': float(latest.get('rsi_14', 0)) if 'rsi_14' in latest else None,
                
                'bollinger_upper': float(latest.get('bollinger_upper', 0)) if 'bollinger_upper' in latest else None,
                'bollinger_middle': float(latest.get('bollinger_middle', 0)) if 'bollinger_middle' in latest else None,
                'bollinger_lower': float(latest.get('bollinger_lower', 0)) if 'bollinger_lower' in latest else None,
                
                'macd': float(latest.get('macd', 0)) if 'macd' in latest else None,
                'macd_signal': float(latest.get('signal', 0)) if 'signal' in latest else None,
                
                'stochastic_k': float(latest.get('stochastic_k', 0)) if 'stochastic_k' in latest else None,
                'stochastic_d': float(latest.get('stochastic_d', 0)) if 'stochastic_d' in latest else None,
            }
            
            # 计算信号
            signals = self._calculate_signals(factors, latest, df_with_indicators)
            factors['signals'] = signals
            
            return factors
        
        except Exception as e:
            print(f"✗ 计算因子错误 [{symbol}.{timeframe}]: {e}")
            return {}
    
    def _send_response(self, topic: str, response: Dict):
        """发送响应到事件总线"""
        try:
            self.event_bus.publish(topic, response)
        except Exception as e:
            print(f"✗ 发送响应错误 [{topic}]: {e}")
    
    def _cleanup_request(self, request_id: str):
        """清理请求和订阅"""
        try:
            with self.request_lock:
                if request_id in self.pending_requests:
                    request_context = self.pending_requests[request_id]
                    
                    # 取消订阅
                    for topic, handler in request_context['subscriptions']:
                        try:
                            self.event_bus.unsubscribe(topic, handler)
                        except Exception:
                            pass
                    
                    self.pending_requests.pop(request_id, None)
        except Exception as e:
            print(f"✗ 清理请求错误 [{request_id}]: {e}")



if __name__ == '__main__':
    import time as time_module
    
    # 示例1: 传统模式（使用DataHandler）
    try:
        data_handler = DataHandler(HOST_IP, 'TradingData', 'root', 'zzb162122')
        indicator_calculator = IndicatorCalculator(data_handler)

        symbol = 'ETH-USD-SWAP'
        interval = '1h'
        start_date = '2024-11-01'
        end_date = '2024-11-31'

        df = data_handler.fetch_data(symbol, interval, start_date, end_date)

        if not df.empty:
            df_with_indicators = indicator_calculator.update_indicators(df)
            print(df_with_indicators.head(50), df_with_indicators.tail(50), len(df_with_indicators))
        else:
            print("No data returned from the database.")

        data_handler.close()
    except Exception as e:
        print(f"传统模式运行失败: {e}")
    
    # 示例2: 请求-响应模式
    print("\n=== 请求-响应模式示例 ===\n")
    
    from ctos.core.io.datafeed.DataPublisher import DataPublisher
    from ctos.core.kernel.event_bus import get_event_bus
    
    bus = get_event_bus()
    
    # 创建指标计算器（事件总线模式）
    indicator_calc = IndicatorCalculator(enable_event_bus=True)
    
    # 启动市场数据发布器（提供K线数据）
    publisher = DataPublisher(
        symbols=['ETH-USDT-SWAP', 'BTC-USDT-SWAP'],
        kline_interval=5.0  # 5秒更新一次K线
    )
    publisher.start()
    
    try:
        print("等待数据发布器启动...\n")
        time_module.sleep(2)
        
        # 方式1: 同步请求（直接调用方法）
        print("=== 方式1: 同步请求 ===\n")
        result = indicator_calc.request_factors(
            symbol='ETH-USDT-SWAP',
            timeframe='1m',
            min_data_points=30,
            timeout=30.0
        )
        
        if result.get('success'):
            factors = result.get('data', {})
            print(f"✓ 请求成功:")
            print(f"  价格: ${factors.get('price', 0):.2f}")
            print(f"  RSI: {factors.get('rsi_14', 0):.2f}")
            print(f"  MA7: {factors.get('ma7', 0):.2f}")
            print(f"  MA20: {factors.get('ma20', 0):.2f}")
            print(f"  信号: {factors.get('signals', {})}")
        else:
            print(f"✗ 请求失败: {result.get('error')}")
        
        print("\n" + "="*50 + "\n")
        
        # 方式2: 异步请求（通过事件总线）
        print("=== 方式2: 异步请求（通过事件总线） ===\n")
        
        request_id = str(uuid.uuid4())
        response_topic = f'factor.response.{request_id}'
        
        # 订阅响应
        response_received = threading.Event()
        response_data = {}
        
        def response_handler(topic, message, event):
            if message.get('request_id') == request_id:
                response_data.update(message)
                response_received.set()
                print(f"✓ 收到响应: {message.get('success')}")
                if message.get('success'):
                    factors = message.get('data', {})
                    print(f"  价格: ${factors.get('price', 0):.2f}, RSI: {factors.get('rsi_14', 0):.2f}")
        
        bus.subscribe(response_topic, response_handler)
        
        # 发送请求
        bus.publish('factor.request', {
            'symbol': 'BTC-USDT-SWAP',
            'timeframe': '1m',
            'request_id': request_id,
            'response_topic': response_topic,
            'min_data_points': 30,
            'timeout': 30.0
        })
        
        # 等待响应
        if response_received.wait(timeout=35.0):
            if not response_data.get('success'):
                print(f"✗ 请求失败: {response_data.get('error')}")
        else:
            print("✗ 等待响应超时")
        
        print("\n" + "="*50 + "\n")
        
        # 方式3: 持续订阅模式（原有功能）
        print("=== 方式3: 持续订阅模式 ===\n")
        
        def factor_handler(topic, message, event):
            symbol = message.get('symbol')
            tf = message.get('timeframe')
            price = message.get('price')
            rsi = message.get('rsi_14')
            print(f"[自动发布] {symbol} {tf}: 价格=${price:.2f}, RSI={rsi:.2f}")
        
        bus.subscribe('factor.indicators.*', factor_handler, wildcard=True)
        
        # 启动持续订阅模式
        indicator_calc.start_event_bus_mode(
            symbols=['ETH-USDT-SWAP'],
            timeframes=['1m']
        )
        
        print("持续订阅模式运行中... (按 Ctrl+C 停止)\n")
        time_module.sleep(30)
        
    except KeyboardInterrupt:
        print("\n正在停止...")
    finally:
        publisher.stop()
        bus.stop()