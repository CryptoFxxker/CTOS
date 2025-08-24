# -*- coding: utf-8 -*-
# ctos/drivers/okx/driver.py
# OKX-only driver that wraps your existing okex.py client.
# Compatible with older Python (no dataclasses/Protocol).

from __future__ import print_function
import math

try:
    # Import your own client defined in /mnt/data/okex.py (or your project path).
    # Change the name below to match your class or factory if different.
    from okex import OkexSpot
except Exception:
    OkexSpot = object  # fallback for static analyzers / import-late patterns

# Import syscall base
from ctos.core.kernel.syscalls import TradingSyscalls


class OkxDriver(TradingSyscalls):
    """
    CTOS OKX driver.
    Adapts methods seen in Strategy.py:
      - get_price_now('btc')
      - get_kline(tf, N, 'BTC-USDT-SWAP') -> returns (df_or_list, ...)
      - revoke_orders(...)
      - get_jiaoyi_asset(), get_zijin_asset(), transfer_money(...)
    """

    def __init__(self, okx_client, mode="swap", default_quote="USDT",
                 price_scale=1e-8, size_scale=1e-8):
        """
        :param okx_client: An initialized client from okex.py (authenticated).
        :param mode: "swap" or "spot". If "swap", we append '-SWAP' suffix when needed.
        :param default_quote: default quote when user passes 'BTC' without '-USDT'
        """
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

    def fees(self):
        # If your okex client exposes real fees, put them here.
        return {"maker": None, "taker": None}

    # -------------- market data --------------
    def get_price_now(self, symbol):
        full, base, _ = self._norm_symbol(symbol)
        # Strategy shows: okx.get_price_now('btc')
        if hasattr(self.okx, "get_price_now"):
            return float(self.okx.get_price_now(base))
        # Fallback: try full symbol if your client expects it
        if hasattr(self.okx, "get_price"):
            return float(self.okx.get_price(full))
        raise NotImplementedError("okex.py client needs get_price_now(base) or get_price(symbol)")

    def get_orderbook(self, symbol, level=50):
        full, _, _ = self._norm_symbol(symbol)
        if hasattr(self.okx, "get_orderbook"):
            raw = self.okx.get_orderbook(full, int(level))
            bids = raw.get("bids", []) if isinstance(raw, dict) else []
            asks = raw.get("asks", []) if isinstance(raw, dict) else []
            return {"symbol": full, "bids": bids, "asks": asks}
        raise NotImplementedError("okex.py client lacks get_orderbook(symbol, level)")

    def get_klines(self, symbol, timeframe, limit=200):
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
    def place_order(self, symbol, side, ord_type, size, price=None, client_id=None, **kwargs):
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
            type=str(ord_type).lower(),
            size=float(size),
            price=price,
            **kwargs
        )
        return order_id, err

    def amend_order(self, order_id, **kwargs):
        # Map to amend/modify if available
        if hasattr(self.okx, "amend_order"):
            order_id, err = self.okx.amend_order(order_id=order_id, **kwargs)
            return order_id, err
        if hasattr(self.okx, "modify_order"):
            order_id, err  = self.okx.modify_order(order_id=order_id, **kwargs)
            return order_id, err
        raise NotImplementedError("okex.py client lacks amend_order/modify_order")

    def revoke_order(self, order_id):
        if hasattr(self.okx, "revoke_order"):
            success, error = self.okx.cancel_order(order_id=order_id)
            return success, error
        raise NotImplementedError("okex.py client lacks cancel_order(order_id=...)")

    def get_order_status(self, order_id):
        if hasattr(self.okx, "get_order_status"):
            success, error = self.okx.cancel_order(order_id=order_id)
            return success, error
        raise NotImplementedError("okex.py client lacks cancel_order(order_id=...)")

    def get_open_orders(self, instType='SWAP', symbol='ETH-USDT-SWAP'):
        if hasattr(self.okx, "get_open_orders"):
            success, error = self.okx.get_open_orders(instType=instType, symbol=symbol)
            return success, error
        raise NotImplementedError("okex.py client lacks cancel_order(order_id=...)")

    def cancel_all(self, symbol=None):
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
    def balances(self):
        """
        Return a simple flat dict. If only jiaoyi/zijin are available,
        expose USDT buckets and a best-effort total in USD.
        """
        # Preferred: if client has get_balances() that returns iterable of dicts
        if hasattr(self.okx, "get_balances"):
            raw = self.okx.get_balances()
            flat = {}
            if isinstance(raw, (list, tuple)):
                for a in raw:
                    ccy = a.get("ccy") or a.get("asset")
                    amt = a.get("availBal") or a.get("free") or a.get("balance")
                    if ccy and amt is not None:
                        flat[str(ccy).upper()] = float(amt)
            # Best-effort equity: favor USDT if present
            total_usdt = 0.0
            if "USDT" in flat:
                total_usdt = float(flat["USDT"])
            # Fill a common key used elsewhere
            flat["total_equity_usd"] = total_usdt
            return flat

        # Fallback: Strategy.py shows get_jiaoyi_asset() and get_zijin_asset()
        total_equity = 0.0
        out = {}
        if hasattr(self.okx, "get_jiaoyi_asset"):
            try:
                j = float(self.okx.get_jiaoyi_asset())
                out["TRADING_USDT"] = j
                total_equity += j
            except Exception:
                pass
        if hasattr(self.okx, "get_zijin_asset"):
            try:
                z = float(self.okx.get_zijin_asset())
                out["FUNDING_USDT"] = z
                total_equity += z
            except Exception:
                pass
        out["total_equity_usd"] = total_equity
        return out

    def positions(self):
        if hasattr(self.okx, "get_positions"):
            try:
                raw = self.okx.get_positions()
                return {"raw": raw}
            except Exception:
                return {"raw": None}
        return {}


# --------- small helpers (no modern features) ---------

def _first_key(d, keys):
    """Return the first present key from list; else None."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d:
            return d[k]
    return None


def _safe_int(row, *keys, **kw):
    default = kw.get("default", 0)
    for k in keys:
        try:
            if hasattr(row, "get"):
                v = row.get(k, None)
            else:
                v = row[k] if k in row else None
            if v is None:
                continue
            return int(v)
        except Exception:
            pass
    return int(default)


def _safe_float(row, key_primary, idx_fallback=None, **kw):
    default = kw.get("default", 0.0)
    # try named column first
    try:
        if hasattr(row, "get"):
            v = row.get(key_primary, None)
        else:
            v = row[key_primary] if key_primary in row else None
        if v is not None:
            return float(v)
    except Exception:
        pass
    # fallback to index (for positional df/series)
    if idx_fallback is not None:
        try:
            return float(row[idx_fallback])
        except Exception:
            pass
    return float(default)
