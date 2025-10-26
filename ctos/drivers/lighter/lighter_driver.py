"""
Lighter exchange client implementation.
"""

import os
import asyncio
import time
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
import sys
import asyncio

"""
TIPS : !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!   
python -m pip install lighter-sdk
"""
# Import official Lighter SDK for API client
import lighter
from lighter import SignerClient, ApiClient, Configuration


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


from ctos.drivers.lighter.base import BaseExchangeClient, OrderResult, OrderInfo, query_retry
from ctos.drivers.lighter.logger import TradingLogger

# Import custom WebSocket implementation
from ctos.drivers.lighter.lighter_custom_websocket import LighterCustomWebSocketManager

# Suppress Lighter SDK debug logs
logging.getLogger('lighter').setLevel(logging.WARNING)
# Also suppress root logger DEBUG messages that might be coming from Lighter SDK
root_logger = logging.getLogger()
if root_logger.level == logging.DEBUG:
    root_logger.setLevel(logging.WARNING)


class LighterClient(BaseExchangeClient):
    """Lighter交易所客户端实现"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化Lighter客户端
        
        输入参数:
            config: 配置字典，包含交易配置信息
        
        输出: 无
        作用: 初始化Lighter交易所客户端，设置API密钥、账户索引和基础URL
        """
        super().__init__(config)

        # Lighter credentials from environment
        self.api_key_private_key = os.getenv('LIGHTER_API_KEY_PRIVATE_KEY')
        self.account_index = int(os.getenv('LIGHTER_ACCOUNT_INDEX', '0'))
        self.api_key_index = int(os.getenv('LIGHTER_API_KEY_INDEX', '0'))
        self.base_url = "https://mainnet.zklighter.elliot.ai"
        print('api_key_private_key: ', self.api_key_private_key)
        print('account_index: ', self.account_index)
        print('api_key_index: ', self.api_key_index)
        print('base_url: ', self.base_url)
        if not self.api_key_private_key:
            raise ValueError("LIGHTER_API_KEY_PRIVATE_KEY must be set in environment variables")

        # Initialize logger
        self.logger = TradingLogger(exchange="lighter", ticker='ETH-USDC', log_to_console=False)
        # self.logger = TradingLogger(exchange="lighter", ticker=self.config.ticker, log_to_console=False)
        self._order_update_handler = None

        # Initialize Lighter client (will be done in connect)
        self.lighter_client = None

        # Initialize API client (will be done in connect)
        self.api_client = None

        # Market configuration
        self.base_amount_multiplier = None
        self.price_multiplier = None
        self.orders_cache = {}
        self.current_order_client_id = None
        self.current_order = None

    def _validate_config(self) -> None:
        """
        验证Lighter配置
        
        输入参数: 无
        
        输出: 无
        作用: 检查必需的环境变量是否已设置，确保API密钥和账户索引已正确配置
        """
        return True
        required_env_vars = ['LIGHTER_API_KEY_PRIVATE_KEY', 'LIGHTER_ACCOUNT_INDEX', 'LIGHTER_API_KEY_INDEX']
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {missing_vars}")

    async def _get_market_config(self, ticker: str) -> Tuple[int, int, int]:
        """
        获取ticker的市场配置信息
        
        输入参数:
            ticker: 交易对符号
        
        输出: Tuple[int, int, int] - (市场ID, 基础数量乘数, 价格乘数)
        作用: 使用官方SDK获取指定ticker的市场配置，包括市场ID和精度乘数
        """
        try:
            # Use shared API client
            order_api = lighter.OrderApi(self.api_client)

            # Get order books to find market info
            order_books = await order_api.order_books()

            for market in order_books.order_books:
                if market.symbol == ticker:
                    market_id = market.market_id
                    base_multiplier = pow(10, market.supported_size_decimals)
                    price_multiplier = pow(10, market.supported_price_decimals)

                    # Store market info for later use
                    self.config.market_info = market

                    self.logger.log(
                        f"Market config for {ticker}: ID={market_id}, "
                        f"Base multiplier={base_multiplier}, Price multiplier={price_multiplier}",
                        "INFO"
                    )
                    return market_id, base_multiplier, price_multiplier

            raise Exception(f"Ticker {ticker} not found in available markets")

        except Exception as e:
            self.logger.log(f"Error getting market config: {e}", "ERROR")
            raise


    async def _initialize_lighter_client(self):
        """
        初始化Lighter客户端
        
        输入参数: 无
        
        输出: 无
        作用: 使用官方SDK初始化Lighter客户端，验证客户端状态
        """
        if self.lighter_client is None:
            try:
                self.lighter_client = SignerClient(
                    url=self.base_url,
                    private_key=self.api_key_private_key,
                    account_index=self.account_index,
                    api_key_index=self.api_key_index,
                )

                # Check client
                err = self.lighter_client.check_client()
                if err is not None:
                    raise Exception(f"CheckClient error: {err}")

                self.logger.log("Lighter client initialized successfully", "INFO")
            except Exception as e:
                self.logger.log(f"Failed to initialize Lighter client: {e}", "ERROR")
                raise
        return self.lighter_client


    async def connect(self) -> None:
        """
        连接到Lighter交易所
        
        输入参数: 无
        
        输出: 无
        作用: 建立与Lighter交易所的连接，初始化API客户端、Lighter客户端和WebSocket管理器
        """
        try:
            # Initialize shared API client
            self.api_client = ApiClient(configuration=Configuration(host=self.base_url))

            # Initialize Lighter client
            await self._initialize_lighter_client()

            # Add market config to config for WebSocket manager
            self.config["market_index"] = self.config.get("contract_id", 0)
            self.config["account_index"] = self.config.get("account_index", 0)
            self.config["lighter_client"] = self.lighter_client

            # Initialize WebSocket manager (using custom implementation)
            self.ws_manager = LighterCustomWebSocketManager(
                config=self.config,
                order_update_callback=self._handle_websocket_order_update
            )

            # Set logger for WebSocket manager
            self.ws_manager.set_logger(self.logger)

            # Start WebSocket connection in background task
            asyncio.create_task(self.ws_manager.connect())
            # Wait a moment for connection to establish
            await asyncio.sleep(2)

        except Exception as e:
            self.logger.log(f"Error connecting to Lighter: {e}", "ERROR")
            raise

    async def disconnect(self) -> None:
        """
        断开与Lighter的连接
        
        输入参数: 无
        
        输出: 无
        作用: 关闭WebSocket连接和API客户端，清理相关资源
        """
        try:
            if hasattr(self, 'ws_manager') and self.ws_manager:
                await self.ws_manager.disconnect()

            # Close shared API client
            if self.api_client:
                await self.api_client.close()
                self.api_client = None
        except Exception as e:
            self.logger.log(f"Error during Lighter disconnect: {e}", "ERROR")

    def get_contract_attributes_sync(self) -> Tuple[str, Decimal]:
        """
        同步版本的获取合约属性函数
        
        输入参数: 无
        
        输出: Tuple[str, Decimal] - (合约ID, 最小价格变动单位)
        作用: 同步获取合约属性信息
        """
        return self._run_async_safely(self.get_contract_attributes())

    def get_market_config_sync(self, ticker: str) -> Tuple[int, int, int]:
        """
        同步版本的市场配置获取函数
        
        输入参数:
            ticker: 交易对符号
        
        输出: Tuple[int, int, int] - (市场ID, 基础数量乘数, 价格乘数)
        作用: 同步获取指定ticker的市场配置信息
        """
        return self._run_async_safely(self._get_market_config(ticker))

    def connect_sync(self) -> None:
        """
        同步版本的连接函数
        
        输入参数: 无
        
        输出: 无
        作用: 同步连接到Lighter交易所
        """
        return self._run_async_safely(self.connect())

    def disconnect_sync(self) -> None:
        """
        同步版本的断开连接函数
        
        输入参数: 无
        
        输出: 无
        作用: 同步断开与Lighter的连接
        """
        return self._run_async_safely(self.disconnect())

    def get_exchange_name(self) -> str:
        """
        获取交易所名称
        
        输入参数: 无
        
        输出: str - 交易所名称
        作用: 返回当前交易所的名称标识
        """
        return "lighter"

    def setup_order_update_handler(self, handler) -> None:
        """
        设置WebSocket订单更新处理器
        
        输入参数:
            handler: 订单更新处理函数
        
        输出: 无
        作用: 设置用于处理WebSocket订单更新消息的回调函数
        """
        self._order_update_handler = handler

    def _handle_websocket_order_update(self, order_data_list: List[Dict[str, Any]]):
        """
        处理来自WebSocket的订单更新
        
        输入参数:
            order_data_list: 订单更新数据列表
        
        输出: 无
        作用: 处理WebSocket接收到的订单更新消息，更新订单缓存并记录交易日志
        """
        for order_data in order_data_list:
            if order_data['market_index'] != self.config.contract_id:
                continue

            side = 'sell' if order_data['is_ask'] else 'buy'
            if side == self.config.close_order_side:
                order_type = "CLOSE"
            else:
                order_type = "OPEN"

            order_id = order_data['order_index']
            status = order_data['status'].upper()
            filled_size = Decimal(order_data['filled_base_amount'])
            size = Decimal(order_data['initial_base_amount'])
            price = Decimal(order_data['price'])
            remaining_size = Decimal(order_data['remaining_base_amount'])

            if order_id in self.orders_cache.keys():
                if (self.orders_cache[order_id]['status'] == 'OPEN' and
                        status == 'OPEN' and
                        filled_size == self.orders_cache[order_id]['filled_size']):
                    continue
                elif status in ['FILLED', 'CANCELED']:
                    del self.orders_cache[order_id]
                else:
                    self.orders_cache[order_id]['status'] = status
                    self.orders_cache[order_id]['filled_size'] = filled_size
            elif status == 'OPEN':
                self.orders_cache[order_id] = {'status': status, 'filled_size': filled_size}

            if status == 'OPEN' and filled_size > 0:
                status = 'PARTIALLY_FILLED'

            if status == 'OPEN':
                self.logger.log(f"[{order_type}] [{order_id}] {status} "
                                f"{size} @ {price}", "INFO")
            else:
                self.logger.log(f"[{order_type}] [{order_id}] {status} "
                                f"{filled_size} @ {price}", "INFO")

            if order_data['client_order_index'] == self.current_order_client_id or order_type == 'OPEN':
                current_order = OrderInfo(
                    order_id=order_id,
                    side=side,
                    size=size,
                    price=price,
                    status=status,
                    filled_size=filled_size,
                    remaining_size=remaining_size,
                    cancel_reason=''
                )
                self.current_order = current_order

            if status in ['FILLED', 'CANCELED']:
                self.logger.log_transaction(order_id, side, filled_size, price, status)

    @query_retry(default_return=(0, 0))
    async def fetch_bbo_prices(self, contract_id: str) -> Tuple[Decimal, Decimal]:
        """
        从Lighter获取最佳买卖价格
        
        输入参数:
            contract_id: 合约ID
        
        输出: Tuple[Decimal, Decimal] - (最佳买价, 最佳卖价)
        作用: 从WebSocket数据获取指定合约的最佳买价和卖价，用于订单价格计算
        """
        # Use WebSocket data if available
        if (hasattr(self, 'ws_manager') and
                self.ws_manager.best_bid and self.ws_manager.best_ask):
            best_bid = Decimal(str(self.ws_manager.best_bid))
            best_ask = Decimal(str(self.ws_manager.best_ask))

            if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
                self.logger.log("Invalid bid/ask prices", "ERROR")
                raise ValueError("Invalid bid/ask prices")
        else:
            self.logger.log("Unable to get bid/ask prices from WebSocket.", "ERROR")
            raise ValueError("WebSocket not running. No bid/ask prices available")

        return best_bid, best_ask

    async def _submit_order_with_retry(self, order_params: Dict[str, Any]) -> OrderResult:
        """
        使用重试机制提交订单
        
        输入参数:
            order_params: 订单参数字典
        
        输出: OrderResult - 订单结果对象
        作用: 使用官方SDK提交订单，处理订单创建错误
        """
        # Ensure client is initialized
        if self.lighter_client is None:
            # This is a sync method, so we need to handle this differently
            # For now, raise an error if client is not initialized
            raise ValueError("Lighter client not initialized. Call connect() first.")

        # Create order using official SDK
        create_order, tx_hash, error = await self.lighter_client.create_order(**order_params)
        if error is not None:
            return OrderResult(
                success=False, order_id=str(order_params['client_order_index']),
                error_message=f"Order creation error: {error}")

        else:
            return OrderResult(success=True, order_id=str(order_params['client_order_index']))

    async def place_limit_order(self, contract_id: str, quantity: Decimal, price: Decimal,
                                side: str) -> OrderResult:
        """
        下限价单
        
        输入参数:
            contract_id: 合约ID
            quantity: 订单数量
            price: 订单价格
            side: 订单方向 ('buy' 或 'sell')
        
        输出: OrderResult - 订单结果对象
        作用: 在Lighter交易所下限价单，使用官方SDK创建订单
        """
        # Ensure client is initialized
        if self.lighter_client is None:
            await self._initialize_lighter_client()

        # Determine order side and price
        if side.lower() == 'buy':
            is_ask = False
        elif side.lower() == 'sell':
            is_ask = True
        else:
            raise Exception(f"Invalid side: {side}")

        # Generate unique client order index
        client_order_index = int(time.time() * 1000) % 1000000  # Simple unique ID
        self.current_order_client_id = client_order_index

        # Create order parameters
        order_params = {
            'market_index': self.config.contract_id,
            'client_order_index': client_order_index,
            'base_amount': int(quantity * self.base_amount_multiplier),
            'price': int(price * self.price_multiplier),
            'is_ask': is_ask,
            'order_type': self.lighter_client.ORDER_TYPE_LIMIT,
            'time_in_force': self.lighter_client.ORDER_TIME_IN_FORCE_GOOD_TILL_TIME,
            'reduce_only': False,
            'trigger_price': 0,
        }

        order_result = await self._submit_order_with_retry(order_params)
        return order_result

    async def place_open_order(self, contract_id: str, quantity: Decimal, direction: str) -> OrderResult:
        """
        下开仓订单
        
        输入参数:
            contract_id: 合约ID
            quantity: 订单数量
            direction: 订单方向 ('buy' 或 'sell')
        
        输出: OrderResult - 订单结果对象
        作用: 在Lighter交易所下开仓订单，等待订单成交并返回结果
        """

        self.current_order = None
        self.current_order_client_id = None
        order_price = await self.get_order_price(direction)

        order_price = self.round_to_tick(order_price)
        order_result = await self.place_limit_order(contract_id, quantity, order_price, direction)
        if not order_result.success:
            raise Exception(f"[OPEN] Error placing order: {order_result.error_message}")

        start_time = time.time()
        order_status = 'OPEN'

        # While waiting for order to be filled
        while time.time() - start_time < 10 and order_status != 'FILLED':
            await asyncio.sleep(0.1)
            if self.current_order is not None:
                order_status = self.current_order.status

        return OrderResult(
            success=True,
            order_id=self.current_order.order_id,
            side=direction,
            size=quantity,
            price=order_price,
            status=self.current_order.status
        )

    async def _get_active_close_orders(self, contract_id: str) -> int:
        """
        获取活跃的平仓订单数量
        
        输入参数:
            contract_id: 合约ID
        
        输出: int - 活跃平仓订单数量
        作用: 统计指定合约的活跃平仓订单数量，用于订单管理
        """
        active_orders = await self.get_active_orders(contract_id)
        active_close_orders = 0
        for order in active_orders:
            if order.side == self.config.close_order_side:
                active_close_orders += 1
        return active_close_orders

    async def place_close_order(self, contract_id: str, quantity: Decimal, price: Decimal, side: str) -> OrderResult:
        """
        下平仓订单
        
        输入参数:
            contract_id: 合约ID
            quantity: 订单数量
            price: 订单价格
            side: 订单方向 ('buy' 或 'sell')
        
        输出: OrderResult - 订单结果对象
        作用: 在Lighter交易所下平仓订单，等待订单确认后返回结果
        """
        self.current_order = None
        self.current_order_client_id = None
        order_result = await self.place_limit_order(contract_id, quantity, price, side)

        # wait for 5 seconds to ensure order is placed
        await asyncio.sleep(5)
        if order_result.success:
            return OrderResult(
                success=True,
                order_id=order_result.order_id,
                side=side,
                size=quantity,
                price=price,
                status='OPEN'
            )
        else:
            raise Exception(f"[CLOSE] Error placing order: {order_result.error_message}")
    
    async def get_order_price(self, side: str = '') -> Decimal:
        """
        获取订单价格
        
        输入参数:
            side: 订单方向 ('buy' 或 'sell')，可选参数
        
        输出: Decimal - 订单价格
        作用: 根据当前市场价格和活跃平仓订单计算合适的订单价格
        """
        # Get current market prices
        best_bid, best_ask = await self.fetch_bbo_prices(self.config.contract_id)
        if best_bid <= 0 or best_ask <= 0 or best_bid >= best_ask:
            self.logger.log("Invalid bid/ask prices", "ERROR")
            raise ValueError("Invalid bid/ask prices")

        order_price = (best_bid + best_ask) / 2

        active_orders = await self.get_active_orders(self.config.contract_id)
        close_orders = [order for order in active_orders if order.side == self.config.close_order_side]
        for order in close_orders:
            if side == 'buy':
                order_price = min(order_price, order.price - self.config.tick_size)
            else:
                order_price = max(order_price, order.price + self.config.tick_size)

        return order_price

    async def cancel_order(self, order_id: str) -> OrderResult:
        """
        取消订单
        
        输入参数:
            order_id: 订单ID
        
        输出: OrderResult - 订单结果对象
        作用: 取消指定ID的订单，使用官方SDK发送取消交易
        """
        # Ensure client is initialized
        if self.lighter_client is None:
            await self._initialize_lighter_client()

        # Cancel order using official SDK
        cancel_order, tx_hash, error = await self.lighter_client.cancel_order(
            market_index=self.config.contract_id,
            order_index=int(order_id)  # Assuming order_id is the order index
        )

        if error is not None:
            return OrderResult(success=False, error_message=f"Cancel order error: {error}")

        if tx_hash:
            return OrderResult(success=True)
        else:
            return OrderResult(success=False, error_message='Failed to send cancellation transaction')

    async def get_order_info(self, order_id: str) -> Optional[OrderInfo]:
        """
        获取订单信息
        
        输入参数:
            order_id: 订单ID
        
        输出: Optional[OrderInfo] - 订单信息对象，如果订单不存在则返回None
        作用: 根据订单ID查询订单的详细信息，通过账户持仓信息获取已成交订单
        """
        try:
            # Use shared API client to get account info
            account_api = lighter.AccountApi(self.api_client)

            # Get account orders
            account_data = await account_api.account(by="index", value=str(self.account_index))

            # Look for the specific order in account positions
            for position in account_data.positions:
                if position.symbol == self.config.ticker:
                    position_amt = abs(float(position.position))
                    if position_amt > 0.001:  # Only include significant positions
                        return OrderInfo(
                            order_id=order_id,
                            side="buy" if float(position.position) > 0 else "sell",
                            size=Decimal(str(position_amt)),
                            price=Decimal(str(position.avg_price)),
                            status="FILLED",  # Positions are filled orders
                            filled_size=Decimal(str(position_amt)),
                            remaining_size=Decimal('0')
                        )

            return None

        except Exception as e:
            self.logger.log(f"Error getting order info: {e}", "ERROR")
            return None

    @query_retry(reraise=True)
    async def _fetch_orders_with_retry(self) -> List[Dict[str, Any]]:
        """
        使用重试机制获取订单列表
        
        输入参数: 无
        
        输出: List[Dict[str, Any]] - 订单数据列表
        作用: 使用官方SDK获取账户的活跃订单列表，包含重试机制
        """
        # Ensure client is initialized
        if self.lighter_client is None:
            await self._initialize_lighter_client()

        # Generate auth token for API call
        auth_token, error = self.lighter_client.create_auth_token_with_expiry()
        if error is not None:
            self.logger.log(f"Error creating auth token: {error}", "ERROR")
            raise ValueError(f"Error creating auth token: {error}")

        # Use OrderApi to get active orders
        order_api = lighter.OrderApi(self.api_client)

        # Get active orders for the specific market
        orders_response = await order_api.account_active_orders(
            account_index=self.account_index,
            market_id=self.config.contract_id,
            auth=auth_token
        )

        if not orders_response:
            self.logger.log("Failed to get orders", "ERROR")
            raise ValueError("Failed to get orders")

        return orders_response.orders

    async def get_active_orders(self, contract_id: str) -> List[OrderInfo]:
        """
        获取活跃订单列表
        
        输入参数:
            contract_id: 合约ID
        
        输出: List[OrderInfo] - 活跃订单信息列表
        作用: 获取指定合约的所有活跃订单（未成交或部分成交的订单）
        """
        order_list = await self._fetch_orders_with_retry()

        # Filter orders for the specific market
        contract_orders = []
        for order in order_list:
            # Convert Lighter Order to OrderInfo
            side = "sell" if order.is_ask else "buy"
            size = Decimal(order.initial_base_amount)
            price = Decimal(order.price)

            # Only include orders with remaining size > 0
            if size > 0:
                contract_orders.append(OrderInfo(
                    order_id=str(order.order_index),
                    side=side,
                    size=Decimal(order.remaining_base_amount),  # FIXME: This is wrong. Should be size
                    price=price,
                    status=order.status.upper(),
                    filled_size=Decimal(order.filled_base_amount),
                    remaining_size=Decimal(order.remaining_base_amount)
                ))

        return contract_orders

    @query_retry(reraise=True)
    async def _fetch_positions_with_retry(self) -> List[Dict[str, Any]]:
        """
        使用重试机制获取持仓信息
        
        输入参数: 无
        
        输出: List[Dict[str, Any]] - 持仓数据列表
        作用: 使用官方SDK获取账户的持仓信息，包含重试机制
        """
        # Use shared API client
        account_api = lighter.AccountApi(self.api_client)

        # Get account info
        account_data = await account_api.account(by="index", value=str(self.account_index))

        if not account_data or not account_data.accounts:
            self.logger.log("Failed to get positions", "ERROR")
            raise ValueError("Failed to get positions")

        return account_data.accounts[0].positions

    async def get_account_positions(self) -> Decimal:
        """
        获取账户持仓数量
        
        输入参数: 无
        
        输出: Decimal - 持仓数量
        作用: 获取当前账户在指定合约上的持仓数量
        """
        # Get account info which includes positions
        positions = await self._fetch_positions_with_retry()

        # Find position for current market
        for position in positions:
            if position.market_id == self.config.contract_id:
                return Decimal(position.position)

        return Decimal(0)

    async def get_contract_attributes(self) -> Tuple[str, Decimal]:
        """
        获取合约属性信息
        
        输入参数: 无
        
        输出: Tuple[str, Decimal] - (合约ID, 最小价格变动单位)
        作用: 根据配置的ticker获取对应的合约ID和最小价格变动单位，设置市场配置参数
        """
        ticker = self.config.ticker
        if len(ticker) == 0:
            self.logger.log("Ticker is empty", "ERROR")
            raise ValueError("Ticker is empty")

        order_api = lighter.OrderApi(self.api_client)
        # Get all order books to find the market for our ticker
        order_books = await order_api.order_books()

        # Find the market that matches our ticker
        market_info = None
        for market in order_books.order_books:
            print('market.symbol: ', market.symbol)
            if market.symbol == ticker:
                market_info = market
                break

        if market_info is None:
            self.logger.log("Failed to get markets", "ERROR")
            raise ValueError("Failed to get markets")

        market_summary = await order_api.order_book_details(market_id=market_info.market_id)
        order_book_details = market_summary.order_book_details[0]
        # Set contract_id to market name (Lighter uses market IDs as identifiers)
        self.config.contract_id = market_info.market_id
        self.base_amount_multiplier = pow(10, market_info.supported_size_decimals)
        self.price_multiplier = pow(10, market_info.supported_price_decimals)

        try:
            self.config.tick_size = Decimal("1") / (Decimal("10") ** order_book_details.price_decimals)
        except Exception:
            self.logger.log("Failed to get tick size", "ERROR")
            raise ValueError("Failed to get tick size")

        return self.config.contract_id, self.config.tick_size

    def _run_async_safely(self, coro):
        """
        安全地运行异步函数的通用方法
        
        输入参数:
            coro: 协程对象
        
        输出: 协程的返回值
        作用: 处理不同环境下的异步函数调用
        """
        import asyncio
        import threading
        
        try:
            # 尝试获取当前运行的事件循环
            loop = asyncio.get_running_loop()
            # 如果成功获取到，说明当前在事件循环中
            # 这种情况下我们不能使用asyncio.run()，需要使用其他方法
            
            # 方法1: 使用线程池在新线程中运行
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, coro)
                return future.result()
                
        except RuntimeError:
            # 没有运行的事件循环，可以直接使用asyncio.run()
            return asyncio.run(coro)

    def get_contract_attributes_sync(self) -> Tuple[str, Decimal]:
        """
        同步版本的获取合约属性函数
        
        输入参数: 无
        
        输出: Tuple[str, Decimal] - (合约ID, 最小价格变动单位)
        作用: 同步获取合约属性信息
        """
        import asyncio
        try:
            # 检查是否在事件循环中
            try:
                loop = asyncio.get_running_loop()
                # 如果事件循环正在运行，使用线程池
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.get_contract_attributes())
                    return future.result()
            except RuntimeError:
                # 没有运行的事件循环，可以直接使用asyncio.run()
                return asyncio.run(self.get_contract_attributes())
        except Exception as e:
            self.logger.log(f"同步获取合约属性失败: {e}", "ERROR")
            raise


