# -*- coding: utf-8 -*-
# tests/test_okx_driver_ccxt.py
# 测试 ccxt 版本的 OKX Driver 接口功能

import os
import sys
from pathlib import Path

# Ensure project root (which contains the `ctos/` package directory) is on sys.path
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[1]  # repo root containing the top-level `ctos/` package dir
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ctos.drivers.okx.driver_ccxt import OkxDriver

# 初始化 ccxt 版本的 OKX Driver
okx = OkxDriver()
symbol = os.getenv("OKX_TEST_SYMBOL", "ETH-USDT-SWAP")

print("=" * 80)
print("OKX CCXT Driver 接口功能测试")
print("=" * 80)
print(f"Driver: {okx}")
print(f"测试交易对: {symbol}")
print("=" * 80)

# 测试 1: get_price_now
print("\n[TEST 1] get_price_now")
print("-" * 80)
try:
    res = okx.get_price_now(symbol)
    print(f"✓ 成功: {res}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 2: get_orderbook
print("\n[TEST 2] get_orderbook")
print("-" * 80)
try:
    res = okx.get_orderbook(symbol, level=5)
    print(f"✓ 成功: symbol={res['symbol']}, bids数量={len(res['bids'])}, asks数量={len(res['asks'])}")
    print(f"  示例: bid={res['bids'][0] if res['bids'] else 'N/A'}, ask={res['asks'][0] if res['asks'] else 'N/A'}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 3: get_klines
print("\n[TEST 3] get_klines")
print("-" * 80)
try:
    res, err = okx.get_klines(symbol, timeframe='1h', limit=20)
    if err:
        print(f"✗ 错误: {err}")
    else:
        if hasattr(res, 'shape'):  # DataFrame
            print(f"✓ 成功: DataFrame, shape={res.shape}")
            print(f"  前5行:")
            print(res.head())
        else:  # List
            print(f"✓ 成功: List, 长度={len(res)}")
            print(f"  前3条: {res[:3]}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 4: place_order (限价买单，价格低于当前价90%)
print("\n[TEST 4] place_order (限价买单)")
print("-" * 80)
order_id = None
try:
    current_price = okx.get_price_now(symbol)
    test_price = current_price * 0.9  # 低于当前价10%
    res = okx.place_order(symbol, side='buy', order_type='limit', size=0.01, price=test_price)
    order_id, err = res
    if err:
        print(f"✗ 错误: {err}")
    else:
        print(f"✓ 成功: order_id={order_id}, price={test_price:.2f}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 5: amend_order (修改订单价格)
print("\n[TEST 5] amend_order")
print("-" * 80)
if order_id:
    try:
        current_price = okx.get_price_now(symbol)
        new_price = current_price * 0.8  # 低于当前价20%
        res = okx.amend_order(order_id, symbol=symbol, price=new_price)
        new_order_id, err = res
        if err:
            print(f"✗ 错误: {err}")
        else:
            # 如果新订单ID为None，保留旧的order_id用于后续测试
            if new_order_id:
                print(f"✓ 成功: new_order_id={new_order_id}, new_price={new_price:.2f}")
                order_id = new_order_id  # 更新 order_id
            else:
                print(f"⚠ 警告: new_order_id=None，保留原order_id={order_id}用于后续测试, new_price={new_price:.2f}")
    except Exception as e:
        print(f"✗ 失败: {e}")
else:
    print("⚠ 跳过: 没有可用的 order_id")

# 测试 6: get_order_status
print("\n[TEST 6] get_order_status")
print("-" * 80)
if order_id:
    try:
        res, err = okx.get_order_status(order_id, symbol=symbol, keep_origin=False)
        if err:
            print(f"✗ 错误: {err}")
        else:
            if res:
                order_id_from_res = res.get('orderId')
                if order_id_from_res:
                    print(f"✓ 成功: orderId={order_id_from_res}, status={res.get('status')}, "
                          f"side={res.get('side')}, price={res.get('price')}, quantity={res.get('quantity')}")
                else:
                    # 如果orderId为None，打印原始数据
                    raw_data = res.get('raw', res)
                    print(f"⚠ orderId为None，原始数据:")
                    print(f"   查询的order_id: {order_id}")
                    print(f"   原始数据keys: {list(raw_data.keys())[:20] if isinstance(raw_data, dict) else 'N/A'}")
                    # 尝试从原始数据中查找可能的ID字段
                    if isinstance(raw_data, dict):
                        possible_ids = {
                            'id': raw_data.get('id'),
                            'orderId': raw_data.get('orderId'),
                            'ordId': raw_data.get('ordId'),
                            'clientOrderId': raw_data.get('clientOrderId'),
                            'clOrdId': raw_data.get('clOrdId'),
                        }
                        found_ids = {k: v for k, v in possible_ids.items() if v is not None}
                        if found_ids:
                            print(f"   找到的ID字段: {found_ids}")
                        else:
                            print(f"   未找到任何ID字段")
            else:
                print("⚠ 订单不存在或已取消")
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        print(f"   详细错误: {traceback.format_exc()}")
else:
    print("⚠ 跳过: 没有可用的 order_id")

# 测试 7: get_open_orders (仅订单ID)
print("\n[TEST 7] get_open_orders (仅订单ID)")
print("-" * 80)
try:
    res, err = okx.get_open_orders(symbol=symbol, onlyOrderId=True, keep_origin=True)
    if err:
        print(f"✗ 错误: {err}")
    else:
        # 处理返回结果：可能是列表或字典
        if isinstance(res, list):
            print(f"✓ 成功: 订单数量={len(res)}, 订单ID列表={res[:5] if len(res) > 5 else res}")
        elif isinstance(res, dict):
            # 如果是字典，尝试提取订单ID
            data = res.get('data', res)
            if isinstance(data, list):
                order_ids = [str(od.get('orderId') or od.get('ordId', '')) for od in data if isinstance(od, dict)]
                print(f"✓ 成功: 订单数量={len(order_ids)}, 订单ID列表={order_ids[:5] if len(order_ids) > 5 else order_ids}")
            else:
                print(f"✓ 成功: {res}")
        else:
            print(f"✓ 成功: {res}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 8: get_open_orders (完整信息)
print("\n[TEST 8] get_open_orders (完整信息)")
print("-" * 80)
try:
    res, err = okx.get_open_orders(symbol=symbol, onlyOrderId=False, keep_origin=False)
    if err:
        print(f"✗ 错误: {err}")
    else:
        print(f"✓ 成功: 订单数量={len(res)}")
        if res:
            first_order = res[0]
            order_id = first_order.get('orderId')
            if order_id:
                print(f"  第一个订单: orderId={order_id}, "
                      f"status={first_order.get('status')}, side={first_order.get('side')}")
            else:
                # 如果拿不到orderId，打印原始数据
                raw_data = first_order.get('raw', first_order)
                print(f"  ⚠ 第一个订单orderId为None，原始数据:")
                print(f"    {raw_data}")
                # 尝试从原始数据中查找可能的ID字段
                if isinstance(raw_data, dict):
                    possible_ids = {
                        'id': raw_data.get('id'),
                        'orderId': raw_data.get('orderId'),
                        'ordId': raw_data.get('ordId'),
                        'clientOrderId': raw_data.get('clientOrderId'),
                        'clOrdId': raw_data.get('clOrdId'),
                    }
                    found_ids = {k: v for k, v in possible_ids.items() if v is not None}
                    if found_ids:
                        print(f"    找到的ID字段: {found_ids}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 9: revoke_order
print("\n[TEST 9] revoke_order")
print("-" * 80)
# 如果没有order_id，尝试从get_open_orders获取一个
if not order_id:
    try:
        open_orders, _ = okx.get_open_orders(symbol=symbol, onlyOrderId=True, keep_origin=True)
        if isinstance(open_orders, list) and open_orders:
            order_id = open_orders[0]
            print(f"ℹ 从get_open_orders获取order_id: {order_id}")
        elif isinstance(open_orders, dict):
            data = open_orders.get('data', open_orders)
            if isinstance(data, list) and data:
                order_id = str(data[0].get('orderId') or data[0].get('ordId', ''))
                print(f"ℹ 从get_open_orders获取order_id: {order_id}")
    except Exception as e:
        print(f"⚠ 无法获取order_id: {e}")

if order_id:
    try:
        res, err = okx.revoke_order(order_id, symbol=symbol)
        if err:
            print(f"✗ 错误: {err}")
        else:
            print(f"✓ 成功: {res}")
    except Exception as e:
        print(f"✗ 失败: {e}")
else:
    print("⚠ 跳过: 没有可用的 order_id")

# 测试 10: cancel_all (无symbol参数)
print("\n[TEST 10] cancel_all (无symbol参数)")
print("-" * 80)
try:
    res, err = okx.cancel_all()
    if err:
        print(f"✗ 错误: {err}")
    else:
        print(f"✓ 成功: {res}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 11: cancel_all (带symbol参数)
print("\n[TEST 11] cancel_all (带symbol参数)")
print("-" * 80)
try:
    res, err = okx.cancel_all(symbol=symbol)
    if err:
        print(f"✗ 错误: {err}")
    else:
        print(f"✓ 成功: {res}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 12: fetch_balance
print("\n[TEST 12] fetch_balance")
print("-" * 80)
try:
    res = okx.fetch_balance('USDT')
    if isinstance(res, Exception):
        print(f"✗ 错误: {res}")
    else:
        if isinstance(res, dict):
            # ccxt返回的余额格式
            usdt_balance = res.get('USDT', {})
            if isinstance(usdt_balance, dict):
                free = usdt_balance.get('free', 0)
                used = usdt_balance.get('used', 0)
                total = usdt_balance.get('total', 0)
                print(f"✓ 成功: USDT余额 - 可用={free}, 已用={used}, 总计={total}")
            else:
                # 可能是其他格式
                print(f"✓ 成功: USDT={usdt_balance}, 完整数据keys={list(res.keys())[:10]}")
        elif isinstance(res, (int, float)):
            print(f"✓ 成功: USDT余额={res}")
        else:
            print(f"✓ 成功: {res} (类型: {type(res).__name__})")
except Exception as e:
    print(f"✗ 失败: {e}")
    import traceback
    print(f"   详细错误: {traceback.format_exc()}")

# 测试 13: get_position (keep_origin=False)
print("\n[TEST 13] get_position (keep_origin=False)")
print("-" * 80)
try:
    res, err = okx.get_position(keep_origin=False)
    if err:
        print(f"✗ 错误: {err}")
    else:
        if isinstance(res, list):
            print(f"✓ 成功: 持仓数量={len(res)}")
            if res:
                first_pos = res[0] if isinstance(res[0], dict) else res
                print(f"  第一个持仓: symbol={first_pos.get('symbol')}, "
                      f"side={first_pos.get('side')}, quantity={first_pos.get('quantity')}")
        elif isinstance(res, dict):
            print(f"✓ 成功: {res}")
        else:
            print(f"✓ 成功: {res}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 14: get_position (keep_origin=True)
print("\n[TEST 14] get_position (keep_origin=True)")
print("-" * 80)
try:
    res, err = okx.get_position(symbol=symbol, keep_origin=True)
    if err:
        print(f"✗ 错误: {err}")
    else:
        print(f"✓ 成功: 返回原始数据")
        if isinstance(res, list) and res:
            print(f"  数据条数: {len(res)}")
        elif isinstance(res, dict):
            print(f"  数据类型: dict")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 15: symbols
print("\n[TEST 15] symbols")
print("-" * 80)
try:
    res, err = okx.symbols()
    if err:
        print(f"✗ 错误: {err}")
    else:
        print(f"✓ 成功: 交易对数量={len(res)}")
        print(f"  前10个交易对: {res[:10]}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 16: exchange_limits
print("\n[TEST 16] exchange_limits")
print("-" * 80)
try:
    res, err = okx.exchange_limits()
    if err:
        print(f"✗ 错误: {err}")
    else:
        if isinstance(res, list):
            print(f"✓ 成功: 交易对数量={len(res)}")
            if res:
                first_limit = res[0]
                print(f"  第一个交易对: symbol={first_limit.get('symbol')}, "
                      f"price_precision={first_limit.get('price_precision')}, "
                      f"size_precision={first_limit.get('size_precision')}")
        elif isinstance(res, dict):
            print(f"✓ 成功: {res}")
        else:
            print(f"✓ 成功: {res}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 17: exchange_limits (指定symbol)
print("\n[TEST 17] exchange_limits (指定symbol)")
print("-" * 80)
try:
    res, err = okx.exchange_limits(symbol=symbol)
    if err:
        print(f"✗ 错误: {err}")
    else:
        if isinstance(res, dict):
            print(f"✓ 成功: symbol={res.get('symbol')}, "
                  f"price_precision={res.get('price_precision')}, "
                  f"size_precision={res.get('size_precision')}, "
                  f"min_order_size={res.get('min_order_size')}")
        else:
            print(f"✓ 成功: {res}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 18: fees
print("\n[TEST 18] fees")
print("-" * 80)
try:
    res, err = okx.fees(symbol=symbol)
    if err:
        print(f"✗ 错误: {err}")
    else:
        if isinstance(res, dict):
            print(f"✓ 成功: symbol={res.get('symbol')}, "
                  f"fundingRate_hourly={res.get('fundingRate_hourly')}, "
                  f"fundingRate_period={res.get('fundingRate_period')}, "
                  f"period_hours={res.get('period_hours')}")
        else:
            print(f"✓ 成功: {res}")
except Exception as e:
    print(f"✗ 失败: {e}")

# 测试 19: fees (keep_origin=True)
print("\n[TEST 19] fees (keep_origin=True)")
print("-" * 80)
try:
    res, err = okx.fees(symbol=symbol, keep_origin=True)
    if err:
        print(f"✗ 错误: {err}")
    else:
        print(f"✓ 成功: 返回原始数据")
        if isinstance(res, dict):
            print(f"  数据类型: dict, keys={list(res.keys())[:5]}")
except Exception as e:
    print(f"✗ 失败: {e}")

print("\n" + "=" * 80)
print("测试完成")
print("=" * 80)

