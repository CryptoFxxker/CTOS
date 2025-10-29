# -*- coding: utf-8 -*-
# ctos/drivers/okx/driver_ccxt.py
# OKX driver using ccxt library
# pip install ccxt

from __future__ import annotations
import os
import time
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import sys

def _add_bpx_path():
    """添加bpx包路径到sys.path，支持多种运行方式"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 添加项目根目录的bpx路径（如果存在）
    project_root = os.path.abspath(os.path.join(current_dir, '../../..'))
    root_bpx_path = os.path.join(project_root, 'bpx')
    if os.path.exists(root_bpx_path) and root_bpx_path not in sys.path:
        sys.path.insert(0, root_bpx_path)
    if os.path.exists(project_root) and project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root
# 执行路径添加
_PROJECT_ROOT = _add_bpx_path()
print('PROJECT_ROOT: ', _PROJECT_ROOT, 'CURRENT_DIR: ', os.path.dirname(os.path.abspath(__file__)))


# syscall base（与你的项目保持一致）
try:
    from ctos.core.kernel.syscalls import TradingSyscalls
except ImportError:
    import sys
    import os
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
    from ctos.core.kernel.syscalls import TradingSyscalls

# ccxt connector
try:
    from ccxt import okx as ccxt_okx
except ImportError:
    raise RuntimeError("请先安装ccxt: pip install ccxt")

def init_okx_clients(mode: str = "swap", api_key: Optional[str] = None, api_secret: Optional[str] = None, passphrase: Optional[str] = None, account_id: int = 0):
    """
    初始化ccxt OKX客户端：
      mode = 'spot' 使用 okx spot
      mode = 'swap' 使用 okx futures
    优先读取环境变量 OKX_API_KEY / OKX_API_SECRET / OKX_PASSPHRASE
    """
    k = api_key or os.getenv("OKX_API_KEY") or ""
    s = api_secret or os.getenv("OKX_API_SECRET") or ""
    p = passphrase or os.getenv("OKX_PASSPHRASE") or ""
    config = {
        'apiKey': k,
        'secret': s,
        'password': p,  # OKX使用passphrase作为password
        'sandbox': False,  # 生产环境
        'enableRateLimit': True,
        'proxies': {'https': 'socks5h://127.0.0.1:1080',}
    }
    if mode.lower() == "spot":
        exchange = ccxt_okx(config)
        return {"spot": exchange, "swap": None}
    else:
        exchange = ccxt_okx(config)
        return {"spot": None, "swap": exchange}


class OkxDriver(TradingSyscalls):
    """
    CTOS OKX driver (ccxt connector).
    Mode-aware symbol normalization for OKX style symbols:
      - spot:  "BASE-QUOTE"           e.g. "BTC-USDT"
      - swap:  "BASE-QUOTE-SWAP"      e.g. "BTC-USDT-SWAP"
    Accepts inputs like 'btc-usdt', 'BTC/USDT', 'BTC-USDT-SWAP', 'btc', etc.
    """

    def __init__(self, account_client=None, mode="swap", default_quote="USDT", account_id=0):
        self.cex = 'OKX'
        self.quote_ccy = 'USDT'
        self.account_id = account_id
        """
        :param account_client: Optional. An initialized ccxt exchange client.
        :param mode: "swap" or "spot". If "swap", we append '-SWAP' suffix when needed.
        :param default_quote: default quote when user passes 'BTC' without '-USDT'
        :param account_id: 账户ID，根据配置文件中的账户顺序映射 (0=第一个账户, 1=第二个账户, ...)
        """
        if account_client is None:
            cli = init_okx_clients(mode=mode, account_id=account_id)
            self.account = account_client or cli["swap"] or cli["spot"]
            if cli["swap"] or cli["spot"]:
                print(f"✓ OKX Driver初始化成功 (账户ID: {account_id}, 模式: {mode})")
            else:
                print(f"✗ OKX Driver初始化失败 (账户ID: {account_id})")
        else:
            self.account = account_client
            print(f"✓ OKX Driver使用外部客户端 (账户ID: {account_id})")
        
        self.mode = (mode or "swap").lower()
        self.default_quote = default_quote or "USDT"
        self.symbol = 'ETH-USDT-SWAP' if mode == "swap" else 'ETH-USDT'
        self.load_exchange_trade_info()
        self.order_id_to_symbol = {}

    def save_exchange_trade_info(self):
        with open(os.path.dirname(os.path.abspath(__file__)) + '/exchange_trade_info.json', 'w') as f:
            json.dump(self.exchange_trade_info, f)

    def load_exchange_trade_info(self):
        if not os.path.exists(os.path.dirname(os.path.abspath(__file__)) + '/exchange_trade_info.json'):
            self.exchange_trade_info = {}
            return
        with open(os.path.dirname(os.path.abspath(__file__)) + '/exchange_trade_info.json', 'r') as f:
            self.exchange_trade_info = json.load(f)

    # -------------- helpers --------------
    def _norm_symbol(self, symbol):
        """
        Normalize symbols to OKX format.
        Returns (full_symbol, base_lower, quote_upper)
        Examples:
          _norm_symbol('btc') -> ('BTC-USDT-SWAP', 'btc', 'USDT')  # in swap mode
          _norm_symbol('BTC-USDT-SWAP') -> ('BTC-USDT-SWAP', 'btc', 'USDT')
          _norm_symbol('SOL/USDT') -> ('SOL-USDT-SWAP', 'sol', 'USDT')  # in swap mode
          _norm_symbol('BTC-USDT') -> ('BTC-USDT-SWAP', 'btc', 'USDT')  # in swap mode
        """
        s = str(symbol or "").strip()
        if not s:
            return None, None, None

        # unify separators and uppercase
        su = s.replace("/", "-").replace("_", "-").upper()

        if "-" in su:
            parts = su.split("-")
            base = parts[0]
            quote = parts[1] if len(parts) > 1 else self.default_quote
        else:
            # Only base provided
            base = su
            quote = self.default_quote

        full = f"{base}-{quote}"
        
        # Add SWAP suffix for swap mode
        if self.mode == "swap" and not full.endswith("-SWAP"):
            full = full + "-SWAP"

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
    def symbols(self, instType='SWAP'):
        """
        返回 (symbols, error)
        - 成功: (list[str], None)
        - 失败: (None, Exception)
        根据 self.mode 过滤：swap 仅返回期货，spot 仅返回现货。
        """
        if not hasattr(self, "public") or self.account is None:
            return None, NotImplementedError("Public client not initialized")
        try:
            markets = self.account.load_markets()
            if self.mode == "spot":
                # 现货市场
                syms = [symbol for symbol, market in markets.items() 
                       if market.get('type') == 'spot' and market.get('active', True)]
            else:
                # 期货市场
                syms = [symbol for symbol, market in markets.items() 
                       if market.get('type') == 'future' and market.get('active', True)]
            return syms, None
        except Exception as e:
            return None, e

    def exchange_limits(self, symbol=None, instType='SWAP'):
        """
        获取交易所限制信息，包括价格精度、数量精度、最小下单数量等
        
        :param symbol: 交易对符号，如 'BTC-USDT-SWAP'，如果为None则返回全类型数据
        :param instType: 产品类型，默认为 'SWAP'
        :return: dict 包含限制信息的字典
        """
        if symbol:
            symbol, _, _ = self._norm_symbol(symbol)
            if symbol in self.exchange_trade_info:
                return self.exchange_trade_info[symbol], None
        try:
            markets = self.account.load_markets()
            
            # 如果指定了symbol，获取单个交易对信息
            if symbol:
                if symbol not in markets:
                    return {"error": f"未找到交易对 {symbol} 的信息"}, None
                
                market = markets[symbol]
                limits = self._extract_limits_from_market(market)
                if limits and 'error' not in limits:
                    self.exchange_trade_info[symbol] = limits
                    self.save_exchange_trade_info()
                return limits, None
            
            # 如果没有指定symbol，获取所有交易对信息
            result = []
            for symbol_name, market in markets.items():
                if self.mode == "spot" and market.get('type') != 'spot':
                    continue
                if self.mode == "swap" and market.get('type') != 'future':
                    continue
                    
                limits = self._extract_limits_from_market(market)
                if limits and 'error' not in limits:
                    result.append(limits)
                    self.exchange_trade_info[symbol_name] = limits
            
            self.save_exchange_trade_info()
            return result, None
            
        except Exception as e:
            return None, {"error": f"处理数据时发生异常: {str(e)}"}
    
    def _extract_limits_from_market(self, market):
        """
        从ccxt market信息中提取限制信息
        
        :param market: ccxt market信息字典
        :return: dict 包含限制信息的字典
        """
        try:
            symbol = market.get('symbol', '')
            
            # 从ccxt market信息中提取精度和限制
            price_precision = market.get('precision', {}).get('price', 0.01)
            size_precision = market.get('precision', {}).get('amount', 0.001)
            min_qty = market.get('limits', {}).get('amount', {}).get('min', 0.001)
            
            return {
                'symbol': symbol,
                'instType': 'SWAP' if self.mode == 'swap' else 'SPOT',
                'price_precision': price_precision,
                'size_precision': size_precision,
                'min_order_size': min_qty,
                'contract_value': 1.0,
                'max_leverage': 125.0 if self.mode == 'swap' else 1.0,
                'state': 'live' if market.get('active', True) else 'inactive',
                'raw': market
            }
        except Exception as e:
            return {"error": f"解析market信息时发生异常: {str(e)}"}

    def fees(self, symbol='ETH-USDT-SWAP', instType='SWAP', keep_origin=False, limit=3, offset=0):
        """
        获取资金费率信息。
        - 对于 OKX，使用 fetch_funding_rate() 方法
        - 返回 (result, error)
        - 统一返回结构到"每小时资金费率"。
        """
        if not hasattr(self.account, 'fetch_funding_rate'):
            return None, NotImplementedError('Public.fetch_funding_rate unavailable')

        full, _, _ = self._norm_symbol(symbol)
        if self.mode != "swap":
            return {"symbol": full, "instType": "SPOT", "fundingRate_hourly": None, "raw": None}, None
        
        try:
            raw = self.account.fetch_funding_rate(symbol=full)
            if keep_origin:
                return raw, None
            
            # ccxt返回格式: {'symbol': 'BTC-USDT-SWAP', 'fundingRate': 0.0001, 'timestamp': 1692345600000, 'datetime': '2023-08-17T00:00:00.000Z'}
            fr_period = raw.get('fundingRate')
            ts_ms = raw.get('timestamp')
            period_hours = 8.0  # OKX默认8小时周期

            hourly = None
            if fr_period is not None:
                hourly = fr_period / period_hours

            result = {
                'symbol': full,
                'instType': instType,
                'fundingRate_hourly': hourly,
                'fundingRate_period': fr_period,
                'period_hours': period_hours,
                'fundingTime': ts_ms,
                'raw': raw,
                'latest': raw,
            }
            return result, None
        except Exception as e:
            return None, e

    # -------------- market data --------------
    def get_price_now(self, symbol='ETH-USDT-SWAP'):
        full, base, _ = self._norm_symbol(symbol)
        if hasattr(self.account, "fetch_ticker"):
            try:
                data = self.account.fetch_ticker(symbol=full)
                # ccxt返回格式: {'symbol': 'BTC-USDT-SWAP', 'last': 2000.0, 'bid': 1999.0, 'ask': 2001.0, ...}
                if isinstance(data, dict):
                    price = data.get('last') or data.get('close')
                    if price is not None:
                        return float(price), None
            except Exception as e:
                return None, e
        return None, NotImplementedError("Public.fetch_ticker unavailable or response lacks price")

    def get_orderbook(self, symbol='ETH-USDT-SWAP', level=50):
        full, _, _ = self._norm_symbol(symbol)
        if hasattr(self.account, "fetch_order_book"):
            try:
                raw = self.account.fetch_order_book(symbol=full, limit=int(level))
                bids = raw.get("bids", []) if isinstance(raw, dict) else []
                asks = raw.get("asks", []) if isinstance(raw, dict) else []
                return {"symbol": full, "bids": bids, "asks": asks}, None
            except Exception as e:
                return None, e
        return None, NotImplementedError("Public.fetch_order_book unavailable")

    def get_klines(self, symbol='ETH-USDT-SWAP', timeframe='1h', limit=200, start_time=None, end_time=None):
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.account, "fetch_ohlcv"):
            return None, NotImplementedError("Public.fetch_ohlcv unavailable")

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
            since = int(start_time * 1000) if start_time else None
            raw = self.account.fetch_ohlcv(symbol=full, timeframe=timeframe, since=since, limit=int(limit))
        except Exception as e:
            return None, e

        # 统一为列表
        if isinstance(raw, list):
            rows = raw
        else:
            return None, ValueError("Unexpected ohlcv response format")

        # 重排为目标DF格式: trade_date(ms), open, high, low, close, vol1(base), vol(quote)
        records = []
        for k in rows:
            if not isinstance(k, list) or len(k) < 6:
                continue
            try:
                # ccxt ohlcv row: [timestamp, open, high, low, close, volume]
                ts_ms = int(k[0])  # 时间戳（毫秒）
                o = float(k[1])
                h = float(k[2])
                l = float(k[3])
                c = float(k[4])
                base_vol = float(k[5])
                quote_vol = base_vol * c  # 估算quote volume

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
            df = pd.DataFrame.from_records(records, columns=['trade_date', 'open', 'high', 'low', 'close', 'vol1', 'vol'])
            return df, None
        except Exception:
            # 退化为列表
            return records, None

    # -------------- trading --------------
    def place_order(self, symbol, side, order_type, size, price=None, client_id=None, max_retries=4, **kwargs):
        """
        下单函数，带错误处理和重试机制
        
        自动处理以下错误类型：
        - Price precision error: 自动调整价格精度
        - Quantity precision error: 自动调整数量精度  
        - Quantity below minimum: 自动增加数量到最小允许值
        - Invalid symbol: 自动调整符号格式
        
        使用示例：
        >>> driver = OKXDriver()
        >>> # 正常下单
        >>> order_id, error = driver.place_order('BTC-USDT-SWAP', 'buy', 'limit', 0.01, 2000.0)
        >>> # 带重试的下单
        >>> order_id, error = driver.place_order('BTC-USDT-SWAP', 'buy', 'limit', 0.01, 2000.0, max_retries=5)
        
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
        if not hasattr(self.account, "create_order"):
            return None, NotImplementedError("Account.create_order unavailable")

        original_size = size
        original_price = price
        
        for attempt in range(max_retries + 1):
            try:
                # Map CTOS -> ccxt format
                ccxt_side = "buy" if str(side).lower() in ("buy", "bid", "long") else "sell"
                ccxt_type = "limit" if str(order_type).lower() in ("limit",) else "market"
                
                params = {
                    "symbol": full,
                    "side": ccxt_side,
                    "type": ccxt_type,
                    "amount": float(size),
                }
                if price is not None:
                    params["price"] = float(price)
                if client_id:
                    params["clientOrderId"] = client_id
                # passthrough extras like post_only
                params.update(kwargs)

                order = self.account.create_order(**params)
                
                # 检查下单结果
                if isinstance(order, dict) and ('id' in order or 'orderId' in order):
                    # 下单成功
                    order_id = order.get('id') or order.get('orderId')
                    if attempt > 0:
                        print(f"✓ 下单成功 (重试第{attempt}次): {symbol} {side} {size}@{price}")
                    return str(order_id), None
                else:
                    # 下单失败，检查是否有重试机会
                    if attempt < max_retries:
                        error_msg = str(order) if order else "Unknown error"
                        print(f"⚠ 下单失败 (第{attempt + 1}次): {error_msg}")
                        
                        # 根据错误类型进行相应的调整
                        error_lower = error_msg.lower()
                        
                        # 记录调整前的参数
                        original_price = price
                        original_size = size
                        
                        # 判断错误类型并调整参数
                        if 'precision' in error_lower and 'price' in error_lower:
                            # 价格精度问题，调整价格精度
                            if order_type.lower() == 'limit' and price is not None:
                                price = round(float(price), 4)
                                print(f"🔧 调整价格精度: {original_price} -> {price}")
                                
                        elif 'precision' in error_lower and 'quantity' in error_lower:
                            # 数量精度问题，调整数量精度
                            size = round(float(size), 4)
                            print(f"🔧 调整数量精度: {original_size} -> {size}")
                            
                        elif 'min notional' in error_lower or 'below minimum' in error_lower:
                            # 数量过小，增加数量
                            size = max(size * 1.1, 0.001)
                            print(f"🔧 增加数量: {original_size} -> {size}")
                            
                        elif 'invalid symbol' in error_lower:
                            # 符号无效，尝试重新规范化
                            full, _, _ = self._norm_symbol(symbol)
                            print(f"🔧 重新规范化符号: {symbol} -> {full}")
                            
                        else:
                            # 未知错误类型，尝试通用调整策略
                            print(f"⚠ 未知错误类型，尝试通用调整: {error_msg}")
                            if order_type.lower() == 'limit' and price is not None:
                                # 尝试减少价格精度
                                price = round(float(price), 4)
                                print(f"🔧 通用调整价格精度: {original_price} -> {price}")
                            
                            # 尝试减少数量精度
                            size = round(float(size), 4)
                            print(f"🔧 通用调整数量精度: {original_size} -> {size}")
                        
                        # 等待一段时间后重试
                        time.sleep(0.5)
                    else:
                        # 最后一次尝试失败，返回错误
                        print(f"✗ 下单最终失败: {symbol} {side} {size}@{price}")
                        return None, order
                        
            except Exception as e:
                if attempt < max_retries:
                    print(f"⚠ 下单异常 (第{attempt + 1}次): {str(e)}")
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
        - 未提供的新参数将继承原订单（side/type/price/size/timeInForce/postOnly）
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
            od, oerr = self.get_order_status(order_id=order_id, symbol=full, keep_origin=True)
            if oerr is None and od.get('orderId', None) == order_id:
                existing_order = od
            else:
                return None, None
        except Exception:
            existing_order = None
            return None, None
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
        old_qty = _get(existing_order, ['origQty', 'quantity', 'size', 'qty'])
        old_price = _get(existing_order, ['price'])

        new_side = side if side is not None else old_side
        new_type = order_type if order_type is not None else old_type
        new_qty = size if size is not None else old_qty
        new_price = price if price is not None else old_price

        if not new_side:
            return None, ValueError("side not provided and cannot infer from existing order")
        if not new_type:
            new_type = 'LIMIT' if new_price is not None else 'MARKET'
        if not new_qty:
            return None, ValueError("size not provided and cannot infer from existing order")

        return self.place_order(
            symbol=full,
            side=new_side,
            order_type=new_type,
            size=str(new_qty),
            price=str(new_price) if new_price is not None else None,
            **kwargs
        )

    def revoke_order(self, order_id, symbol=None):
        if hasattr(self.account, "cancel_order"):
            if not symbol:
                return False, ValueError("symbol is required for cancel_order on OKX")
            full, _, _ = self._norm_symbol(symbol)
            try:
                resp = self.account.cancel_order(symbol=full, id=order_id)
                return True, None if resp is not None else (False, resp)
            except Exception as e:
                return False, e
        return False, NotImplementedError("Account.cancel_order unavailable")

    def get_order_status(self, order_id=None, symbol='ETH-USDT-SWAP', market_type=None, window=None, keep_origin=False):
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.account, "fetch_order"):
            return None, NotImplementedError("Account.fetch_order unavailable")
        try:
            resp = self.account.fetch_order(id=order_id, symbol=full)
            if keep_origin:
                if order_id is None:
                    return resp, None
                # 过滤指定 order_id
                if isinstance(resp, dict):
                    if str(resp.get('orderId')) == str(order_id):
                        return resp, None
                    return None, None
                if isinstance(resp, list):
                    for od in resp:
                        try:
                            if str(od.get('orderId')) == str(order_id):
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
                        if str(item.get('orderId')) == str(order_id):
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
                'orderId': od.get('orderId') or od.get('ordId'),
                'symbol': od.get('symbol') or od.get('market') or od.get('instId'),
                'side': (od.get('side') or '').lower() if od.get('side') else None,
                'orderType': (od.get('type') or '').lower() if (od.get('type')) else None,
                'price': _f(od.get('price')),
                'quantity': _f(od.get('origQty')),
                'filledQuantity': _f(od.get('executedQty')),
                'status': od.get('status'),
                'timeInForce': od.get('timeInForce') or od.get('time_in_force'),
                'postOnly': od.get('postOnly') or od.get('post_only'),
                'reduceOnly': od.get('reduceOnly') or od.get('reduce_only'),
                'clientId': od.get('clientOrderId') or od.get('client_id'),
                'createdAt': _f(od.get('time'), int),
                'updatedAt': _f(od.get('updateTime'), int),
                'raw': od,
            }
            return normalized, None
        except Exception as e:
            return None, e

    def get_open_orders(self, symbol=None, instType='SWAP', onlyOrderId=True, keep_origin=True):
        """
        获取未完成订单列表。
        :param symbol: 指定交易对；为空则返回全部（若底层支持）
        :param instType: 市场类型，默认 'SWAP'
        :param onlyOrderId: True 则仅返回订单号列表；False 返回完整订单对象列表
        :return: (result, error)
        """
        if hasattr(self.account, "fetch_open_orders"):
            try:
                if symbol:
                    try:
                        full, _, _ = self._norm_symbol(symbol)
                    except Exception as e:
                        full = symbol
                else:
                    full = symbol
                resp = self.account.fetch_open_orders(symbol=full)

                if onlyOrderId:
                    order_ids = []
                    # 兼容 list / dict 两种返回结构
                    if isinstance(resp, list):
                        for od in resp:
                            try:
                                oid = od.get('orderId') if isinstance(od, dict) else None
                                if oid is not None:
                                    order_ids.append(str(oid))
                            except Exception:
                                continue
                    elif isinstance(resp, dict):
                        data = resp.get('data')
                        if isinstance(data, list):
                            for od in data:
                                try:
                                    oid = od.get('orderId') if isinstance(od, dict) else None
                                    if oid is not None:
                                        order_ids.append(str(oid))
                                except Exception:
                                    continue
                        else:
                            # 单个订单或以键为订单号等情况
                            oid = resp.get('orderId')
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
                        'orderId': od.get('orderId') or od.get('ordId'),
                        'symbol': od.get('symbol') or od.get('market') or od.get('instId'),
                        'side': (od.get('side') or '').lower() if od.get('side') else None,
                        'orderType': (od.get('type') or '').lower() if (od.get('type')) else None,
                        'price': _f(od.get('price')),  # str -> float
                        'quantity': _f(od.get('origQty')),  # str -> float
                        'filledQuantity': _f(od.get('executedQty')),  # str -> float
                        'status': od.get('status'),
                        'timeInForce': od.get('timeInForce') or od.get('time_in_force'),
                        'postOnly': od.get('postOnly') or od.get('post_only'),
                        'reduceOnly': od.get('reduceOnly') or od.get('reduce_only'),
                        'clientId': od.get('clientOrderId') or od.get('client_id'),
                        'createdAt': _f(od.get('time'), int),
                        'updatedAt': _f(od.get('updateTime'), int),
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
            return None, Exception("Account client not available")

    def cancel_all(self, symbol=None, instType='SWAP', order_ids=None):
        """
        撤销指定交易对的所有未完成订单。
        :param symbol: 交易对；为空则撤销全部（若底层支持）
        :param instType: 市场类型，默认 'SWAP'
        :param order_ids: 若提供，则仅撤销这些订单号（若底层支持）
        :return: (result, error)
        """
        if hasattr(self.account, "cancel_all_orders"):
            try:
                if symbol:
                    try:
                        full, _, _ = self._norm_symbol(symbol)
                    except Exception as e:
                        full = symbol
                else:
                    full = symbol
                resp = self.account.cancel_all_orders(symbol=full)
                return resp, None
            except Exception as e:
                return None, e
        else:
            return None, Exception("Account client not available")

    # -------------- account --------------
    def fetch_balance(self, currency='USDT', instType='SWAP'):
        """
        获取账户余额。
        :param currency: 币种，默认 'USDT'
        :param instType: 市场类型，默认 'SWAP'
        :return: (balance, error)
        """
        if hasattr(self.account, "fetch_balance"):
            try:
                cur = (currency or "").upper()
                balance = self.account.fetch_balance()
                
                if cur in balance:
                    # 返回可用余额
                    return float(balance[cur].get('free', 0)), None
                return 0.0, None
            except Exception as e:
                return None, e
        else:
            return None, Exception("Account client not available")

    def get_position(self, symbol=None, instType='SWAP', keep_origin=True):
        """
        获取持仓信息。
        :param symbol: 交易对；为空则返回全部
        :param instType: 市场类型，默认 'SWAP'
        :param keep_origin: True 则返回原始结构；False 则返回统一结构
        :return: (result, error)
        """
        if self.mode == "spot":
            return [], None

        try:
            if hasattr(self.account, "fetch_positions"):
                positions = self.account.fetch_positions(symbols=[symbol] if symbol else None)
            else:
                return [], None
                
            if keep_origin:
                return positions, None
                
            out = []
            for p in positions or []:
                try:
                    qty = float(p.get("contracts") or 0.0)
                except Exception:
                    qty = 0.0
                side = "long" if qty > 0 else ("short" if qty < 0 else "flat")
                def _f(k):
                    try:
                        return float(p.get(k))
                    except Exception:
                        return None
                out.append({
                    "symbol": p.get("symbol"),
                    "positionId": None,
                    "side": side,
                    "quantity": abs(qty),
                    "entryPrice": _f("entryPrice"),
                    "markPrice": _f("markPrice"),
                    "pnlUnrealized": _f("unrealizedPnl"),
                    "pnlRealized": None,
                    "leverage": _f("leverage"),
                    "liquidationPrice": _f("liquidationPrice"),
                    "ts": None,
                })
            if symbol:
                for u in out:
                    if u["symbol"] == self._norm_symbol(symbol)[0]:
                        return u, None
            return out, None
        except Exception as e:
            return None, e

    def close_all_positions(self, symbol=None, instType='SWAP'):
        """
        平仓所有持仓（仅限期货）
        :param symbol: 交易对；为空则平仓全部
        :param instType: 市场类型，默认 'SWAP'
        :return: (result, error)
        """
        if self.mode == "spot":
            return {"ok": True, "message": "现货无持仓"}, None
        try:
            if hasattr(self.account, "fetch_positions"):
                positions = self.account.fetch_positions(symbols=[symbol] if symbol else None)
            else:
                return {"ok": False, "error": "fetch_positions not available"}, None
                
            for pos in positions or []:
                qty = float(pos.get("contracts", 0))
                if qty != 0:
                    # 平仓
                    side = "sell" if qty > 0 else "buy"
                    try:
                        self.account.create_order(
                            symbol=pos.get("symbol"),
                            side=side,
                            type="market",
                            amount=abs(qty)
                        )
                    except Exception as e:
                        print(f"平仓失败 {pos.get('symbol')}: {e}")
                        
            return {"ok": True}, None
        except Exception as e:
            return {"ok": False, "error": str(e)}, e

if __name__ == "__main__":
    driver = OKXDriver(account_id=0)
    print(driver.get_price_now(symbol='ETH-USDT-SWAP'))
