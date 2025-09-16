# -*- coding: utf-8 -*-
# ctos/drivers/okx/driver.py
# OKX-only driver that wraps your existing okex.py client.
# Compatible with older Python (no dataclasses/Protocol).

from __future__ import print_function
import math

try:
    # Import your own client defined in /mnt/data/okex.py (or your project path).
    # Change the name below to match your class or factory if different.
    from .okex import OkexSpot, ACCESS_KEY, SECRET_KEY, PASSPHRASE
except Exception as e:
    print('Error from okex import ')
    OkexSpot = object  # fallback for static analyzers / import-late patterns

# Import syscall base
try:
    # 包内正常导入
    from ctos.core.kernel.syscalls import TradingSyscalls
except ImportError:
    # 单文件执行时，修正 sys.path 再导入
    import os, sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
    from ctos.core.kernel.syscalls import TradingSyscalls

def init_OkxClient(symbol="ETH-USDT-SWAP", account=0, show=False):
    if symbol.find('-') == -1:
        symbol = f'{symbol.upper()}-USDT-SWAP'
    return OkexSpot(symbol=symbol, access_key=ACCESS_KEY, secret_key=SECRET_KEY, passphrase=PASSPHRASE, host=None)

class OkxDriver(TradingSyscalls):
    """
    CTOS OKX driver.
    Adapts methods seen in Strategy.py:
      - get_price_now('btc')
      - get_kline(tf, N, 'BTC-USDT-SWAP') -> returns (df_or_list, ...)
      - revoke_orders(...)
      - get_jiaoyi_asset(), get_zijin_asset(), transfer_money(...)
    """

    def __init__(self, okx_client=None, mode="swap", default_quote="USDT",
                 price_scale=1e-8, size_scale=1e-8):
        """
        :param okx_client: Optional. An initialized client from okex.py (authenticated).
                           If None, will try to instantiate OkexSpot() with defaults.
        :param mode: "swap" or "spot". If "swap", we append '-SWAP' suffix when needed.
        :param default_quote: default quote when user passes 'BTC' without '-USDT'
        """
        if okx_client is None:
            try:
                self.okx = init_OkxClient()
            except Exception as e:
                print(e)
                self.okx = None
        else:
            self.okx = okx_client
        self.mode = (mode or "swap").lower()
        self.default_quote = default_quote or "USDT"
        self.price_scale = price_scale
        self.size_scale = size_scale

    # -------------- helpers --------------
    def _norm_symbol(self, symbol):
        """
        Accepts 'BTC-USDT', 'BTC/USDT', 'btc', 'BTC-USDT-SWAP'.
        Returns full OKX symbol string (e.g. 'BTC-USDT-SWAP' when in swap mode)
        plus tuple (base, quote).
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
        if self.mode == "swap" and not full.endswith("-SWAP"):
            full = full + "-SWAP"
        return full, base.lower(), quote.upper()

    # -------------- ref-data / meta --------------
    def symbols(self):
        # Provide a tiny default. Replace with a real call if your okex.py exposes one.
        return ["BTC-USDT", "ETH-USDT", "SOL-USDT"]

    def exchange_limits(self):
        return {"price_scale": self.price_scale, "size_scale": self.size_scale}

    def fees(self, symbol='ETH-USDT-SWAP', instType='SPOT'):
        # If your okex client exposes real fees, put them here.
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.okx, "get_fee"):
            raise NotImplementedError("okex.py client lacks get_fee(symbol, instType)")
        raw, err = self.okx.get_fee(full, instType)
        if not err:
            return raw, err
        else:
            return None, err

    # -------------- market data --------------
    def get_price_now(self, symbol='ETH-USDT-SWAP'):
        full, base, _ = self._norm_symbol(symbol)
        print(full, base)
        # Strategy shows: okx.get_price_now('btc')
        if hasattr(self.okx, "get_price_now"):
            return float(self.okx.get_price_now(full))
        # Fallback: try full symbol if your client expects it
        if hasattr(self.okx, "get_price"):
            return float(self.okx.get_price(full))
        raise NotImplementedError("okex.py client needs get_price_now(base) or get_price(symbol)")

    def get_orderbook(self, symbol='ETH-USDT-SWAP', level=50):
        full, _, _ = self._norm_symbol(symbol)
        if hasattr(self.okx, "get_orderbook"):
            raw = self.okx.get_orderbook(full, int(level))
            bids = raw.get("bids", []) if isinstance(raw, dict) else []
            asks = raw.get("asks", []) if isinstance(raw, dict) else []
            return {"symbol": full, "bids": bids, "asks": asks}
        raise NotImplementedError("okex.py client lacks get_orderbook(symbol, level)")

    def get_klines(self, symbol='ETH-USDT-SWAP', timeframe='1h', limit=200):
        """
        Normalize to list of dicts:
        [{'ts': ts_ms, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v}, ...]
        """
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.okx, "get_kline"):
            raise NotImplementedError("okex.py client lacks get_kline(tf, limit, symbol)")

        raw, err = self.okx.get_kline(str(timeframe), int(limit), full)
        if not err:
            return raw, err
        else:
            return None, err

    # -------------- trading --------------
    def place_order(self, symbol, side, order_type, size, price=None, client_id=None, **kwargs):
        """
        Normalize inputs to your okex client.
        Expected mapping often is:
          place_order(symbol=..., side='buy'|'sell', type='market'|'limit', size=float, price=float|None, client_oid=...)
        """
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.okx, "place_order"):
            raise NotImplementedError("okex.py client lacks place_order(...)")

        order_id, err = self.okx.place_order(
            symbol=full,
            side=str(side).lower(),
            order_type=str(order_type).lower(),
            quantity=float(size),
            price=price,
            **kwargs
        )
        return order_id, err

    def buy(self, symbol, size, price=None, order_type="limit", **kwargs):
        """
        Convenience wrapper for placing a buy order.
        :param symbol: e.g. 'ETH-USDT-SWAP' or 'eth'
        :param size: float quantity
        :param price: optional price for limit/post_only; omit for market
        :param order_type: 'limit' | 'market' | 'post_only'
        :return: (order_id, err)
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
        Convenience wrapper for placing a sell order.
        :param symbol: e.g. 'ETH-USDT-SWAP' or 'eth'
        :param size: float quantity
        :param price: optional price for limit/post_only; omit for market
        :param order_type: 'limit' | 'market' | 'post_only'
        :return: (order_id, err)
        """
        return self.place_order(
            symbol=symbol,
            side="sell",
            order_type=str(order_type).lower(),
            size=float(size),
            price=price,
            **kwargs,
        )


    def amend_order(self, orderId, **kwargs):
        # Map to amend/modify if available
        if hasattr(self.okx, "amend_order"):
            order_id, err = self.okx.amend_order(orderId=orderId, **kwargs)
            return order_id, err
        if hasattr(self.okx, "modify_order"):
            order_id, err  = self.okx.modify_order(orderId=orderId, **kwargs)
            return order_id, err
        raise NotImplementedError("okex.py client lacks amend_order/modify_order")

    def revoke_order(self, order_id):
        if hasattr(self.okx, "revoke_order"):
            success, error = self.okx.revoke_order(order_id=order_id)
            return success, error
        raise NotImplementedError("okex.py client lacks cancel_order(order_id=...)")

    def get_order_status(self, order_id):
        if hasattr(self.okx, "get_order_status"):
            success, error = self.okx.get_order_status(order_id=order_id)
            return success, error
        raise NotImplementedError("okex.py client lacks cancel_order(order_id=...)")

    def get_open_orders(self, instType='SWAP', symbol='ETH-USDT-SWAP'):
        if hasattr(self.okx, "get_open_orders"):
            success, error = self.okx.get_open_orders(instType=instType, symbol=symbol)
            return success, error
        raise NotImplementedError("okex.py client lacks cancel_order(order_id=...)")

    def cancel_all(self, symbol='ETH-USDT-SWAP'):
        # Strategy.py shows revoke_orders(...)
        if hasattr(self.okx, "revoke_orders"):
            if symbol:
                full, _, _ = self._norm_symbol(symbol)
                resp = self.okx.revoke_orders(symbol=full)
            else:
                resp = self.okx.revoke_orders()
            return {"ok": True, "raw": resp}

        if hasattr(self.okx, "cancel_all"):
            if symbol:
                full, _, _ = self._norm_symbol(symbol)
                resp = self.okx.cancel_all(symbol=full)
            else:
                resp = self.okx.cancel_all()
            return {"ok": True, "raw": resp}

        raise NotImplementedError("okex.py client lacks revoke_orders/cancel_all")

    # -------------- account --------------
    def fetch_balance(self, currency='USDT'):
        """
        Return a simple flat dict. If only jiaoyi/zijin are available,
        expose USDT buckets and a best-effort total in USD.
        """
        # Preferred: if client has get_balances() that returns iterable of dicts
        if hasattr(self.okx, "fetch_balance"):
            try:
                raw = self.okx.fetch_balance(currency)
                return raw
            except Exception as e:
                return e
        raise NotImplementedError("okex.py client lacks fetch_balance")

    def get_position(self, symbol=None):
        if hasattr(self.okx, "get_position"):
            try:
                result = self.okx.get_position(symbol)
                return result
            except Exception:
                return None
        raise NotImplementedError("okex.py client lacks get_position")