if __name__ == "__main__":
    """
    Lighter客户端测试主函数
    用于测试Lighter交易所客户端的各项功能
    """
    import asyncio
    from decimal import Decimal
    
    async def test_lighter_client():
        """测试Lighter客户端的异步功能"""
        print("=" * 60)
        print("Lighter客户端测试开始")
        print("=" * 60)
        
        try:
            # 1. 初始化客户端
            print("\n1. 初始化Lighter客户端...")
            config = {
                'ticker': 'ETH-USDC',
                'contract_id': None,
                'quantity': Decimal('0.1'),
                'tick_size': Decimal('0.01'),
                'direction': 'buy',
                'close_order_side': 'sell'
            }
            
            client = LighterClient(config)
            print(f"✓ 客户端初始化成功: {client.get_exchange_name()}")
            print(f"  - API密钥: {'已设置' if client.api_key_private_key else '未设置'}")
            print(f"  - 账户索引: {client.account_index}")
            print(f"  - API密钥索引: {client.api_key_index}")
            print(f"  - 基础URL: {client.base_url}")
            
            # 2. 测试连接
            print("\n2. 测试Lighter客户端连接...")
            try:
                await client.connect()
                print("✓ Lighter客户端连接成功")
            except Exception as e:
                print(f"✗ Lighter客户端连接失败: {e}")
                return
            
            # 3. 测试获取合约属性
            print("\n3. 测试获取合约属性...")
            try:
                contract_id, tick_size = await client.get_contract_attributes()
                print(f"✓ 合约ID: {contract_id}")
                print(f"✓ 价格精度: {tick_size}")
                print(f"✓ 基础数量乘数: {client.base_amount_multiplier}")
                print(f"✓ 价格乘数: {client.price_multiplier}")
            except Exception as e:
                print(f"✗ 获取合约属性失败: {e}")
            
            # 4. 测试获取最佳买卖价格
            print("\n4. 测试获取最佳买卖价格...")
            try:
                best_bid, best_ask = await client.fetch_bbo_prices(contract_id)
                print(f"✓ 最佳买价: {best_bid}")
                print(f"✓ 最佳卖价: {best_ask}")
                print(f"✓ 中间价: {(best_bid + best_ask) / 2}")
            except Exception as e:
                print(f"✗ 获取价格失败: {e}")
            
            # 5. 测试获取订单价格
            print("\n5. 测试获取订单价格...")
            try:
                buy_price = await client.get_order_price('buy')
                sell_price = await client.get_order_price('sell')
                print(f"✓ 买入价格: {buy_price}")
                print(f"✓ 卖出价格: {sell_price}")
            except Exception as e:
                print(f"✗ 获取订单价格失败: {e}")
            
            # 6. 测试获取活跃订单
            print("\n6. 测试获取活跃订单...")
            try:
                active_orders = await client.get_active_orders(contract_id)
                print(f"✓ 活跃订单数量: {len(active_orders)}")
                for i, order in enumerate(active_orders[:3]):  # 只显示前3个
                    print(f"  订单{i+1}: {order.side} {order.size} @ {order.price} ({order.status})")
            except Exception as e:
                print(f"✗ 获取活跃订单失败: {e}")
            
            # 7. 测试获取持仓
            print("\n7. 测试获取账户持仓...")
            try:
                position = await client.get_account_positions()
                print(f"✓ 当前持仓: {position}")
            except Exception as e:
                print(f"✗ 获取持仓失败: {e}")
            
            # 8. 测试获取订单信息
            print("\n8. 测试获取订单信息...")
            try:
                # 如果有活跃订单，获取第一个订单的信息
                if active_orders:
                    order_info = await client.get_order_info(active_orders[0].order_id)
                    if order_info:
                        print(f"✓ 订单信息: {order_info.order_id} - {order_info.side} {order_info.size} @ {order_info.price}")
                    else:
                        print("✓ 订单信息: 无订单信息")
                else:
                    print("✓ 订单信息: 无活跃订单")
            except Exception as e:
                print(f"✗ 获取订单信息失败: {e}")
            
            # 9. 测试市场配置
            print("\n9. 测试获取市场配置...")
            try:
                market_id, base_multiplier, price_multiplier = await client._get_market_config('ETH')
                print(f"✓ 市场ID: {market_id}")
                print(f"✓ 基础数量乘数: {base_multiplier}")
                print(f"✓ 价格乘数: {price_multiplier}")
            except Exception as e:
                print(f"✗ 获取市场配置失败: {e}")
            
            # 10. 测试WebSocket连接状态
            print("\n10. 测试WebSocket连接状态...")
            try:
                if hasattr(client, 'ws_manager') and client.ws_manager:
                    print(f"✓ WebSocket管理器已初始化")
                    print(f"✓ 最佳买价: {getattr(client.ws_manager, 'best_bid', 'N/A')}")
                    print(f"✓ 最佳卖价: {getattr(client.ws_manager, 'best_ask', 'N/A')}")
                else:
                    print("✗ WebSocket管理器未初始化")
            except Exception as e:
                print(f"✗ WebSocket状态检查失败: {e}")
            
            # 11. 断开连接
            print("\n11. 断开连接...")
            try:
                await client.disconnect()
                print("✓ 连接已断开")
            except Exception as e:
                print(f"✗ 断开连接失败: {e}")
            
            print("\n" + "=" * 60)
            print("Lighter客户端测试完成")
            print("=" * 60)
            
        except Exception as e:
            print(f"✗ 测试过程中发生错误: {e}")
            import traceback
            traceback.print_exc()
    
    def test_sync_functions():
        """测试同步功能"""
        print("\n" + "=" * 60)
        print("同步功能测试")
        print("=" * 60)
        
        try:
            # 初始化客户端
            config = {
                'ticker': 'ETH-USDC',
                'contract_id': None,
                'quantity': Decimal('0.1'),
                'tick_size': Decimal('0.01'),
                'direction': 'buy',
                'close_order_side': 'sell'
            }
            
            client = LighterClient(config)
            print(f"✓ 客户端初始化成功: {client.get_exchange_name()}")
            
            # 测试同步连接
            print("\n测试同步连接...")
            try:
                client.connect_sync()
                print("✓ 同步连接成功")
            except Exception as e:
                print(f"✗ 同步连接失败: {e}")
            
            # 测试同步获取合约属性
            print("\n测试同步获取合约属性...")
            try:
                contract_id, tick_size = client.get_contract_attributes_sync()
                print(f"✓ 合约ID: {contract_id}")
                print(f"✓ 价格精度: {tick_size}")
            except Exception as e:
                print(f"✗ 同步获取合约属性失败: {e}")
            
            # 测试同步获取市场配置
            print("\n测试同步获取市场配置...")
            try:
                market_id, base_multiplier, price_multiplier = client.get_market_config_sync('ETH')
                print(f"✓ 市场ID: {market_id}")
                print(f"✓ 基础数量乘数: {base_multiplier}")
                print(f"✓ 价格乘数: {price_multiplier}")
            except Exception as e:
                print(f"✗ 同步获取市场配置失败: {e}")
            
            # 测试同步断开连接
            print("\n测试同步断开连接...")
            try:
                client.disconnect_sync()
                print("✓ 同步断开连接成功")
            except Exception as e:
                print(f"✗ 同步断开连接失败: {e}")
            
        except Exception as e:
            print(f"✗ 同步功能测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    def interactive_test():
        """交互式测试"""
        print("\n" + "=" * 60)
        print("交互式测试模式")
        print("=" * 60)
        print("可用的测试命令:")
        print("1. sync - 测试同步功能")
        print("2. async - 测试异步功能")
        print("3. client - 创建客户端实例")
        print("4. connect - 连接客户端")
        print("5. disconnect - 断开连接")
        print("6. price - 获取价格")
        print("7. orders - 获取活跃订单")
        print("8. position - 获取持仓")
        print("9. quit - 退出")
        
        client = None
        
        while True:
            try:
                cmd = input("\n请输入命令: ").strip().lower()
                
                if cmd == 'quit':
                    break
                elif cmd == 'sync':
                    test_sync_functions()
                elif cmd == 'async':
                    asyncio.run(test_lighter_client())
                elif cmd == 'client':
                    config = {
                        'ticker': 'ETH',
                        'contract_id': None,
                        'quantity': Decimal('0.1'),
                        'tick_size': Decimal('0.01'),
                        'direction': 'buy',
                        'close_order_side': 'sell'
                    }
                    client = LighterClient(config)
                    print(f"✓ 客户端实例创建成功: {client.get_exchange_name()}")
                elif cmd == 'connect' and client:
                    print("正在连接...")
                    client.connect_sync()
                    print("✓ 连接成功")
                elif cmd == 'disconnect' and client:
                    print("正在断开连接...")
                    client.disconnect_sync()
                    print("✓ 断开连接成功")
                elif cmd == 'price' and client:
                    try:
                        contract_id, tick_size = client.get_contract_attributes_sync()
                        best_bid, best_ask = asyncio.run(client.fetch_bbo_prices(contract_id))
                        print(f"ETH 价格 - 买价: {best_bid}, 卖价: {best_ask}, 中间价: {(best_bid + best_ask) / 2}")
                    except Exception as e:
                        print(f"获取价格失败: {e}")
                elif cmd == 'orders' and client:
                    try:
                        contract_id, _ = client.get_contract_attributes_sync()
                        orders = asyncio.run(client.get_active_orders(contract_id))
                        print(f"活跃订单数量: {len(orders)}")
                        for i, order in enumerate(orders[:5]):  # 显示前5个
                            print(f"  订单{i+1}: {order.side} {order.size} @ {order.price} ({order.status})")
                    except Exception as e:
                        print(f"获取订单失败: {e}")
                elif cmd == 'position' and client:
                    try:
                        position = asyncio.run(client.get_account_positions())
                        print(f"当前持仓: {position}")
                    except Exception as e:
                        print(f"获取持仓失败: {e}")
                elif cmd == 'help':
                    print("可用命令:")
                    print("- sync: 测试同步功能")
                    print("- async: 测试异步功能")
                    print("- client: 创建客户端实例")
                    print("- connect: 连接客户端 (需要先创建client)")
                    print("- disconnect: 断开连接 (需要先连接)")
                    print("- price: 获取价格 (需要先连接)")
                    print("- orders: 获取活跃订单 (需要先连接)")
                    print("- position: 获取持仓 (需要先连接)")
                    print("- quit: 退出")
                else:
                    print("未知命令，输入 'help' 查看帮助")
                    
            except KeyboardInterrupt:
                print("\n用户中断，退出...")
                break
            except Exception as e:
                print(f"命令执行失败: {e}")
    
    # 主程序入口
    print("Lighter客户端测试程序")
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
            asyncio.run(test_lighter_client())
            
        elif choice == '2':
            # 交互式测试模式
            interactive_test()
        else:
            print("无效选择，运行默认测试...")
            test_sync_functions()
            asyncio.run(test_lighter_client())
            
    except KeyboardInterrupt:
        print("\n用户中断，程序退出")
    except Exception as e:
        print(f"程序运行错误: {e}")
        import traceback
        traceback.print_exc()


