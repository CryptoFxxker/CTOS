# -*- coding: utf-8 -*-
# ctos/drivers/backpack/driver.py
# Backpack-only driver wrapping bpx Account/Public clients.

from __future__ import print_function

from ast import main
import os
import time
from datetime import datetime, timezone

import sys
import os

# 动态添加bpx包路径到sys.path
def _add_bpx_path():
    """添加bpx包路径到sys.path，支持多种运行方式"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    bpx_path = os.path.join(current_dir, 'bpx')
    
    # 添加当前目录的bpx路径
    if bpx_path not in sys.path:
        sys.path.insert(0, bpx_path)
    
    # 添加项目根目录的bpx路径（如果存在）
    project_root = os.path.abspath(os.path.join(current_dir, '../../..'))
    root_bpx_path = os.path.join(project_root, 'bpx')
    if os.path.exists(root_bpx_path) and root_bpx_path not in sys.path:
        sys.path.insert(0, root_bpx_path)
    if os.path.exists(project_root) and project_root not in sys.path:
        sys.path.insert(0, project_root)

# 执行路径添加
_add_bpx_path()

# Import Backpack clients (robust to different execution contexts)
try:
    # When imported as part of the package
    from .bpx.account import Account  # type: ignore
    from .bpx.public import Public    # type: ignore
except Exception:
    try:
        # When the full package is available in sys.path
        from ctos.drivers.backpack.bpx.account import Account  # type: ignore
        from ctos.drivers.backpack.bpx.public import Public    # type: ignore
    except Exception as e:
        # As a last resort, add the local folder so `bpx` can be found when running this file directly
        backpack_dir = os.path.dirname(__file__)
        if backpack_dir not in sys.path:
            sys.path.append(backpack_dir)
        try:
            from bpx.account import Account  # type: ignore
            from bpx.public import Public    # type: ignore
        except Exception as e2:
            print(f'Error importing bpx clients: {e2}')
            print(f'Current sys.path: {sys.path}...')  # 只显示前3个路径
            sys.exit(1)

# Import syscall base
try:
    from ctos.core.kernel.syscalls import TradingSyscalls
except ImportError:
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
    from ctos.core.kernel.syscalls import TradingSyscalls


def init_BackpackClients(window=10000):
    """
    Initialize Backpack Account and Public clients using env credentials.
    Required envs:
      - BP_PUBLIC_KEY
      - BP_SECRET_KEY
    """
    public_key = os.getenv("BP_PUBLIC_KEY")
    secret_key = os.getenv("BP_SECRET_KEY")
    missing = []
    if not public_key:
        missing.append("BP_PUBLIC_KEY")
    if not secret_key:
        missing.append("BP_SECRET_KEY")
    if missing:
        print("[Backpack] Missing environment vars:", ", ".join(missing))
        print("[Backpack] 建议: 运行 scripts/config_env.py 配置，或手动在 .env 中添加上述键并加载。")
        print("[Backpack] Hint: run scripts/config_env.py to set them, or add to .env and source it.")
    account = None
    public = None
    try:
        account = Account(public_key, secret_key, window=window)
    except Exception as e:
        print('init Account failed:', e)
    try:
        public = Public()
    except Exception as e:
        print('init Public failed:', e)
    return account, public


class BackpackDriver(TradingSyscalls):
    """
    CTOS Backpack driver.
    Mode-aware symbol normalization for Backpack style symbols:
      - spot:  "BASE_QUOTE"           e.g. "SOL_USDC"
      - perp:  "BASE_USDC_PERP"       e.g. "ETH_USDC_PERP"
    Accepts inputs like 'eth-usdc', 'ETH/USDC', 'ETH-USDC-SWAP', 'eth', etc.
    """

    def __init__(self, account_client=None, public_client=None, mode="perp", default_quote="USDC"):
        self.cex = 'Backpack'
        if account_client is None or public_client is None:
            acc, pub = init_BackpackClients()
            self.account = account_client or acc
            self.public = public_client or pub
        else:
            self.account = account_client
            self.public = public_client
        self.mode = (mode or "perp").lower()
        self.default_quote = default_quote or "USDC"
        self.symbol = 'ETH_USDC_PERP'

    # -------------- helpers --------------
    def _norm_symbol(self, symbol):
        """
        Normalize symbols to Backpack format.
        Returns (full_symbol, base_lower, quote_upper)
        Examples:
          _norm_symbol('eth') -> ('ETH_USDC_PERP' if perp else 'ETH_USDC', 'eth', 'USDC')
          _norm_symbol('ETH-USDC-SWAP') -> ('ETH_USDC_PERP', 'eth', 'USDC')
          _norm_symbol('SOL/USDC') -> ('SOL_USDC[_PERP]', 'sol', 'USDC')
          _norm_symbol('BTC_USDC_PERP') -> ('BTC_USDC_PERP', 'btc', 'USDC')
        """
        s = str(symbol or "").strip()
        if not s:
            return None, None, None
            # raise ValueError("symbol is empty")

        # unify separators to underscore and uppercase
        su = s.replace("-", "_").replace("/", "_").upper()

        # Already a full Backpack symbol
        if su.endswith("_PERP") or ("_" in su and not su.endswith("_PERP")):
            parts = su.split("_")
            base = parts[0]
            # try to infer quote when provided
            quote = parts[1] if len(parts) > 1 else self.default_quote
            full = su
        else:
            # Only base provided
            base = su
            quote = self.default_quote
            full = f"{base}_{quote}"

        if self.mode == "perp" and not full.endswith("_PERP"):
            # Backpack perps generally quoted in USDC, enforce quote
            base_only = full.split("_")[0]
            full = f"{base_only}_{self.default_quote}_PERP"
        elif self.mode != "perp" and full.endswith("_PERP"):
            # If spot mode but input is perp, strip suffix
            full = full.replace("_PERP", "")

        return full, base.lower(), quote.upper()

    def _timeframe_to_seconds(self, timeframe):
        """Parse timeframe like '1m','15m','1h','4h','1d','1w' -> seconds"""
        tf = str(timeframe).strip().lower()
        if tf.endswith('m'):
            return int(tf[:-1]) * 60
        if tf.endswith('h'):
            return int(tf[:-1]) * 60 * 60
        if tf.endswith('d'):
            return int(tf[:-1]) * 24 * 60 * 60
        if tf.endswith('w'):
            return int(tf[:-1]) * 7 * 24 * 60 * 60
        # default try minutes
        try:
            return int(tf) * 60
        except Exception:
            raise ValueError("Unsupported timeframe: %s" % timeframe)

    # -------------- ref-data / meta --------------
    def symbols(self, instType='PERP'):
        """
        返回 (symbols, error)
        - 成功: (list[str], None)
        - 失败: (None, Exception)
        根据 self.mode 过滤：perp 仅返回 *_PERP，其它仅返回非 *_PERP。
        """
        if not hasattr(self, "public") or self.public is None:
            return None, NotImplementedError("Public client not initialized")
        try:
            markets_response = self.public.get_markets()
            if isinstance(markets_response, dict) and 'data' in markets_response:
                markets = markets_response['data']
            elif isinstance(markets_response, list):
                markets = markets_response
            else:
                return None, ValueError("Unexpected markets response format")

            raw_symbols = []
            for m in markets:
                if isinstance(m, dict):
                    sym = m.get('symbol')
                    if sym:
                        raw_symbols.append(sym)

            symbols = [s for s in raw_symbols if str(s).upper().endswith(instType.upper())]
    
            return symbols, None
        except Exception as e:
            return None, e

    def exchange_limits(self):
        # Unknown from Backpack; return empty or basic defaults
        return {}

    def fees(self, symbol='ETH_USDC_PERP', instType='PERP', keep_origin=False, limit=3, offset=0):
        """
        获取资金费率信息。
        - 对于 Backpack，使用 Public.get_funding_interval_rates(symbol, limit, offset)
        - 返回 (result, error)
        - 统一返回结构到“每小时资金费率”。
        """
        if not hasattr(self.public, 'get_funding_interval_rates'):
            raise NotImplementedError('Public.get_funding_interval_rates unavailable')

        full, _, _ = self._norm_symbol(symbol)
        try:
            raw, err = self.public.get_funding_interval_rates(full, int(limit), int(offset))
            if keep_origin:
                return raw, err
            # 标准化输出，尽量提供 latest，并统一为每小时资金费率
            latest = None
            rows = None
            if isinstance(raw, dict) and 'data' in raw:
                rows = raw.get('data') or []
            elif isinstance(raw, list):
                rows = raw
            rows = rows or []

            if rows:
                latest = rows[-1]
            
            # Backpack 单条字段示例: {'fundingRate': '0.0000125', 'intervalEndTimestamp': '2025-09-16T16:00:00', 'symbol': 'ETH_USDC_PERP'}
            fr_period = None
            period_hours = None
            ts_ms = None
            try:
                if latest and isinstance(latest, dict):
                    fr_period = float(latest.get('fundingRate')) if latest.get('fundingRate') not in (None, '') else None
                    # Backpack 返回的是按区间（通常1小时）结算的费率，时间在 intervalEndTimestamp
                    tstr = latest.get('intervalEndTimestamp')
                    if tstr:
                        try:
                            dt = datetime.strptime(str(tstr), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
                            ts_ms = int(dt.timestamp() * 1000)
                        except Exception:
                            ts_ms = None
                    # 默认按1小时区间
                    period_hours = 1.0
            except Exception:
                pass

            hourly = None
            if fr_period is not None:
                hourly = fr_period / (period_hours or 1.0)

            result = {
                'symbol': full,
                'instType': instType,
                'fundingRate_hourly': hourly,
                'fundingRate_period': fr_period,
                'period_hours': period_hours,
                'fundingTime': ts_ms,
                'raw': raw,
                'latest': latest,
            }
            return result, None
        except Exception as e:
            return None, e

    # -------------- market data --------------
    def get_price_now(self, symbol='ETH_USDC_PERP'):
        full, base, _ = self._norm_symbol(symbol)
        if hasattr(self.public, "get_ticker"):
            try:
                data = self.public.get_ticker(full)
                # Expected shape: { 'lastPrice': '123.45', ... }
                if isinstance(data, dict):
                    price = data.get('lastPrice') or data.get('last') or data.get('price')
                    if price is not None:
                        return float(price)
            except Exception as e:
                raise e
        raise NotImplementedError("Public.get_ticker unavailable or response lacks lastPrice")

    def get_orderbook(self, symbol='ETH_USDC_PERP', level=50):
        full, _, _ = self._norm_symbol(symbol)
        if hasattr(self.public, "get_depth"):
            raw = self.public.get_depth(full)
            bids = raw.get("bids", []) if isinstance(raw, dict) else []
            asks = raw.get("asks", []) if isinstance(raw, dict) else []
            return {"symbol": full, "bids": bids, "asks": asks}
        raise NotImplementedError("Public.get_depth unavailable")

    def get_klines(self, symbol='ETH_USDC', timeframe='1m', limit=200, start_time=None, end_time=None):
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.public, "get_klines"):
            raise NotImplementedError("Public.get_klines unavailable")

        # 计算缺省时间范围：对齐到周期边界，起点=对齐后的边界-(limit-1)*tf，终点=当前时间
        try:
            tf_seconds = self._timeframe_to_seconds(timeframe)
        except Exception as e:
            return None, e

        now_sec = int(time.time())
        if end_time is None:
            end_time = now_sec
        if start_time is None:
            aligned_end_boundary = end_time - (end_time % tf_seconds)
            start_time = aligned_end_boundary - (int(limit) - 1) * tf_seconds

        # 拉取原始数据
        try:
            raw = self.public.get_klines(full, str(timeframe), int(start_time), int(end_time))
        except Exception as e:
            return None, e

        # 统一为列表
        if isinstance(raw, dict) and 'data' in raw:
            rows = raw.get('data') or []
        elif isinstance(raw, list):
            rows = raw
        else:
            return None, ValueError("Unexpected klines response format")

        # 重排为目标DF格式: trade_date(ms), open, high, low, close, vol1(base), vol(quote)
        records = []
        for k in rows:
            if not isinstance(k, dict):
                continue
            try:
                # 解析开始时间为毫秒时间戳
                start_str = k.get('start')
                if isinstance(start_str, (int, float)):
                    ts_ms = int(start_str)
                else:
                    # start 例如 '2025-09-15 08:14:00'，按UTC处理
                    dt = datetime.strptime(str(start_str), '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                    ts_ms = int(dt.timestamp() * 1000)

                o = float(k.get('open'))
                h = float(k.get('high'))
                l = float(k.get('low'))
                c = float(k.get('close'))
                base_vol = float(k.get('volume') or 0.0)
                quote_vol = float(k.get('quoteVolume') or 0.0)

                records.append({
                    'trade_date': ts_ms,
                    'open': o,
                    'high': h,
                    'low': l,
                    'close': c,
                    'vol1': base_vol,
                    'vol': quote_vol,
                })
            except Exception:
                # 跳过坏行
                continue

        # 时间升序并裁剪到 limit
        records.sort(key=lambda r: r['trade_date'])
        if limit and len(records) > int(limit):
            records = records[-int(limit):]

        # 优先返回 pandas.DataFrame
        try:
            import pandas as pd  # type: ignore
            df = pd.DataFrame.from_records(records, columns=['trade_date', 'open', 'high', 'low', 'close', 'vol1', 'vol'])
            return df, None
        except Exception:
            # 退化为列表
            return records, None

    # -------------- trading --------------
    def place_order(self, symbol, side, order_type, size, price=None, client_id=None, **kwargs):
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.account, "execute_order"):
            raise NotImplementedError("Account.execute_order unavailable")

        # Map CTOS -> Backpack enum
        bp_side = "Bid" if str(side).lower() in ("buy", "bid", "long") else "Ask"
        bp_type = "Limit" if str(order_type).lower() in ("limit",) else "Market"
        params = {
            "symbol": full,
            "side": bp_side,
            "order_type": bp_type,
            "quantity": str(size),
            "time_in_force": kwargs.pop("time_in_force", "GTC"),
        }
        if price is not None:
            params["price"] = str(price)
        # passthrough extras like post_only
        params.update(kwargs)

        order = self.account.execute_order(**params)
        # Unify return to (order_id or order, error)
        if isinstance(order, dict) and 'id' in order:
            return order.get('id'), None
        return order, None

    def amend_order(self, order_id, symbol, price=None, size=None, side=None, order_type=None,
                    time_in_force=None, post_only=None, **kwargs):
        """
        通过 查单->撤单->下单 组合实现改单。
        - symbol 必填（撤单需要）
        - 未提供的新参数将继承原订单（side/type/price/size/time_in_force/post_only）
        - 支持只改价、只改量、同时修改、以及更改 tif/post_only

        返回: (new_order_id_or_obj, error)
        """
        if not order_id:
            return None, ValueError("order_id is required")
        if not symbol:
            return None, ValueError("symbol is required")

        full, _, _ = self._norm_symbol(symbol)

        # 1) 查单
        existing_order = None
        try:
            od, oerr = self.get_order_status(order_id=order_id, symbol=full)
            if oerr is None and od:
                existing_order = od
        except Exception:
            existing_order = None
        # 2) 撤单
        ok, cerr = self.revoke_order(order_id, symbol=full)
        if not ok:
            return None, cerr or RuntimeError("cancel order failed")

        # 3) 组装新单参数：优先用传入，其次用旧单
        def _get(o, keys, default=None):
            if not isinstance(o, dict):
                return default
            for k in keys:
                v = o.get(k)
                if v is not None:
                    return v
            return default

        old_side = _get(existing_order, ['side', 'orderSide'])
        old_type = _get(existing_order, ['type', 'orderType'])
        old_qty = _get(existing_order, ['quantity', 'size', 'qty'])
        old_price = _get(existing_order, ['price'])
        old_tif = _get(existing_order, ['timeInForce', 'time_in_force']) or 'GTC'
        old_post_only = _get(existing_order, ['postOnly', 'post_only'])

        new_side = side if side is not None else old_side
        new_type = order_type if order_type is not None else old_type
        new_qty = size if size is not None else old_qty
        new_price = price if price is not None else old_price
        new_tif = time_in_force if time_in_force is not None else old_tif
        new_post_only = post_only if post_only is not None else old_post_only

        if not new_side:
            return None, ValueError("side not provided and cannot infer from existing order")
        if not new_type:
            new_type = 'Limit' if new_price is not None else 'Market'
        if not new_qty:
            return None, ValueError("size not provided and cannot infer from existing order")

        place_kwargs = {}
        if new_post_only is not None:
            place_kwargs['post_only'] = bool(new_post_only)
        if new_tif is not None:
            place_kwargs['time_in_force'] = new_tif

        return self.place_order(
            full,
            side=new_side,
            order_type=new_type,
            size=str(new_qty),
            price=str(new_price) if new_price is not None else None,
            **place_kwargs,
            **kwargs
        )

    def revoke_order(self, order_id, symbol=None):
        if hasattr(self.account, "cancel_order"):
            if not symbol:
                raise ValueError("symbol is required for cancel_order on Backpack")
            full, _, _ = self._norm_symbol(symbol)
            try:
                resp = self.account.cancel_order(full, order_id=order_id)
                return True, None if resp is not None else (False, resp)
            except Exception as e:
                return False, e
        raise NotImplementedError("Account.cancel_order unavailable")


    def get_order_status(self,  order_id=None, symbol='ETH_USDC_PERP', market_type=None, window=None, keep_origin=True):
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.account, "get_open_order"):
            raise NotImplementedError("Account.get_open_order unavailable")
        try:
            resp = self.account.get_open_order(full, order_id=order_id)
            if keep_origin:
                if order_id is None:
                    return resp, None
                # 过滤指定 order_id
                if isinstance(resp, dict):
                    if str(resp.get('id')) == str(order_id):
                        return resp, None
                    return None, None
                if isinstance(resp, list):
                    for od in resp:
                        try:
                            if str(od.get('id')) == str(order_id):
                                return od, None
                        except Exception:
                            continue
                    return None, None
                return None, None

            # 统一结构
            od = None
            if isinstance(resp, dict):
                od = resp
            elif isinstance(resp, list):
                for item in resp:
                    try:
                        if str(item.get('id')) == str(order_id):
                            od = item
                            break
                    except Exception:
                        continue
            if not od:
                return None, None

            def _f(v, cast=float):
                try:
                    return cast(v)
                except Exception:
                    return None

            normalized = {
                'orderId': od.get('id') or od.get('ordId'),
                'symbol': od.get('symbol') or od.get('market') or od.get('instId'),
                'side': (od.get('side') or '').lower() if od.get('side') else None,
                'orderType': (od.get('orderType') or od.get('type') or '').lower() if (od.get('orderType') or od.get('type')) else None,
                'price': _f(od.get('price')),
                'quantity': _f(od.get('quantity')),
                'filledQuantity': _f(od.get('executedQuantity')),
                'status': od.get('status'),
                'timeInForce': od.get('timeInForce') or od.get('time_in_force'),
                'postOnly': od.get('postOnly') or od.get('post_only'),
                'reduceOnly': od.get('reduceOnly') or od.get('reduce_only'),
                'clientId': od.get('clientId') or od.get('client_id'),
                'createdAt': _f(od.get('createdAt'), int),
                'updatedAt': _f(od.get('triggeredAt'), int),
                'raw': od,
            }
            return normalized, None
        except Exception as e:
            return None, e

    def get_open_orders(self, symbol=None, instType='PERP', onlyOrderId=True, keep_origin=True):
        """
        获取未完成订单列表。
        :param symbol: 指定交易对；为空则返回全部（若底层支持）
        :param market_type: 市场类型，默认 'PERP'
        :param onlyOrderId: True 则仅返回订单号列表；False 返回完整订单对象列表
        :return: (result, error)
        """
        if hasattr(self.account, "get_open_orders"):
            try:
                if symbol:
                    try:
                        full, _, _ = self._norm_symbol(symbol)
                    except Exception as e:
                        full = symbol
                else:
                    full = symbol
                resp = self.account.get_open_orders(market_type=instType, symbol=full)

                if onlyOrderId:
                    order_ids = []
                    # 兼容 list / dict 两种返回结构
                    if isinstance(resp, list):
                        for od in resp:
                            try:
                                oid = od.get('id') if isinstance(od, dict) else None
                                if oid is not None:
                                    order_ids.append(str(oid))
                            except Exception:
                                continue
                    elif isinstance(resp, dict):
                        data = resp.get('data')
                        if isinstance(data, list):
                            for od in data:
                                try:
                                    oid = od.get('id') if isinstance(od, dict) else None
                                    if oid is not None:
                                        order_ids.append(str(oid))
                                except Exception:
                                    continue
                        else:
                            # 单个订单或以键为订单号等情况
                            oid = resp.get('id')
                            if oid is not None:
                                order_ids.append(str(oid))
                    return order_ids, None

                if keep_origin:
                    return resp, None

                # 统一结构输出 list[dict]
                def to_norm(od):
                    if not isinstance(od, dict):
                        return None
                    def _f(v, cast=float):
                        try:
                            return cast(v)
                        except Exception:
                            return None
                    return {
                        'orderId': od.get('id') or od.get('ordId'),
                        'symbol': od.get('symbol') or od.get('market') or od.get('instId'),
                        'side': (od.get('side') or '').lower() if od.get('side') else None,
                        'orderType': (od.get('orderType') or od.get('type') or '').lower() if (od.get('orderType') or od.get('type')) else None,
                        'price': _f(od.get('price')),  # str -> float
                        'quantity': _f(od.get('quantity')),  # str -> float
                        'filledQuantity': _f(od.get('executedQuantity')),  # str -> float
                        'status': od.get('status'),
                        'timeInForce': od.get('timeInForce') or od.get('time_in_force'),
                        'postOnly': od.get('postOnly') or od.get('post_only'),
                        'reduceOnly': od.get('reduceOnly') or od.get('reduce_only'),
                        'clientId': od.get('clientId') or od.get('client_id'),
                        'createdAt': _f(od.get('createdAt'), int),
                        'updatedAt': _f(od.get('triggeredAt'), int),
                        'raw': od,
                    }

                normalized = []
                if isinstance(resp, list):
                    for od in resp:
                        n = to_norm(od)
                        if n:
                            normalized.append(n)
                elif isinstance(resp, dict):
                    data = resp.get('data')
                    if isinstance(data, list):
                        for od in data:
                            n = to_norm(od)
                            if n:
                                normalized.append(n)
                    else:
                        n = to_norm(resp)
                        if n:
                            normalized.append(n)
                return normalized, None
            except Exception as e:
                return None, e
        else:
            print('我草你妈')
                
    def cancel_all(self, symbol='ETH_USDC_PERP', order_ids=[]):
        full, _, _ = self._norm_symbol(symbol)
        if hasattr(self.account, "cancel_all_orders"):
            if not symbol and len(order_ids) > 0:
                for ord in order_ids:
                    resp = self.revoke_order(ord)
            else:
                try:
                    resp = self.account.cancel_all_orders(full)
                    return {"ok": True, "raw": resp}
                except Exception as e:
                    return {"ok": False, "error": str(e)}
        raise NotImplementedError("Account.cancel_all_orders unavailable")

    # -------------- account --------------
    def fetch_balance(self, currency='USDC', window=1):
        """
        获取账户余额。
        - currency 为 None / 'ALL' / '*' 时返回全部资产字典
        - 指定 currency 时，仅返回对应资产字典 {currency: {...}}；若不存在返回 {}
        """
        if hasattr(self.account, "get_balances"):
            try:
                raw = self.account.get_balances()
                # 返回全部
                if currency is None or str(currency).strip() in ('ALL', '*'):
                    return raw

                # 仅返回指定币种
                cur = str(currency).upper()
                if isinstance(raw, dict):
                    if cur in raw:
                        return float(raw[cur]['available'])
                    # 容错：键名大小写不一致
                    for k, v in raw.items():
                        if str(k).upper() == cur:
                            return float(v['available'])
                return {}
            except Exception as e:
                return e
        raise NotImplementedError("Account.get_balances unavailable")

    def get_position(self, symbol=None, window=None, keep_origin=True):
        """
        获取当前仓位。
        - symbol 为空: 返回全部仓位
        - 指定 symbol: 仅返回该交易对仓位（若未找到返回 None）
        返回 (result, error)
        """
        if not hasattr(self.account, 'get_open_positions'):
            return None, NotImplementedError('Account.get_open_positions unavailable')
        try:
            resp = self.account.get_open_positions(window=window)
            if keep_origin:
                if not symbol:
                    return resp, None
                full, _, _ = self._norm_symbol(symbol)
                # 可能返回 list[dict] 或 dict
                if isinstance(resp, list):
                    for pos in resp:
                        try:
                            ps = pos.get('symbol') or pos.get('market') or pos.get('instId')
                            if ps and str(ps).upper() == full:
                                return pos, None
                        except Exception:
                            continue
                    return None, None
                if isinstance(resp, dict):
                    if 'symbol' in resp or 'market' in resp or 'instId' in resp:
                        ps = resp.get('symbol') or resp.get('market') or resp.get('instId')
                        if ps and str(ps).upper() == full:
                            return resp, None
                        return None, None
                    for k, v in resp.items():
                        if str(k).upper() == full:
                            return v, None
                    return None, None
                return None, None

            # 统一结构输出
            def to_unified(pos):
                try:
                    qty = float(pos.get('netQuantity') or pos.get('netExposureQuantity') or pos.get('pos') or 0.0)
                except Exception:
                    qty = 0.0
                side = 'long' if qty > 0 else ('short' if qty < 0 else 'flat')
                def _f(v):
                    try:
                        return float(v)
                    except Exception:
                        return None
                entry = _f(pos.get('entryPrice'))
                mark = _f(pos.get('markPrice'))
                upl = _f(pos.get('pnlUnrealized'))
                realized = _f(pos.get('pnlRealized'))
                lev = _f(pos.get('leverage'))
                fee = _f(pos.get('cumulativeFundingPayment'))
                liq = _f(pos.get('estLiquidationPrice'))
                # Backpack 未提供时间戳，置空
                ts = None
                return {
                    'symbol': pos.get('symbol') or pos.get('market') or pos.get('instId'),
                    'positionId': pos.get('positionId') or pos.get('posId'),
                    'side': side,
                    'quantity': abs(qty),
                    'entryPrice': entry,
                    'markPrice': mark,
                    'pnlUnrealized': upl,
                    'pnlRealized': realized,
                    'leverage': lev,
                    'liquidationPrice': liq,
                    'ts': ts,
                    'fee':fee
                }

            unified = None
            if isinstance(resp, list):
                unified = [to_unified(p) for p in resp]
            elif isinstance(resp, dict):
                # 单个或映射
                if 'symbol' in resp or 'market' in resp or 'instId' in resp:
                    unified = [to_unified(resp)]
                else:
                    unified = [to_unified(v) for _, v in resp.items()]
            else:
                unified = []

            if not symbol:
                return unified, None
            full, _, _ = self._norm_symbol(symbol)
            for u in unified:
                if str(u.get('symbol')).upper() == full:
                    return u, None
            return None, None
        except Exception as e:
            return None, e


    def close_all_positions(self, mode="market", price_offset=0.0005, symbol=None, side=None, is_good=None):
        """
        平掉所有仓位，可附加过滤条件

        :param mode: "market" 或 "limit"
        :param price_offset: limit 平仓时的价格偏移系数
        :param symbol: 仅平某个币种 (e.g. "BTC_USDC_PERP")
        :param side: "long" 仅平多仓, "short" 仅平空仓, None 表示不限
        :param is_good: True 仅平盈利仓, False 仅平亏损仓, None 表示不限
        """
        positions = self.get_position(symbol=symbol)  # 获取所有仓位信息
        
        if not positions:
            print("✅ 当前无持仓")
            return
        
        for pos in positions:
            sym = pos["symbol"]
            qty = float(pos["netQuantity"])
            mark_price = float(pos["markPrice"])
            pnl_unreal = float(pos["pnlUnrealized"])

            if qty == 0:
                continue  # 跳过空仓

            # 过滤 symbol
            if symbol and sym != symbol:
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

            # 构造平仓单
            if qty > 0:  # 多仓 -> 平仓卖出
                order_side = "SELL"
                size = qty
            else:        # 空仓 -> 平仓买入
                order_side = "BUY"
                size = abs(qty)
                
            if mode == "market":
                self.place_order(symbol=sym, side=order_side, order_type="market", size=size)
                print(f"📤 市价平仓: {sym} {order_side} {size}")

            elif mode == "limit":
                if order_side == "SELL":
                    price = mark_price * (1 - price_offset)
                else:
                    price = mark_price * (1 + price_offset)
                self.place_order(symbol=sym, side=order_side, order_type="limit", size=size, price=price)
                print(f"📤 限价平仓: {sym} {order_side} {size} @ {price}")

            else:
                raise ValueError("mode 必须是 'market' 或 'limit'")

if __name__ == "__main__":
    bp = BackpackDriver()
    print(bp.get_position())
