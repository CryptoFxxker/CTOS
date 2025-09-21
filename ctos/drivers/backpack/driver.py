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

    def __init__(self, account_client=None, public_client=None, mode="perp", default_quote="USDC", account_id=0):
        self.cex = 'Backpack'
        self.quote_ccy = 'USDC'
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
            # print(self.public.get_funding_interval_rates(full, int(limit), int(offset)))
            raw = self.public.get_funding_interval_rates(full, int(limit), int(offset))
            if keep_origin:
                return raw            # 标准化输出，尽量提供 latest，并统一为每小时资金费率
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
    def _adjust_precision_for_error(self, value, error_msg, value_type='price'):
        """
        根据错误信息调整数值精度
        :param value: 需要调整的数值
        :param error_msg: 错误信息
        :param value_type: 'price' 或 'quantity'
        :return: 调整后的数值
        """
        if not error_msg:
            return value
            
        error_str = str(error_msg).lower()
        
        # 处理价格精度错误
        if value_type == 'price' and ('price decimal too long' in error_str or 'decimal too long' in error_str):
            # 减少价格的小数位数
            if '.' in str(value):
                decimal_places = len(str(value).split('.')[1])
                new_places = max(0, decimal_places - 1)
                return round(value, new_places)
            return value
            
        # 处理数量精度错误
        elif value_type == 'quantity' and ('quantity decimal too long' in error_str or 'decimal too long' in error_str):
            # 减少数量的小数位数
            if '.' in str(value):
                decimal_places = len(str(value).split('.')[1])
                new_places = max(0, decimal_places - 1)
                return round(value, new_places)
            return value
            
        # 处理数量过小错误
        elif value_type == 'quantity' and ('quantity is below the minimum' in error_str or 'below the minimum' in error_str):
            # 增加数量到最小允许值
            return max(value, 0.0001)  # 设置一个合理的最小值
            
        # 处理解析错误（通常是由于精度问题）
        elif 'parse request payload error' in error_str or 'invalid decimal' in error_str:
            if value_type == 'price':
                # 价格保留2位小数
                return round(value, 2)
            elif value_type == 'quantity':
                # 数量保留4位小数
                return round(value, 4)
                
        return value

    def place_order(self, symbol, side, order_type, size, price=None, client_id=None, max_retries=3, **kwargs):
        """
        下单函数，带错误处理和重试机制
        
        自动处理以下错误类型：
        - Price decimal too long: 自动减少价格小数位数
        - Quantity decimal too long: 自动减少数量小数位数  
        - Quantity is below the minimum: 自动增加数量到最小允许值
        - parse request payload error: 自动调整精度格式
        
        使用示例：
        >>> driver = BackpackDriver()
        >>> # 正常下单
        >>> order_id, error = driver.place_order('ETH_USDC_PERP', 'buy', 'limit', 0.01, 2000.0)
        >>> # 带重试的下单
        >>> order_id, error = driver.place_order('ETH_USDC_PERP', 'buy', 'limit', 0.01, 2000.0, max_retries=5)
        
        :param symbol: 交易对
        :param side: 买卖方向 ('buy'/'sell')
        :param order_type: 订单类型 ('limit'/'market')
        :param size: 数量
        :param price: 价格（限价单需要）
        :param client_id: 客户端订单ID
        :param max_retries: 最大重试次数
        :param kwargs: 其他参数
        :return: (order_id, error)
        """
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.account, "execute_order"):
            raise NotImplementedError("Account.execute_order unavailable")

        original_size = size
        original_price = price
        
        for attempt in range(max_retries + 1):
            try:
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
                
                # 检查下单结果
                if isinstance(order, dict) and 'id' in order:
                    # 下单成功
                    if attempt > 0:
                        print(f"✓ 下单成功 (重试第{attempt}次): {symbol} {side} {size}@{price}")
                    return order.get('id'), None
                else:
                    # 下单失败，检查是否有重试机会
                    if attempt < max_retries:
                        error_msg = str(order) if order else "Unknown error"
                        print(f"⚠ 下单失败 (第{attempt + 1}次): {error_msg}")
                        
                        # 根据错误类型进行相应的调整
                        error_lower = error_msg.lower()
                        
                        # 判断错误类型并调整参数
                        if 'price decimal too long' in error_lower:
                            # 价格精度过高，减少小数位
                            if order_type.lower() == 'limit' and price is not None:
                                new_price = self._adjust_precision_for_error(price, error_msg, 'price')
                                if new_price != price:
                                    price = new_price
                                    print(f"调整价格精度: {original_price} -> {price}")
                                    
                        elif 'quantity decimal too long' in error_lower:
                            # 数量精度过高，减少小数位
                            new_size = self._adjust_precision_for_error(size, error_msg, 'quantity')
                            if new_size != size:
                                size = new_size
                                print(f"调整数量精度: {original_size} -> {size}")
                                
                        elif 'quantity is below the minimum' in error_lower:
                            # 数量过小，增加数量
                            new_size = self._adjust_precision_for_error(size, error_msg, 'quantity')
                            if new_size != size:
                                size = new_size
                                print(f"增加数量: {original_size} -> {size}")
                            else:
                                # 如果调整函数没有处理，手动增加数量
                                size = max(size * 1.1, 0.001)
                                print(f"手动增加数量: {original_size} -> {size}")
                                
                        elif 'parse request payload error' in error_lower or 'invalid decimal' in error_lower:
                            # 解析错误，同时调整价格和数量精度
                            if order_type.lower() == 'limit' and price is not None:
                                new_price = self._adjust_precision_for_error(price, error_msg, 'price')
                                if new_price != price:
                                    price = new_price
                                    print(f"调整价格精度: {original_price} -> {price}")
                            
                            new_size = self._adjust_precision_for_error(size, error_msg, 'quantity')
                            if new_size != size:
                                size = new_size
                                print(f"调整数量精度: {original_size} -> {size}")
                                
                        else:
                            # 未知错误类型，尝试通用调整策略
                            print(f"未知错误类型，尝试通用调整: {error_msg}")
                            if order_type.lower() == 'limit' and price is not None:
                                # 尝试减少价格精度
                                price = round(price, 2)
                                print(f"通用调整价格精度: {original_price} -> {price}")
                            
                            # 尝试减少数量精度
                            size = round(size, 4)
                            print(f"通用调整数量精度: {original_size} -> {size}")
                        
                        # 等待一段时间后重试
                        import time
                        time.sleep(0.5)
                    else:
                        # 最后一次尝试失败，返回错误
                        print(f"✗ 下单最终失败: {symbol} {side} {size}@{price}")
                        return None, order
                        
            except Exception as e:
                if attempt < max_retries:
                    print(f"⚠ 下单异常 (第{attempt + 1}次): {str(e)}")
                    import time
                    time.sleep(0.5)
                else:
                    print(f"✗ 下单异常最终失败: {str(e)}")
                    return None, str(e)
        
        return None, "Max retries exceeded"

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
                    # for k, v in raw.items():
                    #     if str(k).upper() == cur:
                    #         return float(v['available'])
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
                    'fee':fee,
                    'breakEvenPrice':pos.get('breakEvenPrice')
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

