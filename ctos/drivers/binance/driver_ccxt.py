# -*- coding: utf-8 -*-
# ctos/drivers/binance/driver_ccxt.py
# Binance driver using ccxt library
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
    from ccxt import binance as ccxt_binance
except ImportError:
    raise RuntimeError("请先安装ccxt: pip install ccxt")

# Import account reader
try:
    from configs.account_reader import get_credentials_for_driver, list_accounts
except ImportError:
    # 如果无法导入，使用备用方案
    def get_credentials_for_driver(exchange, account='main'):
        return {
            'public_key': os.getenv("BINANCE_PUBLIC_KEY", os.getenv("BINANCE_API_KEY", "")),
            'secret_key': os.getenv("BINANCE_SECRET_KEY", os.getenv("BINANCE_API_SECRET", "")),
        }
    
    def list_accounts(exchange='binance'):
        return ['main', 'sub1', 'sub2']  # 默认账户列表

# Import account config reader
try:
    from configs.config_reader import get_ctos_config
except ImportError:
    def get_ctos_config():
        return None

def get_account_name_by_id(account_id=0, exchange='binance'):
    """
    根据账户ID获取账户名称
    
    Args:
        account_id: 账户ID
        exchange: 交易所名称
        
    Returns:
        str: 账户名称
    """
    try:
        accounts = list_accounts(exchange)
        
        if account_id < len(accounts):
            return accounts[account_id]
        else:
            print(f"警告: 账户ID {account_id} 超出范围，可用账户: {accounts}")
            return accounts[0] if accounts else 'main'
            
    except Exception as e:
        print(f"获取账户名称失败: {e}，使用默认映射")
        # 回退到默认映射
        default_mapping = {0: 'main', 1: 'sub1', 2: 'sub2'}
        return default_mapping.get(account_id, 'main')

def init_binance_clients(mode: str = "usdm", public_key: Optional[str] = None, secret_key: Optional[str] = None, account_id: int = 0):
    """
    初始化ccxt Binance客户端：
      mode = 'spot' 使用 okx spot
      mode = 'usdm' 使用 binance usdm futures (ccxt swap)
    优先使用传入的参数，其次从配置文件读取（根据account_id），最后从环境变量读取
    """
    # 1. 获取API凭证
    k = public_key or ""
    s = secret_key or ""
    
    # 如果参数未完全提供，尝试从配置文件读取（根据account_id）
    if not (k and s):
        try:
            account_name = get_account_name_by_id(account_id, 'binance')
            credentials = get_credentials_for_driver('binance', account_name)
            k = k or credentials.get('public_key', '') or credentials.get('api_key', '') or credentials.get('apiKey', '')
            s = s or credentials.get('secret_key', '') or credentials.get('api_secret', '') or credentials.get('secret', '')
            
            if k and s:
                print(f"从配置文件读取Binance账户: {account_name} (ID: {account_id})")
        except Exception as e:
            print(f"从配置文件读取账户信息失败: {e}，尝试使用环境变量")
    
    # 如果配置文件没有，尝试环境变量
    if not (k and s):
        k = k or os.getenv("BINANCE_PUBLIC_KEY") or os.getenv("BINANCE_API_KEY") or ""
        s = s or os.getenv("BINANCE_SECRET_KEY") or os.getenv("BINANCE_API_SECRET") or ""
    
    # 关键：strip 一下，避免末尾换行/空格导致 ccxt 认为是空
    k = (k or "").strip()
    s = (s or "").strip()
    
    # 检查是否所有凭证都已设置
    if not (k and s):
        raise ValueError(f"Binance API凭证未设置！请检查配置文件或环境变量。账户ID: {account_id}")
    
    # 2. 获取代理配置
    proxies = None
    try:
        configs = get_ctos_config()
        if configs is not None and 'proxies' in configs:
            proxies = configs.get('proxies')
            if proxies:
                print(f"从配置文件读取代理配置: {proxies}")
    except Exception as e:
        print(f"从配置文件读取代理配置失败: {e}")
    
    # 3. 构建ccxt配置（参考test_ccxt_driver.py的写法）
    config = {
        "apiKey": k,
        "secret": s,
        "enableRateLimit": True,
        "proxies": proxies,
        "options": {
            "adjustForTimeDifference": True,
            "defaultType": 'spot' if mode.lower() == "spot" else "swap",
            "warnOnFetchOpenOrdersWithoutSymbol": False
        }
    }
    
    # 4. 创建exchange实例
    if mode.lower() == "spot":
        exchange = ccxt_binance(config)
        return {"spot": exchange, "usdm": None}
    else:
        exchange = ccxt_binance(config)
        return {"spot": None, "usdm": exchange}


