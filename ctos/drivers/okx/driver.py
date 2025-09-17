# -*- coding: utf-8 -*-
# ctos/drivers/okx/driver.py
# OKX-only driver that wraps your existing okex.py client.
# Compatible with older Python (no dataclasses/Protocol).

from __future__ import print_function
import math
import os

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
    # ACCESS_KEY = ACCESS_KEY if not os.getenv("OKX_PUBLIC_KEY") else ACCESS_KEY
    # SECRET_KEY = SECRET_KEY if not os.getenv("OKX_SECRET_KEY") else SECRET_KEY
    # PASSPHRASE = PASSPHRASE if not os.getenv("OKX_PASSPHRASE") else PASSPHRASE

    missing = []
    if not ACCESS_KEY:
        missing.append("OKX_ACCESS_KEY")
    if not SECRET_KEY:
        missing.append("OKX_SECRET_KEY")
    if not PASSPHRASE:
        missing.append("OKX_PASSPHRASE")
    if missing:
        print("[OKX] Missing environment vars:", ", ".join(missing))
        print("[OKX] 建议: 运行 scripts/config_env.py 配置，或手动在 .env 中添加上述键并加载。")
        print("[OKX] Hint: run scripts/config_env.py to set them, or add to .env and source it.")
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
        self.cex = 'OKX'
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
    def symbols(self, instType='SWAP'):
        """
        返回指定类型的交易对列表。
        :param instType: 'SWAP' | 'SPOT' | 'MARGIN' 等，默认 'SWAP'
        :return: list[str]，如 ['BTC-USDT-SWAP', 'ETH-USDT-SWAP', ...]
        """
        if not hasattr(self.okx, 'get_market'):
            # 兜底：无法从底层获取时，返回少量默认
            return ["BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP"] if str(instType).upper() == 'SWAP' else ["BTC-USDT", "ETH-USDT", "SOL-USDT"]

        try:
            condition = str(instType).upper() if instType else None
            data, err = self.okx.get_market(instId='', all=True, condition=condition)
            if err:
                # 出错时返回空列表
                return [], err
            # 提取并去重
            symbols = []
            seen = set()
            for item in data or []:
                inst_id = item.get('instId') if isinstance(item, dict) else None
                if not inst_id:
                    continue
                if condition and condition not in inst_id:
                    continue
                if inst_id not in seen:
                    seen.add(inst_id)
                    symbols.append(inst_id)
            return symbols, None
        except Exception as e:
            return [], e

    def exchange_limits(self):
        return {"price_scale": self.price_scale, "size_scale": self.size_scale}

    def fees(self, symbol='ETH-USDT-SWAP', instType='SWAP', keep_origin=False):
        """
        统一资金费率返回结构，标准化为“每小时资金费率”。
        返回:
          ({
             'symbol': str,
             'instType': str,
             'fundingRate_hourly': float,   # 每小时
             'fundingRate_period': float,   # 原始周期费率
             'period_hours': float,         # 原始周期长度(小时)
             'fundingTime': int,            # 当前结算或下一次结算时间戳(ms)，按OKX
             'raw': Any
          }, None) 或 (None, err)
        """
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.okx, "get_funding_rate"):
            raise NotImplementedError("okex.py client lacks get_funding_rate(symbol, instType)")

        raw, err = self.okx.get_funding_rate(full, instType)
        if keep_origin:
            return raw, err
        if err:
            return None, err

        try:
            # OKX 风格 raw: {'code': '0', 'data': [{ 'instId', 'instType', 'fundingRate', 'fundingTime', 'nextFundingRate', 'nextFundingTime', ... }], 'msg': ''}
            data_list = None
            if isinstance(raw, dict):
                data_list = raw.get('data')
            if isinstance(data_list, list) and data_list:
                d0 = data_list[0]
                fr_period = float(d0.get('fundingRate')) if d0.get('fundingRate') not in (None, '') else 0.0

                # 推断周期：使用 nextFundingTime - fundingTime，若不可用，OKX 永续通常8小时一结
                ts = d0.get('fundingTime') or d0.get('ts')
                nts = d0.get('nextFundingTime')
                if ts is not None and nts is not None:
                    period_hours = max(1.0, (float(nts) - float(ts)) / 1000.0 / 3600.0)
                else:
                    period_hours = 8.0

                hourly = fr_period / period_hours if period_hours else fr_period
                result = {
                    'symbol': d0.get('instId', full),
                    'instType': d0.get('instType', instType),
                    'fundingRate_hourly': hourly,
                    'fundingRate_period': fr_period,
                    'period_hours': period_hours,
                    'fundingTime': int(d0.get('fundingTime') or d0.get('ts') or 0),
                    'raw': raw,
                }
                return result, None

            # 回退：原样返回
            return {'symbol': full, 'instType': instType, 'fundingRate_hourly': None, 'fundingRate_period': None, 'period_hours': None, 'fundingTime': None, 'raw': raw}, None
        except Exception as e:
            return None, e

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

    def get_order_status(self, order_id, keep_origin=True):
        if hasattr(self.okx, "get_order_status"):
            success, error = self.okx.get_order_status(order_id=order_id)
            if keep_origin:
                return success, error

            if error:
                return None, error

            od = None
            if isinstance(success, dict):
                # OKX 返回 {'code': '0', 'data': [ {...order...} ], 'msg': ''}
                data_list = success.get('data')
                if isinstance(data_list, list) and data_list:
                    od = data_list[0]
                else:
                    # 兜底：若直接就是订单对象
                    od = success
            if not isinstance(od, dict):
                return None, None

            def _val(k):
                v = od.get(k)
                return v

            def _float(v):
                try:
                    return float(v)
                except Exception:
                    return None

            normalized = {
                'orderId': _val('ordId'),
                'symbol': _val('instId'),
                'side': (str(_val('side')).lower() if _val('side') is not None else None),
                'orderType': (str(_val('ordType')).lower() if _val('ordType') is not None else None),
                'price': _float(_val('px')),
                'quantity': _float(_val('sz')),
                'filledQuantity': _float(_val('accFillSz') or _val('fillSz') or 0.0),
                'status': _val('state'),
                'timeInForce': _val('timeInForce') or _val('tif'),
                'postOnly': _val('postOnly'),
                'reduceOnly': _val('reduceOnly'),
                'clientId': _val('clOrdId'),
                'createdAt': int(_val('cTime') or 0) if _val('cTime') else None,
                'updatedAt': int(_val('uTime') or 0) if _val('uTime') else None,
                'raw': od,
            }
            return normalized, None
        raise NotImplementedError("okex.py client lacks cancel_order(order_id=...)")

    def get_open_orders(self, symbol='ETH-USDT-SWAP', instType='SWAP', onlyOrderId=True, keep_origin=True):
        if hasattr(self.okx, "get_open_orders"):
            success, error = self.okx.get_open_orders(instType=instType, symbol=symbol, onlyOrderId=onlyOrderId)
            if onlyOrderId or keep_origin:
                return success, error

            if error:
                return None, error

            # success 应为 list[dict]
            orders = success or []
            normalized = []
            for od in orders:
                if not isinstance(od, dict):
                    continue
                def _f(key, default=None):
                    v = od.get(key)
                    return v if v is not None else default
                # 解析字段
                order_id = _f('ordId')
                sym = _f('instId')
                side = str(_f('side', '')).lower() or None
                order_type = str(_f('ordType', '')).lower() or None
                try:
                    price = float(_f('px')) if _f('px') not in (None, '') else None
                except Exception:
                    price = None
                try:
                    qty = float(_f('sz')) if _f('sz') not in (None, '') else None
                except Exception:
                    qty = None
                # 成交数量：优先 accFillSz，其次 fillSz
                try:
                    filled = float(_f('accFillSz') or _f('fillSz') or 0.0)
                except Exception:
                    filled = None
                status = _f('state')
                tif = _f('timeInForce') or _f('tif')  # OKX无明确字段时留空
                post_only = _f('postOnly')
                reduce_only = _f('reduceOnly')
                client_id = _f('clOrdId')
                try:
                    created_at = int(_f('cTime') or 0)
                except Exception:
                    created_at = None
                try:
                    updated_at = int(_f('uTime') or 0)
                except Exception:
                    updated_at = None

                normalized.append({
                    'orderId': order_id,
                    'symbol': sym,
                    'side': side,
                    'orderType': order_type,
                    'price': price,
                    'quantity': qty,
                    'filledQuantity': filled,
                    'status': status,
                    'timeInForce': tif,
                    'postOnly': post_only,
                    'reduceOnly': reduce_only,
                    'clientId': client_id,
                    'createdAt': created_at,
                    'updatedAt': updated_at,
                    'raw': od,
                })
            return normalized, None
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

    def get_position(self, symbol=None, keep_origin=True, instType='SWAP'):
        if hasattr(self.okx, "get_position"):
            try:
                success, error = self.okx.get_position(symbol, instType=instType)
                if keep_origin:
                    return success, error

                if error:
                    return None, error

                # 统一结构：list[{
                #   symbol, positionId, side, quantity, entryPrice, markPrice,
                #   pnlUnrealized, pnlRealized, leverage, liquidationPrice, ts
                # }]
                unified = []
                data = None
                if isinstance(success, dict):
                    data = success.get('data')
                if isinstance(data, list):
                    for d in data:
                        try:
                            qty = float(d.get('pos') or 0.0)
                        except Exception:
                            qty = 0.0
                        side = 'long' if qty > 0 else ('short' if qty < 0 else 'flat')
                        try:
                            entry = float(d.get('avgPx') or d.get('nonSettleAvgPx') or 0.0)
                        except Exception:
                            entry = None
                        try:
                            mark = float(d.get('markPx') or d.get('last') or 0.0)
                        except Exception:
                            mark = None
                        try:
                            upl = float(d.get('upl') or 0.0)
                        except Exception:
                            upl = None
                        try:
                            realized = float(d.get('realizedPnl') or d.get('settledPnl') or 0.0)
                        except Exception:
                            realized = None
                        try:
                            lev = float(d.get('lever') or 0.0)
                        except Exception:
                            lev = None
                        try:
                            liq = float(d.get('liqPx') or 0.0) if d.get('liqPx') not in (None, '') else None
                        except Exception:
                            liq = None
                        try:
                            ts = int(d.get('uTime') or d.get('cTime') or 0)
                        except Exception:
                            ts = None
                        try:
                            fee = float(d.get('fundingFee') or d.get('fundingFee') or 0)
                        except Exception:
                            ts = None
                        unified.append({
                            'symbol': d.get('instId'),
                            'positionId': d.get('posId'),
                            'side': side,
                            'quantity': abs(qty),
                            'entryPrice': entry,
                            'markPrice': mark,
                            'pnlUnrealized': upl,
                            'pnlRealized': realized,
                            'leverage': lev,
                            'liquidationPrice': liq,
                            'ts': ts,
                            'fee': fee,
                        })

                if symbol and isinstance(unified, list):
                    # 筛选单个 symbol
                    for u in unified:
                        if str(u.get('symbol')).upper() == str(symbol).upper():
                            return u, None
                return unified, None
            except Exception as e:
                return None, e
        raise NotImplementedError("okex.py client lacks get_position")

    def close_all_positions(self, mode="market", price_offset=0.0005, symbol=None, side=None, is_good=None):
        """
        平掉所有仓位，可附加过滤条件（OKX 版）

        :param mode: "market" 或 "limit"
        :param price_offset: limit 平仓时的价格偏移系数（相对 markPx）
        :param symbol: 仅平某个币种 (e.g. "ETH-USDT-SWAP")
        :param side: "long" 仅平多仓, "short" 仅平空仓, None 表示不限
        :param is_good: True 仅平盈利仓, False 仅平亏损仓, None 表示不限
        """
        # 获取原始仓位数据
        pos_raw, err = self.get_position(symbol=symbol, keep_origin=True)
        if err:
            print("[OKX] get_position error:", err)
            return

        # 解析列表
        rows = None
        if isinstance(pos_raw, dict):
            rows = pos_raw.get('data')
        if not isinstance(rows, list):
            rows = []

        if not rows:
            print("✅ 当前无持仓")
            return

        # 归一化 symbol 用于比较
        full_sym = None
        if symbol:
            full_sym, _, _ = self._norm_symbol(symbol)

        for pos in rows:
            try:
                sym = pos.get('instId')
                qty = float(pos.get('pos') or 0.0)
                mark_price = float(pos.get('markPx') or pos.get('last') or 0.0)
                pnl_unreal = float(pos.get('upl') or 0.0)
            except Exception:
                continue

            if qty == 0:
                continue  # 跳过空仓

            # 过滤 symbol
            if full_sym and sym != full_sym:
                continue

            # 判断仓位方向
            pos_side = "long" if qty > 0 else "short"

            # 过滤 side
            if side and side != pos_side:
                continue

            # 过滤 盈亏
            if is_good is True and pnl_unreal <= 0:
                continue
            if is_good is False and pnl_unreal > 0:
                continue

            # 构造平仓单（OKX 下：多仓 -> 卖出，空仓 -> 买入）
            if qty > 0:
                order_side = "sell"
                size = abs(qty)
            else:
                order_side = "buy"
                size = abs(qty)

            if mode == "market":
                try:
                    self.place_order(symbol=sym, side=order_side, order_type="market", size=size)
                    print(f"📤 市价平仓: {sym} {order_side} {size}")
                except Exception as e:
                    print(f"[OKX] 市价平仓失败 {sym}: {e}")
            elif mode == "limit":
                try:
                    if order_side == "sell":
                        price = mark_price * (1 + price_offset)
                    else:
                        price = mark_price * (1 - price_offset)
                    self.place_order(symbol=sym, side=order_side, order_type="limit", size=size, price=price)
                    print(f"📤 限价平仓: {sym} {order_side} {size} @ {price}")
                except Exception as e:
                    print(f"[OKX] 限价平仓失败 {sym}: {e}")
            else:
                raise ValueError("mode 必须是 'market' 或 'limit'")

    