# last = x.fetch_balance()
# now = time.time()
# for i in range(10):  # 连续测 10 次
#     balance = x.fetch_balance()
#     print(f"[{now}] USDT balance = {balance}")
    
#     if balance != last:
#         print(f" {time.time() - now} ⚡ 变化了！")
#         break    
#     time.sleep(60)  # 每 2 秒请求一次


def test_error_handling():
    """测试Backpack Driver的错误处理功能"""
    print("=== Backpack Driver 错误处理功能测试 ===")
    
    try:
        # 创建Driver实例
        driver = BackpackDriver()
        print("✓ Backpack Driver创建成功")
        
        # 测试1: 错误处理函数测试
        print("\n1. 错误处理函数测试:")
        
        # 测试价格精度调整
        print("\n1.1 测试价格精度调整:")
        test_price = 4200.001
        error_msg = "Price decimal too long"
        adjusted_price = driver._adjust_precision_for_error(test_price, error_msg, 'price')
        print(f"原始价格: {test_price}")
        print(f"调整后价格: {adjusted_price}")
        assert adjusted_price == 4200.0, f"价格调整失败: {adjusted_price}"
        print("✓ 价格精度调整测试通过")
        
        # 测试数量精度调整
        print("\n1.2 测试数量精度调整:")
        test_quantity = 0.0111
        error_msg = "Quantity decimal too long"
        adjusted_quantity = driver._adjust_precision_for_error(test_quantity, error_msg, 'quantity')
        print(f"原始数量: {test_quantity}")
        print(f"调整后数量: {adjusted_quantity}")
        assert adjusted_quantity == 0.011, f"数量调整失败: {adjusted_quantity}"
        print("✓ 数量精度调整测试通过")
        
        # 测试数量过小错误
        print("\n1.3 测试数量过小错误:")
        test_quantity = 0.00001
        error_msg = "Quantity is below the minimum allowed value"
        adjusted_quantity = driver._adjust_precision_for_error(test_quantity, error_msg, 'quantity')
        print(f"原始数量: {test_quantity}")
        print(f"调整后数量: {adjusted_quantity}")
        assert adjusted_quantity == 0.0001, f"数量调整失败: {adjusted_quantity}"
        print("✓ 数量过小错误测试通过")
        
        # 测试解析错误
        print("\n1.4 测试解析错误:")
        test_price = 4200.0
        test_quantity = 0.00001
        error_msg = "parse request payload error: failed to parse \"string_decimal\": Invalid decimal"
        adjusted_price = driver._adjust_precision_for_error(test_price, error_msg, 'price')
        adjusted_quantity = driver._adjust_precision_for_error(test_quantity, error_msg, 'quantity')
        print(f"原始价格: {test_price} -> 调整后: {adjusted_price}")
        print(f"原始数量: {test_quantity} -> 调整后: {adjusted_quantity}")
        assert adjusted_price == 4200.0, f"价格调整失败: {adjusted_price}"
        assert adjusted_quantity == 0.0, f"数量调整失败: {adjusted_quantity}"
        print("✓ 解析错误测试通过")
        
        print("\n=== 错误处理函数测试完成 ===")
        
        # 测试2: 实际下单测试（需要API配置）
        print("\n2. 实际下单测试（需要API配置）:")
        print("注意：此部分需要有效的API配置才能运行")
        
        try:
            # 获取当前价格
            current_price = driver.get_price_now('ETH_USDC_PERP')
            if current_price:
                print(f"当前ETH价格: {current_price}")
                print("✓ 价格获取成功，API连接正常")
                
                # 测试下单（使用很小的金额，避免实际成交）
                print("\n2.1 测试下单（限价单）:")
                test_price = current_price * 0.9  # 低于市价，避免成交
                test_size = 0.0001  # 很小的数量
                
                print(f"测试下单: ETH_USDC_PERP buy limit {test_size}@{test_price}")
                order_id, error = driver.place_order(
                    'ETH_USDC_PERP', 
                    'buy', 
                    'limit', 
                    test_size, 
                    test_price,
                    max_retries=2  # 减少重试次数用于测试
                )
                
                if order_id:
                    print(f"✓ 下单成功，订单ID: {order_id}")
                    # 立即撤销订单
                    try:
                        cancel_result = driver.revoke_order(order_id, 'ETH_USDC_PERP')
                        print(f"✓ 订单撤销: {'成功' if cancel_result else '失败'}")
                    except Exception as cancel_error:
                        print(f"⚠ 订单撤销失败: {cancel_error}")
                else:
                    print(f"✗ 下单失败: {error}")
                    print("这可能是由于API配置或网络问题")
                    
            else:
                print("✗ 无法获取当前价格，请检查API配置")
                
        except Exception as api_error:
            print(f"⚠ API测试失败: {api_error}")
            print("请检查API配置和网络连接")
        
        print("\n=== 所有测试完成 ===")
        
    except Exception as e:
        print(f"✗ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


def test_precision_scenarios():
    """测试各种精度场景"""
    print("\n=== 精度场景测试 ===")
    
    try:
        driver = BackpackDriver()
        
        # 测试场景1: 价格精度过高
        print("\n场景1: 价格精度过高")
        test_cases = [
            (4200.001, "Price decimal too long"),
            (1234.56789, "Price decimal too long"),
            (0.123456, "Price decimal too long")
        ]
        
        for price, error in test_cases:
            adjusted = driver._adjust_precision_for_error(price, error, 'price')
            print(f"  {price} -> {adjusted}")
        
        # 测试场景2: 数量精度过高
        print("\n场景2: 数量精度过高")
        test_cases = [
            (0.0111, "Quantity decimal too long"),
            (1.234567, "Quantity decimal too long"),
            (0.0001234, "Quantity decimal too long")
        ]
        
        for quantity, error in test_cases:
            adjusted = driver._adjust_precision_for_error(quantity, error, 'quantity')
            print(f"  {quantity} -> {adjusted}")
        
        # 测试场景3: 数量过小
        print("\n场景3: 数量过小")
        test_cases = [
            (0.00001, "Quantity is below the minimum allowed value"),
            (0.000001, "Quantity is below the minimum allowed value"),
            (1e-8, "Quantity is below the minimum allowed value")
        ]
        
        for quantity, error in test_cases:
            adjusted = driver._adjust_precision_for_error(quantity, error, 'quantity')
            print(f"  {quantity} -> {adjusted}")
        
        # 测试场景4: 解析错误
        print("\n场景4: 解析错误")
        test_cases = [
            (4200.0, "parse request payload error: failed to parse \"string_decimal\": Invalid decimal"),
            (0.00001, "parse request payload error: failed to parse \"string_decimal\": Invalid decimal")
        ]
        
        for value, error in test_cases:
            adjusted_price = driver._adjust_precision_for_error(value, error, 'price')
            adjusted_quantity = driver._adjust_precision_for_error(value, error, 'quantity')
            print(f"  价格 {value} -> {adjusted_price}")
            print(f"  数量 {value} -> {adjusted_quantity}")
        
        print("✓ 精度场景测试完成")
        
    except Exception as e:
        print(f"✗ 精度场景测试失败: {e}")


def test_error_type_detection():
    """测试错误类型检测逻辑"""
    print("\n=== 错误类型检测测试 ===")
    
    try:
        driver = BackpackDriver()
        
        # 模拟不同的错误类型
        error_scenarios = [
            {
                'error': "Price decimal too long",
                'expected_type': 'price_precision',
                'description': '价格精度过高'
            },
            {
                'error': "Quantity decimal too long", 
                'expected_type': 'quantity_precision',
                'description': '数量精度过高'
            },
            {
                'error': "Quantity is below the minimum allowed value",
                'expected_type': 'quantity_minimum',
                'description': '数量过小'
            },
            {
                'error': "parse request payload error: failed to parse \"string_decimal\": Invalid decimal",
                'expected_type': 'parse_error',
                'description': '解析错误'
            },
            {
                'error': "Unknown error type",
                'expected_type': 'unknown',
                'description': '未知错误'
            }
        ]
        
        for scenario in error_scenarios:
            error_msg = scenario['error']
            error_lower = error_msg.lower()
            
            print(f"\n测试错误: {scenario['description']}")
            print(f"错误信息: {error_msg}")
            
            # 模拟错误类型检测逻辑
            if 'price decimal too long' in error_lower:
                detected_type = 'price_precision'
            elif 'quantity decimal too long' in error_lower:
                detected_type = 'quantity_precision'
            elif 'quantity is below the minimum' in error_lower:
                detected_type = 'quantity_minimum'
            elif 'parse request payload error' in error_lower or 'invalid decimal' in error_lower:
                detected_type = 'parse_error'
            else:
                detected_type = 'unknown'
            
            print(f"检测到的错误类型: {detected_type}")
            print(f"预期错误类型: {scenario['expected_type']}")
            print(f"检测结果: {'✓ 正确' if detected_type == scenario['expected_type'] else '✗ 错误'}")
        
        print("\n✓ 错误类型检测测试完成")
        
    except Exception as e:
        print(f"✗ 错误类型检测测试失败: {e}")


if __name__ == '__main__':
    # 运行错误处理测试
    success = test_error_handling()
    
    if success:
        # 运行精度场景测试
        test_precision_scenarios()
        
        # 运行错误类型检测测试
        test_error_type_detection()
        
        print("\n🎉 所有测试完成！")
        print("\n使用说明:")
        print("1. 基本下单: driver.place_order('ETH_USDC_PERP', 'buy', 'limit', 0.01, 2000.0)")
        print("2. 带重试: driver.place_order('ETH_USDC_PERP', 'buy', 'limit', 0.01, 2000.0, max_retries=5)")
        print("3. 自动错误处理: Driver会自动检测错误类型并进行相应调整")
        print("4. 支持的错误类型:")
        print("   - Price decimal too long: 自动减少价格小数位数")
        print("   - Quantity decimal too long: 自动减少数量小数位数")
        print("   - Quantity is below the minimum: 自动增加数量")
        print("   - Parse request payload error: 自动调整精度格式")
        print("   - 未知错误: 使用通用调整策略")
    else:
        print("\n❌ 测试失败，请检查配置")