class BinanceDriver(TradingSyscalls):
    """
    CTOS Binance driver (ccxt connector).
    Mode-aware symbol normalization for Binance style symbols:
      - spot:  "BASE/QUOTE"           e.g. "BTC/USDT"
      - usdm:  "BASE/QUOTE"           e.g. "ETH/USDT"
    Accepts inputs like 'eth-usdt', 'ETH/USDT', 'ETHUSDT', 'eth', etc.
    """

    def __init__(self, binance_client=None, mode="usdm", default_quote="USDT",
                 price_scale=1e-8, size_scale=1e-8, account_id=0):
        self.cex = 'binance'
        self.quote_ccy = 'USDT'
        self.account_id = account_id
        """
        :param binance_client: Optional. An initialized ccxt exchange client.
        :param mode: "usdm" or "spot".
        :param default_quote: default quote when user passes 'ETH' without '/USDT'
        :param account_id: 账户ID，根据配置文件中的账户顺序映射 (0=第一个账户, 1=第二个账户, ...)
        """
        if binance_client is None:
            try:
                cli = init_binance_clients(mode=mode, account_id=account_id)
                self.binance = cli["usdm"] or cli["spot"]
                if self.binance:
                    print(f"✓ Binance Driver初始化成功 (账户ID: {account_id}, 模式: {mode})")
                else:
                    print(f"✗ Binance Driver初始化失败 (账户ID: {account_id})")
                    self.binance = None
            except Exception as e:
                print(f"✗ Binance Driver初始化失败 (账户ID: {account_id}): {e}")
                self.binance = None
        else:
            self.binance = binance_client
            print(f"✓ Binance Driver使用外部客户端 (账户ID: {account_id})")
        
        self.mode = (mode or "usdm").lower()
        self.default_quote = default_quote or "USDT"
        self.price_scale = price_scale
        self.size_scale = size_scale
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
        Normalize symbols to Binance CCXT format.
        Returns (full_symbol, base_lower, quote_upper)
        Examples:
          _norm_symbol('eth') -> ('ETH/USDT', 'eth', 'USDT')
          _norm_symbol('ETHUSDT') -> ('ETH/USDT', 'eth', 'USDT')
          _norm_symbol('SOL/USDT') -> ('SOL/USDT', 'sol', 'USDT')
        """
        s = str(symbol or "").strip()
        if not s:
            return None, None, None

        # unify separators to CCXT standard /
        su = s.replace("-", "/").replace("_", "/").upper()

        if "/" in su:
            parts = su.split("/")
            base = parts[0]
            quote = parts[1] if len(parts) > 1 else self.default_quote
        elif su.endswith("USDT"):
            base, quote = su[:-4], "USDT"
        elif su.endswith("BUSD"):
            base, quote = su[:-4], "BUSD"
        else:
            # Only base provided
            base = su
            quote = self.default_quote

        full = f"{base}/{quote}"
        if self.mode == "usdm":
            full += f":{quote}"

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
    def symbols(self, instType='USDM'):
        """
        返回指定类型的交易对列表。
        :param instType: 'USDM' | 'SPOT' 等，默认 'USDM'
        :return: list[str]，如 ['BTC/USDT', 'ETH/USDT', ...]
        """
        if self.binance is None:
            # 兜底：无法从底层获取时，返回少量默认
            return ["BTC/USDT", "ETH/USDT"] if str(instType).upper() == 'USDM' else ["BTC/USDT", "ETH/USDT"]

        try:
            markets = self.binance.load_markets()
            if self.mode == "spot":
                # 现货市场
                syms = [symbol for symbol, market in markets.items() 
                       if market.get('type') == 'spot' and market.get('active', True)]
            else:
                # 期货市场 (Binance USDM in CCXT is 'swap')
                syms = [symbol for symbol, market in markets.items() 
                       if market.get('type') == 'swap' and market.get('active', True)]
            return syms, None
        except Exception as e:
            return [], e

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
            markets = self.binance.load_markets()
            
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
                if self.mode == "usdm" and market.get('type') != 'swap':
                    continue # Binance USDM is 'swap' in CCXT
                    
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
                'instType': 'USDM' if self.mode == 'usdm' else 'SPOT',
                'price_precision': price_precision,
                'size_precision': size_precision,
                'min_order_size': min_qty,
                'contract_value': 1.0,
                'max_leverage': 125.0 if self.mode == 'usdm' else 1.0,
                'state': 'live' if market.get('active', True) else 'inactive',
                'raw': market
            }
        except Exception as e:
            return {"error": f"解析market信息时发生异常: {str(e)}"}

    def fees(self, symbol='ETH-USDT-SWAP', instType='SWAP', keep_origin=False):
        """
        获取资金费率信息。
        - 对于 OKX，使用 fetch_funding_rate() 方法
        - 返回 (result, error)
        - 统一返回结构到"每小时资金费率"。
        """
        if not hasattr(self.binance, 'fetch_funding_rate'):
            return None, NotImplementedError('Public.fetch_funding_rate unavailable')

        full, _, _ = self._norm_symbol(symbol)
        if self.mode != "usdm":
            return {"symbol": full, "instType": "SPOT", "fundingRate_hourly": None, "raw": None}, None
        
        try:
            raw = self.binance.fetch_funding_rate(symbol=full)
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
    def get_price_now(self, symbol='ETH/USDT'):
        full, base, _ = self._norm_symbol(symbol)
        if hasattr(self.binance, "fetch_ticker"):
            try:
                data = self.binance.fetch_ticker(symbol=full)
                # ccxt返回格式: {'symbol': 'BTC-USDT-SWAP', 'last': 2000.0, 'bid': 1999.0, 'ask': 2001.0, ...}
                if isinstance(data, dict):
                    price = data.get('last') or data.get('close')
                    if price is not None:
                        return float(price)
            except Exception as e:
                raise e
        raise NotImplementedError("Public.fetch_ticker unavailable or response lacks price")

    def get_orderbook(self, symbol='ETH/USDT', level=50):
        full, _, _ = self._norm_symbol(symbol)
        if hasattr(self.binance, "fetch_order_book"):
            try:
                raw = self.binance.fetch_order_book(symbol=full, limit=int(level))
                bids = raw.get("bids", []) if isinstance(raw, dict) else []
                asks = raw.get("asks", []) if isinstance(raw, dict) else []
                return {"symbol": full, "bids": bids, "asks": asks}
            except Exception as e:
                raise e
        raise NotImplementedError("Public.fetch_order_book unavailable")

    def get_klines(self, symbol='ETH/USDT', timeframe='1h', limit=200):
        """
        Normalize to list of dicts:
        [{'ts': ts_ms, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': v}, ...]
        """
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.binance, "fetch_ohlcv"):
            raise NotImplementedError("Public.fetch_ohlcv unavailable")

        try:
            # 拉取原始数据
            raw = self.binance.fetch_ohlcv(symbol=full, timeframe=timeframe, limit=int(limit))
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

        # 优先返回 pandas.DataFrame（与driver.py保持一致）
        try:
            df = pd.DataFrame.from_records(records, columns=['trade_date', 'open', 'high', 'low', 'close', 'vol1', 'vol'])
            return df, None
        except Exception:
            # 退化为列表
            return records, None

    # -------------- trading --------------
    def place_order(self, symbol, side, order_type, size, price=None, client_id=None, **kwargs):
        """
        Normalize inputs to your okex client.
        """
        full, _, _ = self._norm_symbol(symbol)
        if not hasattr(self.binance, "create_order"):
            raise NotImplementedError("binance client lacks create_order(...)")

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

            order = self.binance.create_order(**params)
            
            # 检查下单结果
            if isinstance(order, dict) and ('id' in order or 'orderId' in order):
                order_id = order.get('id') or order.get('orderId')
                return str(order_id), None
            else:
                return None, order
        except Exception as e:
            return None, e

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
        if hasattr(self.binance, "cancel_order"):
            if not symbol:
                return False, ValueError("symbol is required for cancel_order on Binance")
            full, _, _ = self._norm_symbol(symbol)
            try:
                resp = self.binance.cancel_order(symbol=full, id=order_id)
                return True, None if resp is not None else (False, resp)
            except Exception as e:
                return False, e
        return False, NotImplementedError("Account.cancel_order unavailable")

    def get_order_status(self, order_id, symbol=None, keep_origin=False):
        if not hasattr(self.binance, "fetch_order"):
            raise NotImplementedError("Account.fetch_order unavailable")
        
        if not symbol:
            symbol = self.order_id_to_symbol.get(order_id, None)
        
        full = None
        if symbol:
            full, _, _ = self._norm_symbol(symbol)
        
        try:
            resp = self.binance.fetch_order(id=order_id, symbol=full)
            if keep_origin:
                if order_id is None:
                    return resp, None
                # 过滤指定 order_id - 支持多种ID字段
                def _match_order_id(od, target_id):
                    """检查订单是否匹配目标ID"""
                    if not isinstance(od, dict):
                        return False
                    # 尝试多种ID字段
                    od_id = od.get('id') or od.get('orderId') or od.get('ordId')
                    return str(od_id) == str(target_id) if od_id is not None else False
                
                if isinstance(resp, dict):
                    if _match_order_id(resp, order_id):
                        return resp, None
                    return None, None
                if isinstance(resp, list):
                    for od in resp:
                        try:
                            if _match_order_id(od, order_id):
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
                        # 支持多种ID字段匹配
                        item_id = item.get('id') or item.get('orderId') or item.get('ordId')
                        if item_id and str(item_id) == str(order_id):
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
                'orderId': od.get('id') or od.get('orderId') or od.get('ordId'),
                'symbol': od.get('symbol') or od.get('market') or od.get('instId'),
                'side': (od.get('side') or '').lower() if od.get('side') else None,
                'orderType': (od.get('type') or od.get('ordType') or '').lower() if (od.get('type') or od.get('ordType')) else None,
                'price': _f(od.get('price') or od.get('px')),
                'quantity': _f(od.get('amount') or od.get('origQty') or od.get('quantity') or od.get('size') or od.get('sz')),
                'filledQuantity': _f(od.get('filled') or od.get('executedQty') or od.get('filledSize') or od.get('accFillSz')),
                'status': od.get('status') or od.get('state'),
                'timeInForce': od.get('timeInForce') or od.get('time_in_force'),
                'postOnly': od.get('postOnly') or od.get('post_only'),
                'reduceOnly': od.get('reduceOnly') or od.get('reduce_only'),
                'clientId': od.get('clientOrderId') or od.get('client_id') or od.get('clOrdId'),
                'createdAt': _f(od.get('timestamp') or od.get('time') or od.get('cTime'), int),
                'updatedAt': _f(od.get('lastUpdateTimestamp') or od.get('updateTime') or od.get('uTime'), int),
                'raw': od,
            }
            return normalized, None
        except Exception as e:
            return None, e

    def get_open_orders(self, symbol=None, instType='USDM', onlyOrderId=True, keep_origin=True):
        """
        获取未完成订单列表。
        :param symbol: 指定交易对；为空则返回全部（若底层支持）
        :param instType: 市场类型，默认 'USDM'
        :param onlyOrderId: True 则仅返回订单号列表；False 返回完整订单对象列表
        :return: (result, error)
        """
        if hasattr(self.binance, "fetch_open_orders"):
            try:
                if symbol:
                    try:
                        full, _, _ = self._norm_symbol(symbol)
                    except Exception as e:
                        full = symbol
                else:
                    full = symbol
                resp = self.binance.fetch_open_orders(symbol=full)

                if onlyOrderId:
                    order_ids = []
                    # 兼容 list / dict 两种返回结构
                    if isinstance(resp, list):
                        for od in resp:
                            try:
                                if isinstance(od, dict):
                                    # ccxt返回的订单ID可能在'id'或'orderId'字段
                                    oid = od.get('id') or od.get('orderId') or od.get('ordId')
                                    if oid is not None:
                                        order_ids.append(str(oid))
                            except Exception:
                                continue
                    elif isinstance(resp, dict):
                        data = resp.get('data')
                        if isinstance(data, list):
                            for od in data:
                                try:
                                    if isinstance(od, dict):
                                        oid = od.get('id') or od.get('orderId') or od.get('ordId')
                                        if oid is not None:
                                            order_ids.append(str(oid))
                                except Exception:
                                    continue
                        else:
                            # 单个订单或以键为订单号等情况
                            oid = resp.get('id') or resp.get('orderId') or resp.get('ordId')
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
                        'orderId': od.get('id') or od.get('orderId') or od.get('ordId'),
                        'symbol': od.get('symbol') or od.get('market') or od.get('instId'),
                        'side': (od.get('side') or '').lower() if od.get('side') else None,
                        'orderType': (od.get('type') or od.get('ordType') or '').lower() if (od.get('type') or od.get('ordType')) else None,
                        'price': _f(od.get('price') or od.get('px')),  # str -> float
                        'quantity': _f(od.get('amount') or od.get('origQty') or od.get('quantity') or od.get('size') or od.get('sz')),  # str -> float
                        'filledQuantity': _f(od.get('filled') or od.get('executedQty') or od.get('filledSize') or od.get('accFillSz')),  # str -> float
                        'status': od.get('status') or od.get('state'),
                        'timeInForce': od.get('timeInForce') or od.get('time_in_force'),
                        'postOnly': od.get('postOnly') or od.get('post_only'),
                        'reduceOnly': od.get('reduceOnly') or od.get('reduce_only'),
                        'clientId': od.get('clientOrderId') or od.get('client_id') or od.get('clOrdId'),
                        'createdAt': _f(od.get('timestamp') or od.get('time') or od.get('cTime'), int),
                        'updatedAt': _f(od.get('lastUpdateTimestamp') or od.get('updateTime') or od.get('uTime'), int),
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

    def cancel_all(self, symbol=None, instType='USDM', order_ids=None):
        """
        撤销指定交易对的所有未完成订单。
        :param symbol: 交易对；为空则撤销全部（若底层支持）
        :param instType: 市场类型，默认 'USDM'
        :param order_ids: 若提供，则仅撤销这些订单号（若底层支持）
        :return: (result, error)
        """
        if not self.binance:
            return None, Exception("Account client not available")

        # 1. 如果提供了 order_ids，优先处理
        if order_ids:
            results = []
            for oid in order_ids:
                res, err = self.revoke_order(oid, symbol=symbol)
                results.append(res if err is None else err)
            return results, None

        # 2. 尝试使用 ccxt 原生的 cancel_all_orders
        if symbol and hasattr(self.binance, "cancel_all_orders"):
            try:
                full = self._norm_symbol(symbol)[0]
                resp = self.binance.cancel_all_orders(symbol=full)
                return resp, None
            except Exception as e:
                # 如果 ccxt 提示不支持，则进入手动撤单逻辑
                if "not supported" not in str(e).lower():
                    return None, e

        # 3. 手动撤单逻辑：获取所有挂单并逐个撤销
        open_orders, err = self.get_open_orders(symbol=symbol, instType=instType, onlyOrderId=False, keep_origin=False)
        if err:
            return None, err
        
        results = []
        for od in open_orders:
            oid = od.get('orderId')
            osym = od.get('symbol')
            res, err = self.revoke_order(oid, symbol=osym)
            results.append(res if err is None else err)
        return results, None

    # -------------- account --------------
    def fetch_balance(self, currency='USDT'):
        """
        Return a simple flat dict. If only jiaoyi/zijin are available,
        expose USDT buckets and a best-effort total in USD.
        """
        if hasattr(self.binance, "fetch_balance"):
            try:
                # ccxt的fetch_balance返回所有币种余额
                raw = self.binance.fetch_balance()
                if isinstance(raw, dict):
                    # 如果指定了currency，返回该币种的总计余额
                    cur = (currency or "USDT").upper()
                    if cur in raw:
                        balance_info = raw[cur]
                        if isinstance(balance_info, dict):
                            # 返回总计余额
                            total = balance_info.get('total', 0)
                            return float(total) if total is not None else 0.0
                    # 如果没有找到指定币种，返回整个字典
                    return raw
                return raw
            except Exception as e:
                return e
        raise NotImplementedError("Account.fetch_balance unavailable")

    def get_position(self, symbol=None, keep_origin=False, instType='USDM'):
        """
        获取持仓信息。
        :param symbol: 交易对；为空则返回全部
        :param instType: 市场类型，默认 'USDM'
        :param keep_origin: True 则返回原始结构；False 则返回统一结构
        :return: (result, error)
        """
        if self.mode == "spot":
            return [], None

        try:
            if hasattr(self.binance, "fetch_positions"):
                positions = self.binance.fetch_positions(symbols=[symbol] if symbol else None)
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

    def close_all_positions(self, symbol=None, instType='USDM'):
        """
        平仓所有持仓（仅限期货）
        :param symbol: 交易对；为空则平仓全部
        :param instType: 市场类型，默认 'USDM'
        :return: (result, error)
        """
        if self.mode == "spot":
            return {"ok": True, "message": "现货无持仓"}, None
        try:
            if hasattr(self.binance, "fetch_positions"):
                positions = self.binance.fetch_positions(symbols=[symbol] if symbol else None)
            else:
                return {"ok": False, "error": "fetch_positions not available"}, None
                
            for pos in positions or []:
                qty = float(pos.get("contracts", 0))
                if qty != 0:
                    # 平仓
                    side = "sell" if qty > 0 else "buy"
                    try:
                        self.binance.create_order(
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
    driver = BinanceDriver(account_id=0)
    print(driver.get_price_now(symbol='ETH/USDT'))
