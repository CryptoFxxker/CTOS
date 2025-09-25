# -*- coding: utf-8 -*-
# ctos/core/kernel/syscalls.py
# A minimal, old-Python-compatible syscall interface.
# No Protocol/dataclasses; plain base class with NotImplementedError.

class TradingSyscalls(object):
    # ---- Ref-data / meta ----
    def symbols(self):
        """Return an iterable of unified symbols, e.g. ['BTC-USDT', 'ETH-USDT']"""
        raise NotImplementedError

    def exchange_limits(self):
        """Return dict of exchange limits/scales"""
        raise NotImplementedError

    def exchange_information(self):
        """Return dict of exchange information"""
        raise NotImplementedError

    def fees(self):
        """Return dict of fee info (maker/taker etc.)"""
        raise NotImplementedError

    # ---- Market data ----
    def get_price_now(self, symbol):
        """Return last price (float)"""
        raise NotImplementedError

    def get_orderbook(self, symbol, level=50):
        """Return dict: {'symbol': 'BTC-USDT[-SWAP]', 'bids': [...], 'asks': [...]}"""
        raise NotImplementedError

    def get_klines(self, symbol, timeframe='1h', limit=200, start_time=None, end_time=None):
        """Return list of dict rows:
           [{'ts': 1710000000000, 'open':1.0,'high':2.0,'low':0.9,'close':1.5,'volume':123.45}, ...]
           :param symbol: Trading pair symbol
           :param timeframe: Time interval (e.g., '1m', '1h', '1d')
           :param limit: Number of klines to return
           :param start_time: Start timestamp (optional)
           :param end_time: End timestamp (optional)
        """
        raise NotImplementedError

    # ---- Trading ----
    def place_order(self, symbol, side, order_type, size, price=None, client_id=None, max_retries=3, **kwargs):
        """Place order, return (order_id, error)
           :param symbol: Trading pair symbol
           :param side: 'buy'/'sell' or 'bid'/'ask'
           :param order_type: 'limit'/'market'
           :param size: Order quantity
           :param price: Order price (required for limit orders)
           :param client_id: Client order ID
           :param max_retries: Maximum retry attempts
        """
        raise NotImplementedError

    def amend_order(self, order_id, symbol=None, price=None, size=None, side=None, order_type=None, 
                   time_in_force=None, post_only=None, **kwargs):
        """Amend/modify order
           :param order_id: Order ID to amend
           :param symbol: Trading pair symbol (required for some exchanges)
           :param price: New price
           :param size: New size
           :param side: New side
           :param order_type: New order type
           :param time_in_force: New time in force
           :param post_only: New post only flag
        """
        raise NotImplementedError

    def revoke_order(self, order_id, symbol=None):
        """Cancel a single order
           :param order_id: Order ID to cancel
           :param symbol: Trading pair symbol (required for some exchanges)
        """
        raise NotImplementedError

    def cancel_all(self, symbol=None, order_ids=None):
        """Cancel all orders (optionally filtered by symbol or order_ids)
           :param symbol: Trading pair symbol to filter by
           :param order_ids: List of specific order IDs to cancel
        """
        raise NotImplementedError

    def get_open_orders(self, symbol=None, instType=None, onlyOrderId=True, keep_origin=True):
        """Get open orders
           :param symbol: Trading pair symbol (optional)
           :param instType: Instrument type (e.g., 'PERP', 'SWAP', 'SPOT')
           :param onlyOrderId: Return only order IDs if True
           :param keep_origin: Return original format if True
        """
        raise NotImplementedError

    def get_order_status(self, order_id, symbol=None, keep_origin=True):
        """Get order status
           :param order_id: Order ID to query
           :param symbol: Trading pair symbol (optional)
           :param keep_origin: Return original format if True
        """
        raise NotImplementedError

    # ---- Account ----
    def fetch_balance(self, currency, window=None):
        """Return balance information
           :param currency: Currency to fetch balance for (e.g., 'USDT', 'USDC', 'ALL')
           :param window: Time window for balance query (optional)
        """
        raise NotImplementedError

    def get_position(self, symbol=None, keep_origin=True, instType=None, window=None):
        """Return current positions
           :param symbol: Trading pair symbol (optional, None for all positions)
           :param keep_origin: Return original format if True
           :param instType: Instrument type (e.g., 'PERP', 'SWAP', 'SPOT')
           :param window: Time window for position query (optional)
        """
        raise NotImplementedError

    # ---- Convenience methods ----
    def buy(self, symbol, size, price=None, order_type="limit", **kwargs):
        """Convenience method for placing buy orders
           :param symbol: Trading pair symbol
           :param size: Order quantity
           :param price: Order price (required for limit orders)
           :param order_type: 'limit' or 'market'
           :param kwargs: Additional parameters
        """
        return self.place_order(symbol, "buy", order_type, size, price, **kwargs)

    def sell(self, symbol, size, price=None, order_type="limit", **kwargs):
        """Convenience method for placing sell orders
           :param symbol: Trading pair symbol
           :param size: Order quantity
           :param price: Order price (required for limit orders)
           :param order_type: 'limit' or 'market'
           :param kwargs: Additional parameters
        """
        return self.place_order(symbol, "sell", order_type, size, price, **kwargs)

    # ---- Position management ----
    def close_all_positions(self, mode="market", price_offset=0.0005, symbol=None, side=None, is_good=None):
        """Close all positions with optional filtering
           :param mode: 'market' or 'limit'
           :param price_offset: Price offset for limit orders (relative to mark price)
           :param symbol: Trading pair symbol to filter by (optional)
           :param side: 'long' to close only long positions, 'short' for short, None for all
           :param is_good: True to close only profitable positions, False for losing, None for all
        """
        raise NotImplementedError
