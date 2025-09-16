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

    def get_klines(self, symbol, timeframe, limit=200):
        """Return list of dict rows:
           [{'ts': 1710000000000, 'open':1.0,'high':2.0,'low':0.9,'close':1.5,'volume':123.45}, ...]"""
        raise NotImplementedError

    # ---- Trading ----
    def place_order(self, symbol, side, ord_type, size, price=None, client_id=None, **kwargs):
        """Place order, return dict with at least {'order_id': ..., 'client_id': ..., 'status': ..., 'raw': ...}"""
        raise NotImplementedError

    def amend_order(self, order_id, **kwargs):
        """Amend/modify order"""
        raise NotImplementedError

    def revoke_order(self, order_id):
        """Cancel a single order"""
        raise NotImplementedError

    def cancel_all(self, symbol=None):
        """Cancel all (optionally filtered by symbol)"""
        raise NotImplementedError

    def get_open_orders(self, symbols):
        """Return dict: {'symbol': 'order_id', ……}"""
        raise NotImplementedError

    def get_order_status(self, order_id):
        """Return dict: order_info"""
        raise NotImplementedError

    # ---- Account ----
    def fetch_balance(self, currency):
        """Return dict like {'USDT': 123.45, 'BTC': 0.01, 'total_equity_usd': 123.45} (keys optional except totals)"""
        raise NotImplementedError

    def get_position(self, symbol):
        """Return dict of current positions (shape up to driver)"""
        raise NotImplementedError
