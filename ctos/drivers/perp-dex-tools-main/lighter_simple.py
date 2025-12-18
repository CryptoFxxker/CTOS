#!/usr/bin/env python3
"""
Lighter 交易所最简化使用示例
仅包含初始化和下单的核心代码
"""

import os
import asyncio
import time
from decimal import Decimal
from typing import Dict, Any, Optional

import lighter
from lighter import SignerClient, ApiClient, Configuration
import aiohttp


class LighterSimple:
    """Lighter 交易所最简化客户端"""

    def __init__(self, ticker: str, max_retries: int = 3, retry_delay: float = 2.0):
        """初始化 Lighter 客户端
        
        Args:
            ticker: 交易对符号，如 'ETH'
            max_retries: 最大重试次数，默认 3
            retry_delay: 重试延迟（秒），默认 2.0
        """
        # 从环境变量读取配置
        self.api_key_private_key = os.getenv('LIGHTER_API_KEY_PRIVATE_KEY')
        self.account_index = int(os.getenv('LIGHTER_ACCOUNT_INDEX', '0'))
        self.api_key_index = int(os.getenv('LIGHTER_API_KEY_INDEX', '0'))
        self.base_url = "https://mainnet.zklighter.elliot.ai"
        
        if not self.api_key_private_key:
            raise ValueError("API_KEY_PRIVATE_KEY 必须设置")
        
        self.ticker = ticker
        self.lighter_client = None
        self.api_client = None
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # 市场配置
        self.market_id = None
        self.base_amount_multiplier = None
        self.price_multiplier = None
        
        # 检查代理设置
        self._check_proxy_settings()

    def _check_proxy_settings(self):
        """检查并显示代理设置"""
        http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
        https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
        
        if http_proxy or https_proxy:
            print(f"检测到代理设置:")
            if http_proxy:
                print(f"  HTTP_PROXY: {http_proxy}")
            if https_proxy:
                print(f"  HTTPS_PROXY: {https_proxy}")
            print("  提示: 如果连接失败，可能是代理问题。可以尝试取消设置代理环境变量。")

    async def connect(self):
        """连接交易所并初始化客户端"""
        # 初始化 API 客户端
        self.api_client = ApiClient(configuration=Configuration(host=self.base_url))
        
        # 初始化 Lighter 客户端
        self.lighter_client = SignerClient(
            url=self.base_url,
            private_key=self.api_key_private_key,
            account_index=self.account_index,
            api_key_index=self.api_key_index,
        )
        
        # 检查客户端
        err = self.lighter_client.check_client()
        if err is not None:
            raise Exception(f"客户端检查错误: {err}")
        
        # 获取市场配置
        await self._get_market_config()
        
        print(f"已连接到 Lighter，交易对: {self.ticker}, 市场ID: {self.market_id}")

    async def _get_market_config(self):
        """获取市场配置（带重试机制）"""
        last_error = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                order_api = lighter.OrderApi(self.api_client)
                order_books = await order_api.order_books()
                
                for market in order_books.order_books:
                    if market.symbol == self.ticker:
                        self.market_id = market.market_id
                        self.base_amount_multiplier = pow(10, market.supported_size_decimals)
                        self.price_multiplier = pow(10, market.supported_price_decimals)
                        return
                
                raise Exception(f"未找到交易对: {self.ticker}")
                
            except (aiohttp.client_exceptions.ServerDisconnectedError, 
                    aiohttp.client_exceptions.ClientConnectorError,
                    asyncio.TimeoutError,
                    Exception) as e:
                last_error = e
                error_type = type(e).__name__
                
                if attempt < self.max_retries:
                    print(f"⚠️  获取市场配置失败 (尝试 {attempt}/{self.max_retries}): {error_type}: {str(e)}")
                    print(f"   将在 {self.retry_delay} 秒后重试...")
                    await asyncio.sleep(self.retry_delay)
                else:
                    print(f"❌ 获取市场配置失败，已重试 {self.max_retries} 次")
                    if isinstance(e, aiohttp.client_exceptions.ServerDisconnectedError):
                        raise Exception(
                            f"服务器断开连接。可能的原因：\n"
                            f"  1. 代理服务器不稳定或配置错误\n"
                            f"  2. 网络连接问题\n"
                            f"  3. 服务器暂时不可用\n"
                            f"  建议：检查代理设置或稍后重试\n"
                            f"  原始错误: {error_type}: {str(e)}"
                        ) from e
                    else:
                        raise Exception(f"获取市场配置失败: {error_type}: {str(e)}") from e
        
        # 如果所有重试都失败
        if last_error:
            raise last_error

    async def place_limit_order(self, quantity: Decimal, price: Decimal, side: str) -> str:
        """下单（限价单）
        
        Args:
            quantity: 数量
            price: 价格
            side: 'buy' 或 'sell'
            
        Returns:
            client_order_index: 客户端订单索引
        """
        if self.lighter_client is None:
            raise ValueError("请先调用 connect() 连接交易所")
        
        # 确定订单方向
        is_ask = (side.lower() == 'sell')
        
        # 生成唯一的客户端订单索引
        client_order_index = int(time.time() * 1000) % 1000000
        
        # 下单参数
        order_params = {
            'market_index': self.market_id,
            'client_order_index': client_order_index,
            'base_amount': int(quantity * self.base_amount_multiplier),
            'price': int(price * self.price_multiplier),
            'is_ask': is_ask,
            'order_type': self.lighter_client.ORDER_TYPE_LIMIT,
            'time_in_force': self.lighter_client.ORDER_TIME_IN_FORCE_GOOD_TILL_TIME,
            'reduce_only': False,
            'trigger_price': 0,
        }
        
        # 创建订单
        create_order, tx_hash, error = await self.lighter_client.create_order(**order_params)
        
        if error is not None:
            raise Exception(f"下单失败: {error}")
        
        print(f"下单成功: {side} {quantity} @ {price}, 订单ID: {client_order_index}")
        return str(client_order_index)

    async def cancel_order(self, order_id: str):
        """取消订单
        
        Args:
            order_id: 订单ID（order_index）
        """
        if self.lighter_client is None:
            raise ValueError("请先调用 connect() 连接交易所")
        
        cancel_order, tx_hash, error = await self.lighter_client.cancel_order(
            market_index=self.market_id,
            order_index=int(order_id)
        )
        
        if error is not None:
            raise Exception(f"取消订单失败: {error}")
        
        print(f"取消订单成功: {order_id}")

    async def get_active_orders(self):
        """获取活跃订单列表"""
        if self.lighter_client is None:
            raise ValueError("请先调用 connect() 连接交易所")
        
        # 生成认证令牌
        auth_token, error = self.lighter_client.create_auth_token_with_expiry()
        if error is not None:
            raise Exception(f"创建认证令牌失败: {error}")
        
        # 获取活跃订单
        order_api = lighter.OrderApi(self.api_client)
        orders_response = await order_api.account_active_orders(
            account_index=self.account_index,
            market_id=self.market_id,
            auth=auth_token
        )
        
        return orders_response.orders if orders_response else []

    async def get_positions(self):
        """获取账户持仓"""
        account_api = lighter.AccountApi(self.api_client)
        account_data = await account_api.account(by="index", value=str(self.account_index))
        
        if account_data and account_data.accounts:
            for position in account_data.accounts[0].positions:
                if position.market_id == self.market_id:
                    return Decimal(position.position)
        
        return Decimal(0)

    async def disconnect(self):
        """断开连接"""
        if self.api_client:
            await self.api_client.close()
            self.api_client = None
        print("已断开连接")


async def main():
    """示例：使用 Lighter 交易所下单"""
    # 初始化客户端
    client = LighterSimple(ticker='ETH')
    
    try:
        # 连接交易所
        await client.connect()
        
        # 示例：下一个买单
        # await client.place_limit_order(
        #     quantity=Decimal('0.1'),
        #     price=Decimal('3000.0'),
        #     side='buy'
        # )
        
        # 示例：获取活跃订单
        # orders = await client.get_active_orders()
        # print(f"活跃订单数量: {len(orders)}")
        
        # 示例：获取持仓
        # position = await client.get_positions()
        # print(f"当前持仓: {position}")
        
    finally:
        # 断开连接
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

