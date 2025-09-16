# -*- coding: utf-8 -*-
# tests/test_bp_driver.py

import os
import sys
from pathlib import Path

# Ensure project root (which contains the `ctos/` package directory) is on sys.path
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ctos.drivers.backpack.driver import BackpackDriver
from ctos.drivers.okx.util import align_decimal_places


bp = BackpackDriver(mode=os.getenv("BP_TEST_MODE", "perp"))

symbol = os.getenv("BP_TEST_SYMBOL", "ETH_USDC_PERP")

print(bp)

print("[BP_TEST] before call: get_price_now")
try:
    res = bp.get_price_now(symbol)
    print("[BP_TEST] after call: get_price_now ->", res)
except Exception as e:
    print("[BP_TEST] after call: get_price_now raised:", e)

print("[BP_TEST] before call: get_orderbook")
try:
    res = bp.get_orderbook(symbol, level=1)['symbol']
    print("[BP_TEST] after call: get_orderbook ->", res)
except Exception as e:
    print("[BP_TEST] after call: get_orderbook raised:", e)

print("[BP_TEST] before call: get_klines")
try:
    res = bp.get_klines(symbol, timeframe=os.getenv("BP_TEST_TIMEFRAME", "1h"), limit=int(os.getenv("BP_TEST_LIMIT", "20")))
    print("[BP_TEST] after call: get_klines ->", res)
except Exception as e:
    print("[BP_TEST] after call: get_klines raised:", e)

print("[BP_TEST] before call: place_order")
try:
    last = None
    try:
        last = bp.get_price_now(symbol)
    except Exception:
        pass
    price = align_decimal_places(last, last * 0.9  if isinstance(last, (int, float)) else None)
    res = bp.place_order(symbol, side='buy', order_type='limit' if price else 'market', size=0.01, price=price)
    order_id, err = res
    print("[BP_TEST] after call: place_order ->", res)
except Exception as e:
    order_id = None
    print("[BP_TEST] after call: place_order raised:", e)

print("[BP_TEST] before call: amend_order")
try:
    if order_id:
        last = bp.get_price_now(symbol)
        res = bp.amend_order(order_id, symbol=symbol, price=align_decimal_places(last, last * 0.88))
        order_id, err = res
        print("[BP_TEST] after call: amend_order ->", res)
    else:
        print("[BP_TEST] amend_order skipped: no order_id")
except Exception as e:
    print("[BP_TEST] after call: amend_order raised:", e)

print("[BP_TEST] before call: get_order_status")
try:
    if order_id:
        res = bp.get_order_status(order_id, symbol=symbol, keep_origin=False)
        print("[BP_TEST] after call: get_order_status ->", res)
    else:
        print("[BP_TEST] get_order_status skipped: no order_id")
except Exception as e:
    print("[BP_TEST] after call: get_order_status raised:", e)

print("[BP_TEST] before call: get_open_orders only Orderids")
try:
    res = bp.get_open_orders(symbol='eth', keep_origin=False)
    print("[BP_TEST] after call: get_open_orders ->", res)
except Exception as e:
    print("[BP_TEST] after call: get_open_orders raised:", e)


print("[BP_TEST] before call: get_open_orders all infos")
try:
    res = bp.get_open_orders(symbol='eth', onlyOrderId=False, keep_origin=False)
    print("[BP_TEST] after call: get_open_orders ->", res)
except Exception as e:
    print("[BP_TEST] after call: get_open_orders raised:", e)


print("[BP_TEST] before call: revoke_order")
try:
    if order_id:
        res = bp.revoke_order(order_id, symbol=symbol)
        print("[BP_TEST] after call: revoke_order ->", res)
    else:
        print("[BP_TEST] revoke_order skipped: no order_id")
except Exception as e:
    print("[BP_TEST] after call: revoke_order raised:", e)

print("[BP_TEST] before call: cancel_all (no symbol)")
try:
    res = bp.cancel_all()
    print("[BP_TEST] after call: cancel_all (no symbol) ->", res)
except Exception as e:
    print("[BP_TEST] after call: cancel_all (no symbol) raised:", e)

print("[BP_TEST] before call: cancel_all (with symbol)")
try:
    res = bp.cancel_all(symbol)
    print("[BP_TEST] after call: cancel_all (with symbol) ->", res)
except Exception as e:
    print("[BP_TEST] after call: cancel_all (with symbol) raised:", e)

print("[BP_TEST] before call: fetch_balance")
try:
    res = bp.fetch_balance('USDC')
    print("[BP_TEST] after call: fetch_balance ->", res)
except Exception as e:
    print("[BP_TEST] after call: fetch_balance raised:", e)

print("[BP_TEST] before call: get_position")
try:
    res = bp.get_position(symbol, keep_origin=False)
    print("[BP_TEST] after call: get_position ->", res)
except Exception as e:
    print("[BP_TEST] after call: get_position raised:", e)

print("[BP_TEST] before call: symbols")
try:
    res = bp.symbols()[0][:10]
    print("[BP_TEST] after call: symbols ->", res)
except Exception as e:
    print("[BP_TEST] after call: symbols raised:", e)

print("[BP_TEST] before call: exchange_limits")
try:
    res = bp.exchange_limits()
    print("[BP_TEST] after call: exchange_limits ->", res)
except Exception as e:
    print("[BP_TEST] after call: exchange_limits raised:", e)

print("[BP_TEST] before call: fees")
try:
    res = bp.fees(symbol)
    print("[BP_TEST] after call: fees ->", res)
except Exception as e:
    print("[BP_TEST] after call: fees raised:", e)