# -*- coding: utf-8 -*-
# tests/test_okx_driver.py

import os
import sys
from pathlib import Path

# Ensure project root (which contains the `ctos/` package directory) is on sys.path
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[1]  # repo root containing the top-level `ctos/` package dir
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ctos.drivers.okx.driver import OkxDriver, init_OkxClient
from ctos.drivers.okx.okex import *
from ctos.drivers.okx.util import *


okx = OkxDriver()
symbol = os.getenv("OKX_TEST_SYMBOL", "ETH-USDT-SWAP")


print(okx)
print("\n\n[OKX_TEST] before call: get_price_now")
try:
    res = okx.get_price_now('ETH-USDT-SWAP')
    print("\n\n[OKX_TEST] after call: get_price_now ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: get_price_now raised:", e)

print("\n\n[OKX_TEST] before call: get_orderbook")
try:
    res = okx.get_orderbook('ETH-USDT-SWAP', level=5)['symbol']
    print("\n\n[OKX_TEST] after call: get_orderbook ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: get_orderbook raised:", e)

print("\n\n[OKX_TEST] before call: get_klines")
try:
    res = okx.get_klines('ETH-USDT-SWAP', timeframe='1h', limit=20)
    print("\n\n[OKX_TEST] after call: get_klines ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: get_klines raised:", e)

print("\n\n[OKX_TEST] before call: place_order")
try:
    res = okx.place_order('ETH-USDT-SWAP', side='buy', order_type='limit', size=0.01, price=okx.get_price_now('ETH-USDT-SWAP')*0.9)
    order_id, err  = res
    print("\n\n[OKX_TEST] after call: place_order ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: place_order raised:", e)

print("\n\n[OKX_TEST] before call: amend_order")
try:
    res = okx.amend_order(order_id, price=okx.get_price_now('ETH-USDT-SWAP')*0.8)
    order_id, err  = res
    print("\n\n[OKX_TEST] after call: amend_order ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: amend_order raised:", e)

print("\n\n[OKX_TEST] before call: get_order_status")
try:
    res = okx.get_order_status(order_id, keep_origin=False)
    print("\n\n[OKX_TEST] after call: get_order_status ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: get_order_status raised:", e)

print("\n\n[OKX_TEST] before call: get_open_orders only Orderids")
try:
    res = okx.get_open_orders(symbol='ETH-USDT-SWAP',  onlyOrderId=True, keep_origin=False)
    print("\n\n[OKX_TEST] after call: get_open_orders ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: get_open_orders raised:", e)


print("\n\n[OKX_TEST] before call: get_open_orders all infos")
try:
    res = okx.get_open_orders(symbol='ETH-USDT-SWAP', onlyOrderId=False, keep_origin=False)
    print("\n\n[OKX_TEST] after call: get_open_orders ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: get_open_orders raised:", e)


print("\n\n[OKX_TEST] before call: revoke_order")
try:
    res = okx.revoke_order(order_id)
    print("\n\n[OKX_TEST] after call: revoke_order ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: revoke_order raised:", e)

print("\n\n[OKX_TEST] before call: cancel_all (no symbol)")
try:
    res = okx.cancel_all()
    print("\n\n[OKX_TEST] after call: cancel_all (no symbol) ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: cancel_all (no symbol) raised:", e)

print("\n\n[OKX_TEST] before call: cancel_all (with symbol)")
try:
    res = okx.cancel_all('ETH-USDT-SWAP')
    print("\n\n[OKX_TEST] after call: cancel_all (with symbol) ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: cancel_all (with symbol) raised:", e)

print("\n\n[OKX_TEST] before call: fetch_balance")
try:
    res = okx.fetch_balance('USDT')
    print("\n\n[OKX_TEST] after call: fetch_balance ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: fetch_balance raised:", e)

print("\n\n[OKX_TEST] before call: get_position")
try:
    res = len(okx.get_position(keep_origin=False)[0])
    print("\n\n[OKX_TEST] after call: get_position ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: get_position raised:", e)

print("\n\n[OKX_TEST] before call: get_position keep_origin")
try:
    res = okx.get_position(symbol, keep_origin=True)
    print("\n\n[OKX_TEST] after call: get_position ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: get_position raised:", e)


print("\n\n[OKX_TEST] before call: symbols")
try:
    res = okx.symbols()[0][:10]
    print("\n\n[OKX_TEST] after call: symbols ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: symbols raised:", e)

print("\n\n[OKX_TEST] before call: exchange_limits")
try:
    res = okx.exchange_limits()
    print("\n\n[OKX_TEST] after call: exchange_limits ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: exchange_limits raised:", e)

print("\n\n[OKX_TEST] before call: fees")
try:
    res = okx.fees()
    print("\n\n[OKX_TEST] after call: fees ->", res)
except Exception as e:
    print("\n\n[OKX_TEST] after call: fees raised:", e)

