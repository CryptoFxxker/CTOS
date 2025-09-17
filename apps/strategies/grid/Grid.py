#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
from pathlib import Path

# 将项目根目录加入 sys.path，确保可以导入 `ctos` 包
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ctos.drivers.okx.util import align_decimal_places

def pick_exchange(from_arg: str | None = None):
    ex = (from_arg or os.getenv('GRID_EX') or '').strip().lower()
    if ex not in ('okx', 'bp'):
        ex = input("选择交易所 exchange [okx/bp] (默认 okx): ").strip().lower() or 'okx'
    if ex == 'bp':
        from ctos.drivers.backpack.driver import BackpackDriver as Driver
        return 'bp', Driver()
    else:
        from ctos.drivers.okx.driver import OkxDriver as Driver
        return 'okx', Driver()


def get_float(prompt: str, default: float):
    try:
        s = input(f"{prompt} (默认 {default}): ").strip()
        return float(s) if s else default
    except Exception:
        return default


def build_grid_prices(center: float, span: float, n_levels: int, mode: str = 'percent'):
    """
    返回买/卖价列表（不含中心价），长度各为 n_levels。
    mode='percent' → span 视作百分比（如 0.02 表示 ±2%）
    mode='arithmetic' → span 视作绝对价格带（如 50 表示 ±50）
    """
    buys, sells = [], []
    for i in range(1, n_levels + 1):
        if mode == 'arithmetic':
            step = span * i / n_levels
            buys.append(center * 1.0 - step)
            sells.append(center * 1.0 + step)
        else:
            pct = span * i / n_levels
            buys.append(center * (1 - pct))
            sells.append(center * (1 + pct))
    # 价格从低到高统一一下
    buys.sort()
    sells.sort()
    return buys, sells




def place_grid(driver, symbol: str, base_size: float, buys: list[float], sells: list[float]):
    orders = []
    price_now = driver.get_price_now(symbol)
    for p in buys:
        oid, err = driver.place_order(symbol, side='buy', order_type='limit', size=base_size, price=align_decimal_places(price_now, p))
        if err:
            print('下买单失败:', p, err)
        else:
            orders.append(oid)
    for p in sells:
        oid, err = driver.place_order(symbol, side='sell', order_type='limit', size=base_size, price=align_decimal_places(price_now, p))
        if err:
            print('下卖单失败:', p, err)
        else:
            orders.append(oid)
    return orders


def main():
    print("\n=== Grid Futures Strategy (简易网格合约) ===")
    arg_ex = sys.argv[1] if len(sys.argv) > 1 else None
    exch, driver = pick_exchange(arg_ex)
    print(f"使用交易所: {exch}")

    # 符号
    default_symbol = 'ETH-USDT-SWAP' if exch == 'okx' else 'ETH_USDC_PERP'
    symbol = input(f"交易对 symbol (默认 {default_symbol}): ").strip() or default_symbol

    # 获取中心价
    try:
        mid = float(driver.get_price_now(symbol))
    except Exception as e:
        print('获取中心价失败，回退为手动输入:', e)
        mid = get_float('请输入中心价', 2000.0)
    print('中心价 =', mid)

    mode = (input("网格模式 [percent/arithmetic] (默认 percent): ").strip().lower() or 'percent')
    span = get_float('价格带幅度(百分比:0.02=±2% / 绝对: 50=±50)', 0.02 if mode == 'percent' else 50.0)
    n_levels = int(get_float('每侧网格层数', 3))
    base_size = get_float('每格下单数量(合约张/币数量，小额测试为宜)', 0.01)

    buys, sells = build_grid_prices(mid, span, n_levels, mode)
    print('买单价:', [round(x, 6) for x in buys])
    print('卖单价:', [round(x, 6) for x in sells])

    confirm = input('确认下单? [Y/n]: ').strip().lower()
    if confirm not in ('', 'y', 'yes'):
        print('已取消。')
        return

    order_ids = place_grid(driver, symbol, base_size, buys, sells)
    print('已提交网格订单数 =', len(order_ids), order_ids)

    print('\n运行中。按 Ctrl+C 结束并尝试撤单...')
    start_ts = time.time()
    last_print_len = 0
    try:
        while True:
            t0 = time.time()
            # 余额
            try:
                quote_ccy = 'USDT' if 'USDT' in symbol or exch == 'okx' else 'USDC'
                balance = driver.fetch_balance(quote_ccy)
            except Exception as e:
                print('??? fetch_balance: ', e)
                balance = 000
            # 现价
            try:
                price_now = driver.get_price_now(symbol)
            except Exception as e:
                print('??? get_price_now: ', e)
                price_now = None
            # 未完成订单数
            try:
                oids, _ = driver.get_open_orders(symbol=symbol, onlyOrderId=True, keep_origin=True)
                open_cnt = len(oids) if isinstance(oids, (list, tuple)) else 0
            except Exception as e:
                print('??? get_open_orders: ', e)
                open_cnt = None

            # 运行时长
            uptime = int(time.time() - start_ts)
            hh = uptime // 3600
            mm = (uptime % 3600) // 60
            ss = uptime % 60    

            line = f"[Grid:{exch}] Uptime {hh:02d}:{mm:02d}:{ss:02d} | {symbol} px={price_now} | openOrders={open_cnt} | {('bal='+str(round(float(balance),4)) if isinstance(balance,(int,float,str)) else 'bal=?')}"
            # 清理上一行残留
            pad = max(0, last_print_len - len(line))
            print("\r" + line + (" " * pad), end="")
            last_print_len = len(line)

            # 每10秒更新一次
            elapsed = time.time() - t0
            sleep_left = max(0, 10 - elapsed)
            time.sleep(sleep_left)
    except KeyboardInterrupt:
        try:
            print('\n尝试撤销全部未完成订单...')
            if exch == 'okx':
                driver.cancel_all(symbol)
            else:
                driver.cancel_all(symbol)
        except Exception as e:
            print('撤单失败:', e)
        print('退出。')
    except Exception as e:
        print('what is wrong?: ', e)


if __name__ == '__main__':
    main()


