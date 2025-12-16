# -*- coding: utf-8 -*-
"""
K线数据管理模块
提供K线数据获取、缓存功能
"""
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from pathlib import Path

# 动态添加项目路径
def _add_project_path():
    """添加项目路径到sys.path"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, '../../../../'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root

_PROJECT_ROOT = _add_project_path()

# 导入驱动
OKX_AVAILABLE = False

try:
    from ctos.drivers.okx.okex import OkexSpot
    OKX_AVAILABLE = True
    print("✓ OKX驱动导入成功 (K线模块)")
except ImportError as e:
    print(f"✗ OKX驱动导入失败 (K线模块): {e}")

# 导入API密钥读取函数
def load_api_keys_from_file(file_path: Optional[str] = None) -> Dict[str, str]:
    """
    从文本文件读取API密钥
    """
    api_keys = {}
    
    if file_path is None:
        # 尝试从funds目录读取api.txt
        current_dir = os.path.dirname(os.path.abspath(__file__))
        funds_dir = os.path.join(current_dir, '../funds')
        file_path = os.path.join(funds_dir, 'api.txt')
    
    if not os.path.exists(file_path):
        return api_keys
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    api_keys[key] = value
        
        if api_keys:
            print(f"✓ 从文件读取API密钥 (K线模块): {len(api_keys)} 个")
    except Exception as e:
        print(f"✗ 读取API密钥文件失败 (K线模块): {e}")
    
    return api_keys


class KlineDataManager:
    """K线数据管理器"""
    
    def __init__(self):
        """初始化K线数据管理器"""
        self.okx_client = None
        self.cache = {}  # 缓存K线数据: {(symbol, timeframe, limit): (data, timestamp)}
        self.cache_ttl = 60  # 缓存60秒
        
        # 初始化驱动
        self._init_driver()
    
    def _init_driver(self):
        """初始化OKX驱动（只读，用于获取K线数据）"""
        if not OKX_AVAILABLE:
            print("⚠ OKX驱动不可用，K线功能将受限")
            return
        
        try:
            # 优先从文件读取API密钥
            api_keys = load_api_keys_from_file()
            
            access_key = api_keys.get('OKX_API_KEY') or api_keys.get('OKX_ACCESS_KEY') or os.getenv('OKX_API_KEY') or os.getenv('OKX_ACCESS_KEY')
            secret_key = api_keys.get('OKX_SECRET_KEY') or api_keys.get('OKX_SECRET') or os.getenv('OKX_SECRET_KEY') or os.getenv('OKX_SECRET')
            passphrase = api_keys.get('OKX_PASSPHRASE') or os.getenv('OKX_PASSPHRASE')
            
            if access_key and secret_key and passphrase:
                self.okx_client = OkexSpot(
                    symbol="ETH-USDT-SWAP",
                    access_key=access_key,
                    secret_key=secret_key,
                    passphrase=passphrase,
                    host=None
                )
                print("✓ OKX驱动初始化成功 (K线模块)")
            else:
                print("⚠ OKX API密钥未配置，K线功能将受限（仅支持公开数据）")
        except Exception as e:
            print(f"✗ OKX驱动初始化失败 (K线模块): {e}")
    
    def _normalize_symbol(self, symbol: str) -> str:
        """
        标准化交易对符号
        btc -> BTC-USDT-SWAP
        BTC -> BTC-USDT-SWAP
        BTC-USDT -> BTC-USDT-SWAP
        """
        symbol = symbol.upper().strip()
        
        if '-' not in symbol:
            # 只有币种名称，添加USDT-SWAP后缀
            return f"{symbol}-USDT-SWAP"
        elif symbol.endswith('-SWAP'):
            # 已经是完整格式
            return symbol
        elif symbol.endswith('-USDT'):
            # 添加SWAP后缀
            return f"{symbol}-SWAP"
        else:
            # 其他格式，尝试添加-USDT-SWAP
            return f"{symbol}-USDT-SWAP"
    
    def _normalize_timeframe(self, timeframe: str) -> str:
        """
        标准化时间框架
        1m -> 1m
        1h -> 1H
        1d -> 1D
        """
        timeframe = timeframe.upper().strip()
        # OKX支持的时间框架
        valid_timeframes = ['1m', '3m', '5m', '15m', '30m', '1H', '2H', '4H', '6H', '12H', '1D', '1W', '1M']
        
        # 如果已经是标准格式，直接返回
        if timeframe in valid_timeframes:
            return timeframe
        
        # 尝试转换常见格式
        timeframe_map = {
            '1M': '1m', '5M': '5m', '15M': '15m', '30M': '30m',
            '1H': '1H', '4H': '4H', '1D': '1D', '1W': '1W'
        }
        
        return timeframe_map.get(timeframe, '1H')  # 默认1小时
    
    def get_kline_data(self, symbol: str, timeframe: str = '1H', limit: int = 200) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        获取K线数据
        
        Args:
            symbol: 交易对符号，如 'btc', 'BTC', 'BTC-USDT', 'BTC-USDT-SWAP'
            timeframe: 时间框架，如 '1m', '5m', '1H', '1D'
            limit: 获取的K线数量，默认200
            
        Returns:
            (kline_data, error_message)
            kline_data格式: [
                {
                    'timestamp': int,  # 时间戳（毫秒）
                    'open': float,
                    'high': float,
                    'low': float,
                    'close': float,
                    'volume': float
                },
                ...
            ]
        """
        try:
            # 标准化输入
            normalized_symbol = self._normalize_symbol(symbol)
            normalized_timeframe = self._normalize_timeframe(timeframe)
            
            # 检查缓存
            cache_key = (normalized_symbol, normalized_timeframe, limit)
            if cache_key in self.cache:
                cached_data, cached_time = self.cache[cache_key]
                if time.time() - cached_time < self.cache_ttl:
                    return cached_data, None
            
            # 如果驱动未初始化，返回错误
            if self.okx_client is None:
                return None, "OKX驱动未初始化，无法获取K线数据"
            
            # 调用OKX API获取K线数据
            try:
                # 使用get_kline_origin获取原始数据
                raw_data, error = self.okx_client.get_kline_origin(
                    interval=normalized_timeframe,
                    limit=limit,
                    symbol=normalized_symbol
                )
                
                if error:
                    return None, f"获取K线数据失败: {error}"
                
                if not raw_data:
                    return None, "未获取到K线数据"
                
                # 转换数据格式
                kline_data = []
                for item in raw_data:
                    # OKX返回格式: [timestamp, open, high, low, close, volume, volumeCcy, ...]
                    # timestamp可能是ISO字符串或毫秒时间戳
                    try:
                        timestamp = item[0]
                        # 如果是字符串，尝试转换为时间戳
                        if isinstance(timestamp, str):
                            # OKX返回的格式可能是 "2024-12-09T06:00:00.000Z" 或毫秒时间戳字符串
                            try:
                                # 先尝试作为毫秒时间戳解析
                                timestamp_ms = int(timestamp)
                            except ValueError:
                                # 如果不是数字，尝试解析ISO格式
                                from datetime import datetime
                                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                timestamp_ms = int(dt.timestamp() * 1000)
                        else:
                            # 如果是数字，确保是毫秒
                            timestamp_ms = int(timestamp)
                            # 如果时间戳看起来是秒（小于10000000000），转换为毫秒
                            if timestamp_ms < 10000000000:
                                timestamp_ms = timestamp_ms * 1000
                        
                        kline_data.append({
                            'timestamp': timestamp_ms,  # 时间戳（毫秒）
                            'open': float(item[1]),
                            'high': float(item[2]),
                            'low': float(item[3]),
                            'close': float(item[4]),
                            'volume': float(item[5]) if len(item) > 5 else 0.0
                        })
                    except (ValueError, IndexError, TypeError) as e:
                        print(f"解析K线数据项失败: {item}, 错误: {e}")
                        continue
                
                # 更新缓存
                self.cache[cache_key] = (kline_data, time.time())
                
                return kline_data, None
                
            except Exception as e:
                return None, f"获取K线数据异常: {str(e)}"
                
        except Exception as e:
            return None, f"处理K线请求失败: {str(e)}"
    
    def get_available_symbols(self) -> List[str]:
        """
        获取可用的交易对列表
        主流币种在前，从驱动获取的币种在后
        
        Returns:
            交易对列表，如 ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', ...]
        """
        # 定义主流币种列表（按优先级排序）
        mainstream_symbols = [
            'BTC-USDT-SWAP', 'ETH-USDT-SWAP', 'SOL-USDT-SWAP', 
            'XRP-USDT-SWAP', 'BNB-USDT-SWAP', 'ADA-USDT-SWAP', 
            'DOGE-USDT-SWAP', 'TRX-USDT-SWAP', 'LTC-USDT-SWAP', 
            'SHIB-USDT-SWAP', 'MATIC-USDT-SWAP', 'AVAX-USDT-SWAP',
            'DOT-USDT-SWAP', 'LINK-USDT-SWAP', 'UNI-USDT-SWAP'
        ]
        
        # 如果驱动未初始化，只返回主流币种
        if self.okx_client is None:
            return mainstream_symbols
        
        try:
            # 使用驱动获取所有可用的交易对
            all_symbols = []
            
            # 方法1: 尝试使用get_market方法
            if hasattr(self.okx_client, 'get_market'):
                data, error = self.okx_client.get_market(instId='', all=True, condition='SWAP')
                if not error and data:
                    all_symbols = [item.get('instId', '') for item in data if item.get('instId', '')]
            
            # 方法2: 如果方法1失败，尝试使用OkxDriver的symbols方法
            if not all_symbols:
                try:
                    from ctos.drivers.okx.driver import OkxDriver
                    driver = OkxDriver(okx_client=self.okx_client, mode='swap')
                    symbols_result, err = driver.symbols(instType='SWAP')
                    if not err and symbols_result:
                        all_symbols = symbols_result
                except Exception as e:
                    print(f"使用OkxDriver获取交易对失败: {e}")
            
            # 如果没有获取到任何交易对，返回主流币种
            if not all_symbols:
                print("⚠ 无法从驱动获取交易对列表，使用主流币种")
                return mainstream_symbols
            
            # 去重并排序：主流币种在前，其他币种在后
            mainstream_set = set(mainstream_symbols)
            other_symbols = [s for s in all_symbols if s not in mainstream_set]
            
            # 合并：主流币种 + 其他币种（按字母顺序排序）
            result = mainstream_symbols + sorted(other_symbols)
            
            print(f"✓ 获取到 {len(result)} 个交易对（主流币种: {len(mainstream_symbols)}, 其他: {len(other_symbols)}）")
            return result
            
        except Exception as e:
            print(f"获取交易对列表失败: {e}")
            return mainstream_symbols
    
    def get_available_coins(self) -> List[str]:
        """
        获取可用的币种列表（从交易对中提取币种名称）
        主流币种在前，从驱动获取的币种在后
        
        Returns:
            币种列表，如 ['btc', 'eth', 'sol', ...]
        """
        symbols = self.get_available_symbols()
        # 从交易对中提取币种名称（去掉-USDT-SWAP后缀）
        coins = []
        seen = set()
        
        for symbol in symbols:
            # 提取币种名称：BTC-USDT-SWAP -> btc
            coin = symbol.split('-')[0].lower()
            if coin and coin not in seen:
                coins.append(coin)
                seen.add(coin)
        
        return coins


# 全局实例
_global_kline_manager: Optional[KlineDataManager] = None

def get_kline_manager() -> KlineDataManager:
    """获取全局K线数据管理器实例"""
    global _global_kline_manager
    if _global_kline_manager is None:
        _global_kline_manager = KlineDataManager()
    return _global_kline_manager

