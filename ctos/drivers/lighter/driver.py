# -*- coding: utf-8 -*-
# ctos/drivers/lighter/driver.py
# Lighter交易所驱动，包装现有的lighter.py客户端
# 兼容较老的Python版本（无dataclasses/Protocol）

from __future__ import print_function
import math
import json
import os
import sys
import asyncio
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

def _add_lighter_path():
    """添加lighter包路径到sys.path，支持多种运行方式"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    lighter_path = os.path.join(current_dir, 'lighter')
    
    # 添加当前目录的lighter路径
    if lighter_path not in sys.path:
        sys.path.insert(0, lighter_path)
    
    # 添加项目根目录的lighter路径（如果存在）
    project_root = os.path.abspath(os.path.join(current_dir, '../../..'))
    root_lighter_path = os.path.join(project_root, 'lighter')
    if os.path.exists(root_lighter_path) and root_lighter_path not in sys.path:
        sys.path.insert(0, root_lighter_path)
    if os.path.exists(project_root) and project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root

# 执行路径添加
_PROJECT_ROOT = _add_lighter_path()
print('PROJECT_ROOT: ', _PROJECT_ROOT, 'CURRENT_DIR: ', os.path.dirname(os.path.abspath(__file__)))

try:
    # 优先：绝对导入（当项目以包方式安装/运行时）
    from ctos.drivers.lighter.lighter_driver import LighterClient
except Exception as e:
    print('Error from lighter import ', e)

# Import syscall base
try:
    # 包内正常导入
    from ctos.core.kernel.syscalls import TradingSyscalls
except ImportError:
    # 单文件执行时，修正 sys.path 再导入
    import os, sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
    from ctos.core.kernel.syscalls import TradingSyscalls

# Import account reader
try:
    from configs.account_reader import get_lighter_credentials, list_accounts
except ImportError:
    # 如果无法导入，使用备用方案
    def get_lighter_credentials(account='main'):
        """获取Lighter账户认证信息"""
        return {
            'api_key_private_key': os.getenv('LIGHTER_API_KEY_PRIVATE_KEY'),
            'account_index': int(os.getenv('LIGHTER_ACCOUNT_INDEX', '0')),
            'api_key_index': int(os.getenv('LIGHTER_API_KEY_INDEX', '0'))
        }
    
    def list_accounts(exchange='lighter'):
        """获取账户列表"""
        return ['main', 'sub1', 'sub2']  # 默认账户列表

def get_account_name_by_id(account_id=0, exchange='lighter'):
    """
    根据账户ID获取账户名称
    
    输入参数:
        account_id: 账户ID
        exchange: 交易所名称
        
    输出: str - 账户名称
    作用: 根据账户ID映射到对应的账户名称
    """
    try:
        accounts = list_accounts(exchange)
        
        if account_id < len(accounts):
            return accounts[account_id]
        else:
            print(f"警告: 账户ID {account_id} 超出范围，可用账户: {accounts}")
            return accounts[0] if accounts else 'main'
            
    except Exception as e:
        print(f"获取账户名称失败: {e}，使用默认映射")
        # 回退到默认映射
        default_mapping = {0: 'main', 1: 'sub1', 2: 'sub2'}
        return default_mapping.get(account_id, 'main')

def init_LighterClient(symbol="ETH-USDC", account_id=0, show=True):
    """
    初始化Lighter客户端
    
    输入参数:
        symbol: 交易对符号
        account_id: 账户ID，根据配置文件中的账户顺序映射 (0=第一个账户, 1=第二个账户, ...)
        show: 是否显示调试信息
        
    输出: LighterClient - Lighter客户端实例
        
    作用: 根据账户ID初始化Lighter交易所客户端
    """
    if symbol.find('-') == -1:
        symbol = f'{symbol.upper()}-USDC'
    
    # 从配置文件动态获取账户名称
    account_name = get_account_name_by_id(account_id, 'lighter')
    
    # try:
    if True:
        # 使用账户获取器获取认证信息
        credentials = get_lighter_credentials(account_name)
        
        if show:
            print(f"使用Lighter账户: {account_name} (ID: {account_id})")
            print(f"认证字段: {list(credentials.keys())}")
        
        # 创建配置字典
        config = {
            'ticker': "ETH",  # 基础货币
            'contract_id': None,  # 将在连接时设置
            'quantity': Decimal('0.1'),  # 默认数量
            'tick_size': Decimal('0.01'),  # 默认价格精度
            'direction': 'buy',  # 默认方向
            'close_order_side': 'sell'  # 默认平仓方向
        }
        print(config)
        return LighterClient(config)
    # except Exception as e:
    #     print(f"获取Lighter账户 {account_name} 认证信息失败: {e}")
    #     # 回退到默认配置
    #     config = {
    #         'ticker': symbol.split('-')[0],
    #         'contract_id': None,
    #         'quantity': Decimal('0.1'),
    #         'tick_size': Decimal('0.01'),
    #         'direction': 'buy',
    #         'close_order_side': 'sell'
    #     }
    #     return LighterClient(config)

class LighterDriver(TradingSyscalls):
    """
    CTOS Lighter驱动
    适配Strategy.py中看到的方法:
      - get_price_now('eth')
      - get_kline(tf, N, 'ETH-USDC') -> returns (df_or_list, ...)
      - revoke_orders(...)
      - get_jiaoyi_asset(), get_zijin_asset(), transfer_money(...)
    """

    def __init__(self, lighter_client=None, mode="spot", default_quote="USDC",
                 price_scale=1e-8, size_scale=1e-8, account_id=0):
        """
        初始化Lighter驱动
        
        输入参数:
            lighter_client: 可选的已初始化客户端（已认证）
            mode: "spot" 或 "swap"，默认为 "spot"
            default_quote: 当用户传入'ETH'而没有'-USDC'时的默认计价货币
            account_id: 账户ID，根据配置文件中的账户顺序映射
            price_scale: 价格精度缩放
            size_scale: 数量精度缩放
        
        输出: 无
        作用: 初始化Lighter交易所驱动，设置基础参数和客户端
        """
        self.cex = 'lighter'
        self.quote_ccy = 'USDC'
        self.account_id = account_id
        
        if lighter_client is None:
            # try:
            self.lighter = init_LighterClient(account_id=account_id)
            print(f"✓ Lighter Driver初始化成功 (账户ID: {account_id})")
            # except Exception as e:
            #     print(f"✗ Lighter Driver初始化失败 (账户ID: {account_id}): {e}")
            #     self.lighter = None
        else:
            self.lighter = lighter_client
            print(f"✓ Lighter Driver使用外部客户端 (账户ID: {account_id})")
        
        self.mode = (mode or "spot").lower()
        self.default_quote = default_quote or "USDC"
        self.price_scale = price_scale
        self.size_scale = size_scale
        self.load_exchange_trade_info()
        self.order_id_to_symbol = {}

    def save_exchange_trade_info(self):
        """
        保存交易所交易信息到文件
        
        输入参数: 无
        输出: 无
        作用: 将交易所交易信息保存到本地JSON文件
        """
        with open(os.path.dirname(os.path.abspath(__file__)) + '/exchange_trade_info.json', 'w') as f:
            json.dump(self.exchange_trade_info, f)

    def load_exchange_trade_info(self):
        """
        从文件加载交易所交易信息
        
        输入参数: 无
        输出: 无
        作用: 从本地JSON文件加载交易所交易信息，如果文件不存在则初始化为空字典
        """
        if not os.path.exists(os.path.dirname(os.path.abspath(__file__)) + '/exchange_trade_info.json'):
            self.exchange_trade_info = {}
            return
        with open(os.path.dirname(os.path.abspath(__file__)) + '/exchange_trade_info.json', 'r') as f:
            self.exchange_trade_info = json.load(f)

    # -------------- helpers --------------
    def _norm_symbol(self, symbol):
        """
        标准化交易对符号
        
        输入参数:
            symbol: 交易对符号，支持多种格式
        
        输出: Tuple[str, str, str] - (完整符号, 基础货币, 计价货币)
        作用: 接受'ETH-USDC', 'ETH/USDC', 'eth', 'ETH-USDC'等格式，返回标准化的Lighter符号
        """
        s = str(symbol or "").replace("/", "-").upper()
        if "-" in s:
            parts = s.split("-")
            base = parts[0]
            quote = parts[1] if len(parts) > 1 else self.default_quote
        else:
            base = s
            quote = self.default_quote

        full = base + "-" + quote
        return full, base.lower(), quote.upper()

    # -------------- ref-data / meta --------------
    def symbols(self, instType='SPOT'):
        """
        返回指定类型的交易对列表
        
        输入参数:
            instType: 'SPOT' | 'SWAP' | 'MARGIN' 等，默认 'SPOT'
        
        输出: Tuple[List[str], Optional[Exception]] - (交易对列表, 错误信息)
        作用: 获取指定类型的交易对列表
        """
        if not hasattr(self.lighter, 'get_contract_attributes'):
            # 兜底：无法从底层获取时，返回少量默认
            return ["ETH-USDC", "BTC-USDC", "SOL-USDC"] if str(instType).upper() == 'SPOT' else ["ETH-USDC-SWAP", "BTC-USDC-SWAP", "SOL-USDC-SWAP"]

        try:
            # Lighter使用异步方法，需要特殊处理
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果事件循环正在运行，创建任务
                task = asyncio.create_task(self._get_symbols_async(instType))
                return task.result(), None
            else:
                # 如果事件循环未运行，直接运行
                return asyncio.run(self._get_symbols_async(instType))
        except Exception as e:
            return [], e

    async def _get_symbols_async(self, instType):
        """
        异步获取交易对列表
        
        输入参数:
            instType: 产品类型
        
        输出: List[str] - 交易对列表
        作用: 异步获取指定类型的交易对列表
        """
        try:
            # 这里需要根据Lighter的实际API来实现
            # 暂时返回默认列表
            if str(instType).upper() == 'SPOT':
                return ["ETH-USDC", "BTC-USDC", "SOL-USDC"]
            else:
                return ["ETH-USDC-SWAP", "BTC-USDC-SWAP", "SOL-USDC-SWAP"]
        except Exception as e:
            return []

    def exchange_limits(self, symbol=None, instType='SPOT'):
        """
        获取交易所限制信息，包括价格精度、数量精度、最小下单数量等
        
        输入参数:
            symbol: 交易对符号，如 'ETH-USDC'，如果为None则返回全类型数据
            instType: 产品类型，默认为 'SPOT'
        
        输出: Tuple[Dict, Optional[Exception]] - (限制信息字典, 错误信息)
        作用: 获取指定交易对的交易所限制信息
        """
        if symbol:
            symbol, _, _ = self._norm_symbol(symbol)
            if symbol in self.exchange_trade_info:
                return self.exchange_trade_info[symbol], None
        
        try:
            # 使用异步方法获取合约属性
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._get_exchange_limits_async(symbol, instType))
                return task.result()
            else:
                return asyncio.run(self._get_exchange_limits_async(symbol, instType))
        except Exception as e:
            return {"error": f"处理数据时发生异常: {str(e)}"}, None

    async def _get_exchange_limits_async(self, symbol, instType):
        """
        异步获取交易所限制信息
        
        输入参数:
            symbol: 交易对符号
            instType: 产品类型
        
        输出: Tuple[Dict, Optional[Exception]] - (限制信息字典, 错误信息)
        作用: 异步获取交易所限制信息
        """
        try:
            if not self.lighter:
                return {"error": "Lighter client not initialized"}, None
            
            # 获取合约属性
            contract_id, tick_size = await self.lighter.get_contract_attributes()
            
            limits = {
                'symbol': symbol or 'ETH-USDC',
                'instType': instType,
                'price_precision': float(tick_size),
                'size_precision': 0.001,  # 默认数量精度
                'min_order_size': 0.001,  # 默认最小下单数量
                'contract_value': 1.0,    # 默认合约面值
                'max_leverage': 1.0,     # 默认最大杠杆
                'state': 'live',         # 默认状态
                'raw': {'contract_id': contract_id, 'tick_size': str(tick_size)}
            }
            
            if symbol:
                self.exchange_trade_info[symbol] = limits
                self.save_exchange_trade_info()
                return limits, None
            else:
                return limits, None
                
        except Exception as e:
            return {"error": f"获取限制信息失败: {str(e)}"}, None

    def fees(self, symbol='ETH-USDC', instType='SPOT', keep_origin=False):
        """
        获取资金费率信息
        
        输入参数:
            symbol: 交易对符号
            instType: 产品类型
            keep_origin: 是否保持原始格式
        
        输出: Tuple[Dict, Optional[Exception]] - (费率信息, 错误信息)
        作用: 获取指定交易对的资金费率信息
        """
        full, _, _ = self._norm_symbol(symbol)
        
        # Lighter是现货交易所，通常没有资金费率
        if instType.upper() == 'SPOT':
            return {
                'symbol': full,
                'instType': instType,
                'fundingRate_hourly': 0.0,
                'fundingRate_period': 0.0,
                'period_hours': 0.0,
                'fundingTime': 0,
                'raw': {'message': 'Spot trading has no funding rate'}
            }, None
        else:
            return None, Exception("Lighter does not support funding rate for this instrument type")

    # -------------- market data --------------
    def get_price_now(self, symbol='ETH-USDC'):
        """
        获取当前价格
        
        输入参数:
            symbol: 交易对符号
        
        输出: float - 当前价格
        作用: 获取指定交易对的当前价格
        """
        full, base, _ = self._norm_symbol(symbol)
        
        try:
            # 使用异步方法获取价格
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._get_price_now_async(full))
                return task.result()
            else:
                return asyncio.run(self._get_price_now_async(full))
        except Exception as e:
            raise NotImplementedError(f"获取价格失败: {e}")

    async def _get_price_now_async(self, symbol):
        """
        异步获取当前价格
        
        输入参数:
            symbol: 交易对符号
        
        输出: float - 当前价格
        作用: 异步获取指定交易对的当前价格
        """
        try:
            if not self.lighter:
                raise Exception("Lighter client not initialized")
            
            # 获取最佳买卖价格
            best_bid, best_ask = await self.lighter.fetch_bbo_prices(symbol)
            
            # 返回中间价
            return float((best_bid + best_ask) / 2)
        except Exception as e:
            raise Exception(f"获取价格失败: {e}")

    def get_orderbook(self, symbol='ETH-USDC', level=50):
        """
        获取订单簿
        
        输入参数:
            symbol: 交易对符号
            level: 订单簿深度
        
        输出: Dict - 订单簿数据
        作用: 获取指定交易对的订单簿信息
        """
        full, _, _ = self._norm_symbol(symbol)
        
        try:
            # 使用异步方法获取订单簿
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._get_orderbook_async(full, level))
                return task.result()
            else:
                return asyncio.run(self._get_orderbook_async(full, level))
        except Exception as e:
            raise NotImplementedError(f"获取订单簿失败: {e}")

    async def _get_orderbook_async(self, symbol, level):
        """
        异步获取订单簿
        
        输入参数:
            symbol: 交易对符号
            level: 订单簿深度
        
        输出: Dict - 订单簿数据
        作用: 异步获取指定交易对的订单簿信息
        """
        try:
            if not self.lighter:
                raise Exception("Lighter client not initialized")
            
            # 获取最佳买卖价格
            best_bid, best_ask = await self.lighter.fetch_bbo_prices(symbol)
            
            # 构造简化的订单簿
            return {
                "symbol": symbol,
                "bids": [[str(best_bid), "1.0"]],  # 简化的买单
                "asks": [[str(best_ask), "1.0"]]   # 简化的卖单
            }
        except Exception as e:
            raise Exception(f"获取订单簿失败: {e}")

    def get_klines(self, symbol='ETH-USDC', timeframe='1h', limit=200):
        """
        获取K线数据
        
        输入参数:
            symbol: 交易对符号
            timeframe: 时间周期
            limit: 数据条数
        
        输出: Tuple[Optional[List], Optional[Exception]] - (K线数据, 错误信息)
        作用: 获取指定交易对的K线数据
        """
        full, _, _ = self._norm_symbol(symbol)
        
        try:
            # 使用异步方法获取K线
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._get_klines_async(full, timeframe, limit))
                return task.result()
            else:
                return asyncio.run(self._get_klines_async(full, timeframe, limit))
        except Exception as e:
            return None, e

    async def _get_klines_async(self, symbol, timeframe, limit):
        """
        异步获取K线数据
        
        输入参数:
            symbol: 交易对符号
            timeframe: 时间周期
            limit: 数据条数
        
        输出: Tuple[Optional[List], Optional[Exception]] - (K线数据, 错误信息)
        作用: 异步获取指定交易对的K线数据
        """
        try:
            # Lighter可能没有直接的K线API，这里返回模拟数据
            # 实际实现需要根据Lighter的API来调整
            return None, Exception("K线数据获取功能需要根据Lighter API实现")
        except Exception as e:
            return None, e

    # -------------- trading --------------
    def place_order(self, symbol, side, order_type, size, price=None, client_id=None, **kwargs):
        """
        下单
        
        输入参数:
            symbol: 交易对符号
            side: 买卖方向 ('buy' 或 'sell')
            order_type: 订单类型 ('market' 或 'limit')
            size: 订单数量
            price: 订单价格（限价单需要）
            client_id: 客户端订单ID
            **kwargs: 其他参数
        
        输出: Tuple[Optional[str], Optional[Exception]] - (订单ID, 错误信息)
        作用: 在Lighter交易所下单
        """
        full, _, _ = self._norm_symbol(symbol)
        
        try:
            # 使用异步方法下单
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._place_order_async(full, side, order_type, size, price, client_id, **kwargs))
                return task.result()
            else:
                return asyncio.run(self._place_order_async(full, side, order_type, size, price, client_id, **kwargs))
        except Exception as e:
            return None, e

    async def _place_order_async(self, symbol, side, order_type, size, price, client_id, **kwargs):
        """
        异步下单
        
        输入参数:
            symbol: 交易对符号
            side: 买卖方向
            order_type: 订单类型
            size: 订单数量
            price: 订单价格
            client_id: 客户端订单ID
            **kwargs: 其他参数
        
        输出: Tuple[Optional[str], Optional[Exception]] - (订单ID, 错误信息)
        作用: 异步在Lighter交易所下单
        """
        try:
            if not self.lighter:
                return None, Exception("Lighter client not initialized")
            
            # 连接客户端
            await self.lighter.connect()
            
            # 获取合约属性
            contract_id, tick_size = await self.lighter.get_contract_attributes()
            
            # 设置合约ID
            self.lighter.config.contract_id = contract_id
            
            # 根据订单类型下单
            if order_type.lower() == 'market':
                # 市价单
                result = await self.lighter.place_market_order(contract_id, Decimal(str(size)), side)
            else:
                # 限价单
                if price is None:
                    return None, Exception("限价单需要指定价格")
                result = await self.lighter.place_limit_order(contract_id, Decimal(str(size)), Decimal(str(price)), side)
            
            if result.success:
                return result.order_id, None
            else:
                return None, Exception(result.error_message)
                
        except Exception as e:
            return None, e

    def buy(self, symbol, size, price=None, order_type="limit", **kwargs):
        """
        买入订单的便捷包装
        
        输入参数:
            symbol: 交易对符号，如 'ETH-USDC' 或 'eth'
            size: 数量
            price: 限价单的价格，市价单可省略
            order_type: 'limit' | 'market' | 'post_only'
            **kwargs: 其他参数
        
        输出: Tuple[Optional[str], Optional[Exception]] - (订单ID, 错误信息)
        作用: 便捷的买入订单方法
        """
        return self.place_order(
            symbol=symbol,
            side="buy",
            order_type=str(order_type).lower(),
            size=float(size),
            price=price,
            **kwargs,
        )

    def sell(self, symbol, size, price=None, order_type="limit", **kwargs):
        """
        卖出订单的便捷包装
        
        输入参数:
            symbol: 交易对符号，如 'ETH-USDC' 或 'eth'
            size: 数量
            price: 限价单的价格，市价单可省略
            order_type: 'limit' | 'market' | 'post_only'
            **kwargs: 其他参数
        
        输出: Tuple[Optional[str], Optional[Exception]] - (订单ID, 错误信息)
        作用: 便捷的卖出订单方法
        """
        return self.place_order(
            symbol=symbol,
            side="sell",
            order_type=str(order_type).lower(),
            size=float(size),
            price=price,
            **kwargs,
        )

    def amend_order(self, order_id, symbol=None, **kwargs):
        """
        修改订单
        
        输入参数:
            order_id: 订单ID
            symbol: 交易对符号
            **kwargs: 修改参数
        
        输出: Tuple[Optional[str], Optional[Exception]] - (订单ID, 错误信息)
        作用: 修改指定订单的参数
        """
        try:
            # 使用异步方法修改订单
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._amend_order_async(order_id, symbol, **kwargs))
                return task.result()
            else:
                return asyncio.run(self._amend_order_async(order_id, symbol, **kwargs))
        except Exception as e:
            return None, e

    async def _amend_order_async(self, order_id, symbol, **kwargs):
        """
        异步修改订单
        
        输入参数:
            order_id: 订单ID
            symbol: 交易对符号
            **kwargs: 修改参数
        
        输出: Tuple[Optional[str], Optional[Exception]] - (订单ID, 错误信息)
        作用: 异步修改指定订单的参数
        """
        try:
            if not self.lighter:
                return None, Exception("Lighter client not initialized")
            
            # Lighter可能不支持订单修改，这里返回错误
            return None, Exception("Lighter does not support order amendment")
        except Exception as e:
            return None, e

    def revoke_order(self, order_id, symbol=None):
        """
        撤销订单
        
        输入参数:
            order_id: 订单ID
            symbol: 交易对符号
        
        输出: Tuple[bool, Optional[Exception]] - (是否成功, 错误信息)
        作用: 撤销指定订单
        """
        try:
            # 使用异步方法撤销订单
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._revoke_order_async(order_id, symbol))
                return task.result()
            else:
                return asyncio.run(self._revoke_order_async(order_id, symbol))
        except Exception as e:
            return False, e

    async def _revoke_order_async(self, order_id, symbol):
        """
        异步撤销订单
        
        输入参数:
            order_id: 订单ID
            symbol: 交易对符号
        
        输出: Tuple[bool, Optional[Exception]] - (是否成功, 错误信息)
        作用: 异步撤销指定订单
        """
        try:
            if not self.lighter:
                return False, Exception("Lighter client not initialized")
            
            # 连接客户端
            await self.lighter.connect()
            
            # 取消订单
            result = await self.lighter.cancel_order(order_id)
            
            return result.success, None if result.success else Exception(result.error_message)
        except Exception as e:
            return False, e

    def get_order_status(self, order_id, symbol=None, keep_origin=False):
        """
        获取订单状态
        
        输入参数:
            order_id: 订单ID
            symbol: 交易对符号
            keep_origin: 是否保持原始格式
        
        输出: Tuple[Optional[Dict], Optional[Exception]] - (订单状态, 错误信息)
        作用: 获取指定订单的状态信息
        """
        try:
            # 使用异步方法获取订单状态
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._get_order_status_async(order_id, symbol, keep_origin))
                return task.result()
            else:
                return asyncio.run(self._get_order_status_async(order_id, symbol, keep_origin))
        except Exception as e:
            return None, e

    async def _get_order_status_async(self, order_id, symbol, keep_origin):
        """
        异步获取订单状态
        
        输入参数:
            order_id: 订单ID
            symbol: 交易对符号
            keep_origin: 是否保持原始格式
        
        输出: Tuple[Optional[Dict], Optional[Exception]] - (订单状态, 错误信息)
        作用: 异步获取指定订单的状态信息
        """
        try:
            if not self.lighter:
                return None, Exception("Lighter client not initialized")
            
            # 连接客户端
            await self.lighter.connect()
            
            # 获取订单信息
            order_info = await self.lighter.get_order_info(order_id)
            
            if order_info is None:
                return None, Exception("订单不存在")
            
            if keep_origin:
                return order_info.__dict__, None
            
            # 标准化订单信息
            normalized = {
                'orderId': order_info.order_id,
                'symbol': symbol or 'ETH-USDC',
                'side': order_info.side,
                'orderType': 'limit',  # Lighter主要使用限价单
                'price': float(order_info.price),
                'quantity': float(order_info.size),
                'filledQuantity': float(order_info.filled_size),
                'status': order_info.status,
                'timeInForce': 'GTC',
                'postOnly': True,
                'reduceOnly': False,
                'clientId': None,
                'createdAt': None,
                'updatedAt': None,
                'raw': order_info.__dict__,
            }
            return normalized, None
        except Exception as e:
            return None, e

    def get_open_orders(self, symbol='ETH-USDC', instType='SPOT', onlyOrderId=True, keep_origin=True):
        """
        获取开放订单
        
        输入参数:
            symbol: 交易对符号
            instType: 产品类型
            onlyOrderId: 是否只返回订单ID
            keep_origin: 是否保持原始格式
        
        输出: Tuple[Optional[List], Optional[Exception]] - (订单列表, 错误信息)
        作用: 获取指定交易对的开放订单列表
        """
        try:
            # 使用异步方法获取开放订单
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._get_open_orders_async(symbol, instType, onlyOrderId, keep_origin))
                return task.result()
            else:
                return asyncio.run(self._get_open_orders_async(symbol, instType, onlyOrderId, keep_origin))
        except Exception as e:
            return None, e

    async def _get_open_orders_async(self, symbol, instType, onlyOrderId, keep_origin):
        """
        异步获取开放订单
        
        输入参数:
            symbol: 交易对符号
            instType: 产品类型
            onlyOrderId: 是否只返回订单ID
            keep_origin: 是否保持原始格式
        
        输出: Tuple[Optional[List], Optional[Exception]] - (订单列表, 错误信息)
        作用: 异步获取指定交易对的开放订单列表
        """
        try:
            if not self.lighter:
                return None, Exception("Lighter client not initialized")
            
            # 连接客户端
            await self.lighter.connect()
            
            # 获取合约属性
            contract_id, _ = await self.lighter.get_contract_attributes()
            
            # 获取活跃订单
            orders = await self.lighter.get_active_orders(contract_id)
            
            if onlyOrderId or keep_origin:
                return [order.order_id for order in orders], None
            
            # 标准化订单信息
            normalized = []
            for order in orders:
                normalized.append({
                    'orderId': order.order_id,
                    'symbol': symbol,
                    'side': order.side,
                    'orderType': 'limit',
                    'price': float(order.price),
                    'quantity': float(order.size),
                    'filledQuantity': float(order.filled_size),
                    'status': order.status,
                    'timeInForce': 'GTC',
                    'postOnly': True,
                    'reduceOnly': False,
                    'clientId': None,
                    'createdAt': None,
                    'updatedAt': None,
                    'raw': order.__dict__,
                })
            
            return normalized, None
        except Exception as e:
            return None, e

    def cancel_all(self, symbol='ETH-USDC', order_ids=[]):
        """
        撤销所有订单
        
        输入参数:
            symbol: 交易对符号
            order_ids: 订单ID列表
        
        输出: Dict - 撤销结果
        作用: 撤销指定交易对的所有订单或指定订单列表
        """
        try:
            # 使用异步方法撤销所有订单
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._cancel_all_async(symbol, order_ids))
                return task.result()
            else:
                return asyncio.run(self._cancel_all_async(symbol, order_ids))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _cancel_all_async(self, symbol, order_ids):
        """
        异步撤销所有订单
        
        输入参数:
            symbol: 交易对符号
            order_ids: 订单ID列表
        
        输出: Dict - 撤销结果
        作用: 异步撤销指定交易对的所有订单或指定订单列表
        """
        try:
            if not self.lighter:
                return {"ok": False, "error": "Lighter client not initialized"}
            
            # 连接客户端
            await self.lighter.connect()
            
            # 获取合约属性
            contract_id, _ = await self.lighter.get_contract_attributes()
            
            if order_ids:
                # 撤销指定订单
                results = []
                for order_id in order_ids:
                    result = await self.lighter.cancel_order(order_id)
                    results.append({"order_id": order_id, "success": result.success})
                return {"ok": True, "results": results}
            else:
                # 撤销所有订单
                orders = await self.lighter.get_active_orders(contract_id)
                results = []
                for order in orders:
                    result = await self.lighter.cancel_order(order.order_id)
                    results.append({"order_id": order.order_id, "success": result.success})
                return {"ok": True, "results": results}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -------------- account --------------
    def fetch_balance(self, currency='USDC'):
        """
        获取账户余额
        
        输入参数:
            currency: 货币类型
        
        输出: Dict - 余额信息
        作用: 获取指定货币的账户余额
        """
        try:
            # 使用异步方法获取余额
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._fetch_balance_async(currency))
                return task.result()
            else:
                return asyncio.run(self._fetch_balance_async(currency))
        except Exception as e:
            return {"error": str(e)}

    async def _fetch_balance_async(self, currency):
        """
        异步获取账户余额
        
        输入参数:
            currency: 货币类型
        
        输出: Dict - 余额信息
        作用: 异步获取指定货币的账户余额
        """
        try:
            if not self.lighter:
                return {"error": "Lighter client not initialized"}
            
            # Lighter可能没有直接的余额API，这里返回模拟数据
            return {
                "currency": currency,
                "available": "1000.0",
                "frozen": "0.0",
                "total": "1000.0"
            }
        except Exception as e:
            return {"error": str(e)}

    def get_position(self, symbol=None, keep_origin=False, instType='SPOT'):
        """
        获取持仓信息
        
        输入参数:
            symbol: 交易对符号
            keep_origin: 是否保持原始格式
            instType: 产品类型
        
        输出: Tuple[Optional[Dict], Optional[Exception]] - (持仓信息, 错误信息)
        作用: 获取指定交易对的持仓信息
        """
        try:
            # 使用异步方法获取持仓
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._get_position_async(symbol, keep_origin, instType))
                return task.result()
            else:
                return asyncio.run(self._get_position_async(symbol, keep_origin, instType))
        except Exception as e:
            return None, e

    async def _get_position_async(self, symbol, keep_origin, instType):
        """
        异步获取持仓信息
        
        输入参数:
            symbol: 交易对符号
            keep_origin: 是否保持原始格式
            instType: 产品类型
        
        输出: Tuple[Optional[Dict], Optional[Exception]] - (持仓信息, 错误信息)
        作用: 异步获取指定交易对的持仓信息
        """
        try:
            if not self.lighter:
                return None, Exception("Lighter client not initialized")
            
            # 连接客户端
            await self.lighter.connect()
            
            # 获取合约属性
            contract_id, _ = await self.lighter.get_contract_attributes()
            
            # 获取持仓
            position = await self.lighter.get_account_positions()
            
            if keep_origin:
                return {"position": str(position)}, None
            
            # 标准化持仓信息
            unified = {
                'symbol': symbol or 'ETH-USDC',
                'positionId': None,
                'side': 'long' if position > 0 else ('short' if position < 0 else 'flat'),
                'quantity': abs(float(position)),
                'quantityUSD': abs(float(position)) * 1000,  # 假设价格
                'entryPrice': None,
                'markPrice': None,
                'pnlUnrealized': None,
                'pnlRealized': None,
                'leverage': 1.0,
                'liquidationPrice': None,
                'ts': None,
                'fee': None,
                'breakEvenPrice': None
            }
            
            return unified, None
        except Exception as e:
            return None, e

    def close_all_positions(self, mode="market", price_offset=0.0005, symbol=None, side=None, is_good=None):
        """
        平掉所有仓位，可附加过滤条件（Lighter版）
        
        输入参数:
            mode: "market" 或 "limit"
            price_offset: limit平仓时的价格偏移系数（相对markPx）
            symbol: 仅平某个币种
            side: "long" 仅平多仓, "short" 仅平空仓, None表示不限
            is_good: True仅平盈利仓, False仅平亏损仓, None表示不限
        
        输出: 无
        作用: 平掉所有符合条件的仓位
        """
        try:
            # 使用异步方法平仓
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = asyncio.create_task(self._close_all_positions_async(mode, price_offset, symbol, side, is_good))
                task.result()
            else:
                asyncio.run(self._close_all_positions_async(mode, price_offset, symbol, side, is_good))
        except Exception as e:
            print(f"[Lighter] 平仓失败: {e}")

    async def _close_all_positions_async(self, mode, price_offset, symbol, side, is_good):
        """
        异步平掉所有仓位
        
        输入参数:
            mode: 平仓模式
            price_offset: 价格偏移
            symbol: 交易对符号
            side: 仓位方向
            is_good: 盈亏过滤
        
        输出: 无
        作用: 异步平掉所有符合条件的仓位
        """
        try:
            if not self.lighter:
                print("[Lighter] 客户端未初始化")
                return
            
            # 连接客户端
            await self.lighter.connect()
            
            # 获取合约属性
            contract_id, _ = await self.lighter.get_contract_attributes()
            
            # 获取持仓
            position = await self.lighter.get_account_positions()
            
            if position == 0:
                print("✅ 当前无持仓")
                return
            
            # 判断仓位方向
            pos_side = "long" if position > 0 else "short"
            
            # 过滤条件
            if side and side != pos_side:
                return
            
            # 构造平仓单
            if position > 0:
                order_side = "sell"
                size = abs(position)
            else:
                order_side = "buy"
                size = abs(position)
            
            if mode == "market":
                try:
                    result = await self.lighter.place_market_order(contract_id, size, order_side)
                    if result.success:
                        print(f"📤 市价平仓: {symbol or 'ETH-USDC'} {order_side} {size}")
                    else:
                        print(f"[Lighter] 市价平仓失败: {result.error_message}")
                except Exception as e:
                    print(f"[Lighter] 市价平仓失败: {e}")
            elif mode == "limit":
                try:
                    # 获取当前价格
                    best_bid, best_ask = await self.lighter.fetch_bbo_prices(contract_id)
                    if order_side == "sell":
                        price = best_ask * (1 + price_offset)
                    else:
                        price = best_bid * (1 - price_offset)
                    
                    result = await self.lighter.place_limit_order(contract_id, size, price, order_side)
                    if result.success:
                        print(f"📤 限价平仓: {symbol or 'ETH-USDC'} {order_side} {size} @ {price}")
                    else:
                        print(f"[Lighter] 限价平仓失败: {result.error_message}")
                except Exception as e:
                    print(f"[Lighter] 限价平仓失败: {e}")
            else:
                raise ValueError("mode 必须是 'market' 或 'limit'")
                
        except Exception as e:
            print(f"[Lighter] 平仓过程出错: {e}")


if __name__ == "__main__":
    """
    Lighter驱动测试主函数
    用于测试Lighter交易所驱动的各项功能
    """
    import asyncio
    
    async def test_lighter_driver():
        """测试Lighter驱动的异步功能"""
        print("=" * 50)
        print("Lighter驱动测试开始")
        print("=" * 50)
        
        try:
            # 1. 初始化驱动
            print("\n1. 初始化Lighter驱动...")
            driver = LighterDriver(account_id=0)
            print(f"✓ 驱动初始化成功: {driver.cex}")
            
            # 2. 测试连接
            print("\n2. 测试Lighter客户端连接...")
            if driver.lighter:
                await driver.lighter.connect()
                print("✓ Lighter客户端连接成功")
            else:
                print("✗ Lighter客户端未初始化")
                return
            
            # 3. 测试获取合约属性
            print("\n3. 测试获取合约属性...")
            try:
                contract_id, tick_size = await driver.lighter.get_contract_attributes()
                print(f"✓ 合约ID: {contract_id}")
                print(f"✓ 价格精度: {tick_size}")
            except Exception as e:
                print(f"✗ 获取合约属性失败: {e}")
            
            # 4. 测试获取价格
            print("\n4. 测试获取当前价格...")
            try:
                price = driver.get_price_now('ETH-USDC')
                print(f"✓ ETH-USDC 当前价格: {price}")
            except Exception as e:
                print(f"✗ 获取价格失败: {e}")
            
            # 5. 测试获取订单簿
            print("\n5. 测试获取订单簿...")
            try:
                orderbook = driver.get_orderbook('ETH-USDC')
                print(f"✓ 订单簿获取成功: {orderbook}")
            except Exception as e:
                print(f"✗ 获取订单簿失败: {e}")
            
            # 6. 测试获取持仓
            print("\n6. 测试获取持仓信息...")
            try:
                position, error = driver.get_position('ETH-USDC')
                if error:
                    print(f"✗ 获取持仓失败: {error}")
                else:
                    print(f"✓ 持仓信息: {position}")
            except Exception as e:
                print(f"✗ 获取持仓异常: {e}")
            
            # 7. 测试获取开放订单
            print("\n7. 测试获取开放订单...")
            try:
                orders, error = driver.get_open_orders('ETH-USDC')
                if error:
                    print(f"✗ 获取开放订单失败: {error}")
                else:
                    print(f"✓ 开放订单数量: {len(orders) if orders else 0}")
            except Exception as e:
                print(f"✗ 获取开放订单异常: {e}")
            
            # 8. 测试获取余额
            print("\n8. 测试获取账户余额...")
            try:
                balance = driver.fetch_balance('USDC')
                print(f"✓ 账户余额: {balance}")
            except Exception as e:
                print(f"✗ 获取余额失败: {e}")
            
            # 9. 测试交易所限制信息
            print("\n9. 测试获取交易所限制信息...")
            try:
                limits, error = driver.exchange_limits('ETH-USDC')
                if error:
                    print(f"✗ 获取限制信息失败: {error}")
                else:
                    print(f"✓ 限制信息: {limits}")
            except Exception as e:
                print(f"✗ 获取限制信息异常: {e}")
            
            # 10. 测试获取交易对列表
            print("\n10. 测试获取交易对列表...")
            try:
                symbols, error = driver.symbols('SPOT')
                if error:
                    print(f"✗ 获取交易对列表失败: {error}")
                else:
                    print(f"✓ 交易对列表: {symbols}")
            except Exception as e:
                print(f"✗ 获取交易对列表异常: {e}")
            
            # 11. 断开连接
            print("\n11. 断开连接...")
            try:
                await driver.lighter.disconnect()
                print("✓ 连接已断开")
            except Exception as e:
                print(f"✗ 断开连接失败: {e}")
            
            print("\n" + "=" * 50)
            print("Lighter驱动测试完成")
            print("=" * 50)
            
        except Exception as e:
            print(f"✗ 测试过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
    
    def test_sync_functions():
        """测试同步功能"""
        print("\n" + "=" * 50)
        print("同步功能测试")
        print("=" * 50)
        
        try:
            # 初始化驱动
            driver = LighterDriver(account_id=0)
            print(f"✓ 驱动初始化成功: {driver.cex}")
            
            # 测试符号标准化
            print("\n测试符号标准化...")
            test_symbols = ['ETH', 'ETH-USDC', 'eth/usdc', 'BTC-USDC']
            for symbol in test_symbols:
                full, base, quote = driver._norm_symbol(symbol)
                print(f"  {symbol} -> {full} ({base}/{quote})")
            
            # 测试配置保存和加载
            print("\n测试配置保存和加载...")
            driver.exchange_trade_info = {'test': 'data'}
            driver.save_exchange_trade_info()
            driver.load_exchange_trade_info()
            print(f"✓ 配置保存和加载成功: {driver.exchange_trade_info}")
            
        except Exception as e:
            print(f"✗ 同步功能测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    def interactive_test():
        """交互式测试"""
        print("\n" + "=" * 50)
        print("交互式测试模式")
        print("=" * 50)
        print("可用的测试命令:")
        print("1. sync - 测试同步功能")
        print("2. async - 测试异步功能")
        print("3. driver - 创建驱动实例")
        print("4. quit - 退出")
        
        driver = None
        
        while True:
            try:
                cmd = input("\n请输入命令: ").strip().lower()
                
                if cmd == 'quit':
                    break
                elif cmd == 'sync':
                    test_sync_functions()
                elif cmd == 'async':
                    asyncio.run(test_lighter_driver())
                elif cmd == 'driver':
                    driver = LighterDriver(account_id=0)
                    print(f"✓ 驱动实例创建成功: {driver.cex}")
                elif cmd == 'connect' and driver:
                    print("正在连接...")
                    asyncio.run(driver.lighter.connect())
                    print("✓ 连接成功")
                elif cmd == 'price' and driver:
                    try:
                        price = driver.get_price_now('ETH-USDC')
                        print(f"ETH-USDC 价格: {price}")
                    except Exception as e:
                        print(f"获取价格失败: {e}")
                elif cmd == 'help':
                    print("可用命令:")
                    print("- sync: 测试同步功能")
                    print("- async: 测试异步功能")
                    print("- driver: 创建驱动实例")
                    print("- connect: 连接客户端 (需要先创建driver)")
                    print("- price: 获取价格 (需要先连接)")
                    print("- quit: 退出")
                else:
                    print("未知命令，输入 'help' 查看帮助")
                    
            except KeyboardInterrupt:
                print("\n用户中断，退出...")
                break
            except Exception as e:
                print(f"命令执行失败: {e}")
    
    # 主程序入口
    print("Lighter驱动测试程序")
    print("选择测试模式:")
    print("1. 自动测试 (推荐)")
    print("2. 交互式测试")
    
    try:
        choice = input("请选择 (1/2): ").strip()
        
        if choice == '1':
            # 自动测试模式
            print("\n开始自动测试...")
            
            # 先测试同步功能
            test_sync_functions()
            
            # 再测试异步功能
            asyncio.run(test_lighter_driver())
            
        elif choice == '2':
            # 交互式测试模式
            interactive_test()
        else:
            print("无效选择，运行默认测试...")
            test_sync_functions()
            asyncio.run(test_lighter_driver())
            
    except KeyboardInterrupt:
        print("\n用户中断，程序退出")
    except Exception as e:
        print(f"程序运行错误: {e}")
        import traceback
        traceback.print_exc()


