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

from ctos.drivers.backpack.util import align_decimal_places, round_dynamic, round_to_two_digits

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

def get_all_positions(driver):
    """
    返回 {symbol: {init_price, entryPrice, side, size}} 的字典
    """
    positions = {}
    try:
        unified, err = driver.get_position(symbol=None, keep_origin=False)
        if err:
            print("获取持仓失败:", err)
            return {}

        if isinstance(unified, list):
            for pos in unified:
                sym = pos["symbol"]
                size = float(pos["quantity"])
                entry = float(pos["entryPrice"] or 0.0)
                mark = float(pos["markPrice"] or 0.0)
                side = pos["side"]
                pnlUnrealized = float(pos["pnlUnrealized"] or 0.0)
                if size > 0:
                    positions[sym] = {
                        "init_price": mark,
                        "avg_cost": entry,
                        "size": size,
                        "side": side,
                        'pnlUnrealized':pnlUnrealized,
                    }
    except Exception as e:
        print("get_all_positions 异常:", e)
    return positions

def print_position(sym, pos, init_price, start_ts):
    """
    打印实时仓位信息 + 起步价
    :param sym: 交易对
    :param pos: driver.get_position 返回的单个仓位(dict)
    :param init_price: 手动设定的起步价
    :param start_ts: 启动时间戳
    """
    uptime = int(time.time() - start_ts)
    hh = uptime // 3600
    mm = (uptime % 3600) // 60
    ss = uptime % 60

    # 从仓位数据里拿需要的字段
    price_now = float(pos.get("markPrice", 0) or 0)
    avg_cost = float(pos.get("entryPrice", 0) or 0)
    size = float(pos.get("quantity", 0) or 0)
    side = pos.get("side", "?")
    pnlUnrealized = float(pos.get("pnlUnrealized", 0) or 0)

    change_pct = (price_now - init_price) / init_price * 100 if init_price else 0.0

    header = f"=== [仓位监控] {sym} | Uptime {hh:02d}:{mm:02d}:{ss:02d} ==="
    line = (
        f"现价={price_now:.4f} | "
        f"起步价_init_price={init_price:.4f} | "
        f"均价_avg_cost={avg_cost:.4f} | "
        f"数量={size:.6f} | "
        f"方向={side} | "
        f"浮盈={pnlUnrealized:+.2f} | "
        f"涨跌幅={change_pct:+.2f}%"
    )
    output = header + line + '===='
    if len(output) < 80:
        output += '*' * (80 - len(output))
    print('\r' + output, end='')

def main():
    print("\n=== 动态监控策略 (涨跌买卖 8.88) ===")
    arg_ex = sys.argv[1] if len(sys.argv) > 1 else None
    exch, driver = pick_exchange(arg_ex)
    print(f"使用交易所: {exch}")

    positions = get_all_positions(driver)
    if not positions:
        print("没有持仓，退出。")
        return
    print("初始持仓:", positions)
    start_ts = time.time()
    try:
        while True:
            for sym, data in positions.items():
                try:
                    pos, err = driver.get_position(symbol=sym, keep_origin=False)
                    if err or not pos:
                        continue
                    price_now = float(pos["markPrice"])
                    entryPrice = float(pos["entryPrice"])
                    avg_cost = float(pos["entryPrice"] or 0.0)
                    size = float(pos["quantity"])
                    side = pos["side"]
                    pnlUnrealized = float(pos["pnlUnrealized"] or 0.0)
                    init_price = data["init_price"]
                    print_position(sym, pos, init_price, start_ts)


                    change_pct = (price_now - init_price) / init_price
                    # 涨幅 >= 1% → 卖出
                    if change_pct >= 0.01:
                        qty = 8.88 / price_now
                        if (side == "long" and price_now > entryPrice) or side == "short":
                            qty = round_to_two_digits(qty)
                            price_align = round_dynamic(price_now * 1.0005)
                            oid, err = driver.place_order(sym, side="sell",
                                                          order_type="limit",
                                                          size=qty, price=price_align)
                            if err:
                                print(f"\n[{sym}] 卖单失败:", err, '\n')
                            else:
                                print(f"\n[{sym}] 卖出 {qty}, px={price_align}, id={oid}\n")
                                data["init_price"] = price_now
                                data["size"] -= qty

                    # 跌幅 >= 1.11% → 买入
                    elif change_pct <= -0.0111:
                        qty = 8.88 / price_now
                        if (side == "short" and price_now < entryPrice) or side == "long":
                            qty = round_to_two_digits(qty)
                            price_align = round_dynamic(price_now * 0.9995)
                            oid, err = driver.place_order(sym, side="buy",
                                                        order_type="limit",
                                                        size=qty, price=price_align)
                            if err:
                                print(f"\n[{sym}] 买单失败:", err, '\n')
                            else:
                                print(f"\n[{sym}] 买入 {qty}, px={price_align}, id={oid}\n")
                                data["init_price"] = price_now
                                data["size"] += qty
                                # 更新均价（加权）
                                data["avg_cost"] = (avg_cost * (data["size"] - qty) + price_now * qty) / data["size"]

                except Exception as e:
                    print(f"[{sym}] 循环异常:", e)

            time.sleep(60)

    except KeyboardInterrupt:
        print("手动退出。")


if __name__ == '__main__':
    main()