#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
from pathlib import Path

# ==========================================
# 🔥 多币种策略配置区 🔥
# ==========================================
ACCOUNT_ID = 0  # 对应 account.yaml 中的 'grid' 账户
LOOP_INTERVAL = 2

# 在这里配置每个币种的逻辑、数量和利润
# direction 参数说明:
#   "LONG"  -> 做多逻辑 (先买后卖)
#   "SHORT" -> 做空逻辑 (先卖后买)
COIN_CONFIGS = [
    {
        "symbol": "PAXG_USDC_PERP",
        "direction": "LONG",      # <--- 这里控制做多还是做空
        "trade_size": 0.5,
        "profit_margin": 0.0006,  # 0.04%
    },
    {
        "symbol": "BTC_USDC_PERP",
        "direction": "SHORT",     # <--- 做空
        "trade_size": 0.01,      
        "profit_margin": 0.002,
    },
    {
        "symbol": "ETH_USDC_PERP",
        "direction": "SHORT",     # <--- 做空
        "trade_size": 0.2,
        "profit_margin": 0.002,
    },
    {
        "symbol": "SOL_USDC_PERP",
        "direction": "SHORT",     # <--- 做空
        "trade_size": 2,
        "profit_margin": 0.002,
    }
]
# ==========================================

def add_project_paths(project_name="ctos"):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = None
    path = current_dir
    while path != os.path.dirname(path):
        if os.path.basename(path) == project_name or os.path.exists(os.path.join(path, ".git")):
            project_root = path
            break
        path = os.path.dirname(path)
    if not project_root:
        raise RuntimeError("未找到项目根目录 (ctos)")
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root

PROJECT_ROOT = add_project_paths()

from ctos.drivers.backpack.util import align_decimal_places, BeijingTime
from ctos.core.runtime.ExecutionEngine import pick_exchange

# 全局状态字典，用于隔离每个币种的订单状态
TRADING_STATES = {}

def init_states(configs):
    """根据配置初始化状态"""
    for conf in configs:
        sym = conf['symbol']
        TRADING_STATES[sym] = {
            "buy_oid": None,      # 挂在买单的ID
            "sell_oid": None,     # 挂在卖单的ID
            "entry_price": None,  # 记录开仓价格
            "precision": 0.01     # 价格精度
        }

def recover_states(engine, configs):
    """启动时恢复状态：检查每个币种的遗留订单"""
    print(f"[{BeijingTime()}] 正在检查遗留订单以恢复状态...")
    
    for conf in configs:
        sym = conf['symbol']
        direction = conf['direction'] # 获取该币种的策略方向
        state = TRADING_STATES[sym]
        
        try:
            # 获取该币种的所有挂单
            orders, err = engine.cex_driver.get_open_orders(
                symbol=sym, onlyOrderId=False, keep_origin=False
            )
            if err or not orders:
                continue

            for order in orders:
                oid = str(order.get('orderId') or order.get('id'))
                side = str(order.get('side', '')).lower()
                price = float(order.get('price', 0))
                
                # 识别到买单 (Buy/Bid)
                if side in ['buy', 'bid', 'long']:
                    state['buy_oid'] = oid
                    # 如果是做多策略，买单就是开仓单，记录价格
                    if direction == 'LONG':
                        state['entry_price'] = price
                    print(f"  -> [{sym}] 发现遗留买单: {oid} @ {price}")

                # 识别到卖单 (Sell/Ask)
                elif side in ['sell', 'ask', 'short']:
                    state['sell_oid'] = oid
                    # 如果是做空策略，卖单就是开仓单，记录价格
                    if direction == 'SHORT':
                        state['entry_price'] = price
                    print(f"  -> [{sym}] 发现遗留卖单: {oid} @ {price}")

        except Exception as e:
            print(f"  [{sym}] 状态恢复出错: {e}")

def process_single_coin(engine, conf):
    """处理单个币种的交易逻辑"""
    sym = conf['symbol']
    direction = conf['direction'] # 核心参数：决定是跑多头还是空头
    size = conf['trade_size']
    margin = conf['profit_margin']
    state = TRADING_STATES[sym]
    precision = state['precision']
    
    # 获取当前挂单ID列表，用于判断订单是否成交
    open_orders_ids, err = engine.cex_driver.get_open_orders(symbol=sym, onlyOrderId=True)
    if err:
        return # 跳过本次循环

    # ====================================================
    # 策略逻辑 A: 做多 (LONG) -> 先买后卖
    # ====================================================
    if direction == 'LONG':
        # 1. 空仓开多：没单子 -> 挂买单
        if not state['buy_oid'] and not state['sell_oid']:
            try:
                price_now = engine.cex_driver.get_price_now(sym)
                buy_price = align_decimal_places(precision, price_now)
                
                print(f"[{BeijingTime()}] {sym} [做多开仓] 现价:{price_now} | 挂买: {buy_price}")
                oid, err = engine.cex_driver.place_order(sym, 'buy', 'limit', size, buy_price)
                if not err:
                    state['buy_oid'] = oid
                    state['entry_price'] = buy_price
            except Exception as e:
                print(f"⚠️ {sym} 下单异常: {e}")

        # 2. 多单成交：买单消失 -> 挂卖单止盈
        elif state['buy_oid'] and state['buy_oid'] not in open_orders_ids:
            print(f"[{BeijingTime()}] ✅ {sym} 买单成交！挂止盈卖单...")
            
            # 卖价 = 开仓价 * (1 + 利润)
            base_price = state['entry_price'] or engine.cex_driver.get_price_now(sym)
            sell_price = align_decimal_places(precision, base_price * (1 + margin))
            
            oid, err = engine.cex_driver.place_order(sym, 'sell', 'limit', size, sell_price)
            if not err:
                state['sell_oid'] = oid
                state['buy_oid'] = None # 清除买单标记
            else:
                print(f"❌ {sym} 挂卖单失败: {err}")

        # 3. 止盈结束：卖单消失 -> 重置
        elif state['sell_oid'] and state['sell_oid'] not in open_orders_ids:
            print(f"[{BeijingTime()}] 🎉 {sym} 止盈结束！")
            state['sell_oid'] = None
            state['entry_price'] = None

    # ====================================================
    # 策略逻辑 B: 做空 (SHORT) -> 先卖后买
    # ====================================================
    elif direction == 'SHORT':
        # 1. 空仓开空：没单子 -> 挂卖单
        if not state['buy_oid'] and not state['sell_oid']:
            try:
                price_now = engine.cex_driver.get_price_now(sym)
                sell_price = align_decimal_places(precision, price_now)
                
                print(f"[{BeijingTime()}] {sym} [做空开仓] 现价:{price_now} | 挂卖: {sell_price}")
                oid, err = engine.cex_driver.place_order(sym, 'sell', 'limit', size, sell_price)
                if not err:
                    state['sell_oid'] = oid
                    state['entry_price'] = sell_price
            except Exception as e:
                print(f"⚠️ {sym} 下单异常: {e}")

        # 2. 空单成交：卖单消失 -> 挂买单止盈 (平空)
        elif state['sell_oid'] and state['sell_oid'] not in open_orders_ids:
            print(f"[{BeijingTime()}] ✅ {sym} 卖单成交！挂平空买单...")
            
            # 平空买价 = 开仓价 * (1 - 利润)
            base_price = state['entry_price'] or engine.cex_driver.get_price_now(sym)
            buy_price = align_decimal_places(precision, base_price * (1 - margin))
            
            oid, err = engine.cex_driver.place_order(sym, 'buy', 'limit', size, buy_price)
            if not err:
                state['buy_oid'] = oid
                state['sell_oid'] = None # 清除卖单标记
            else:
                print(f"❌ {sym} 挂买单失败: {err}")

        # 3. 止盈结束：买单消失 -> 重置
        elif state['buy_oid'] and state['buy_oid'] not in open_orders_ids:
            print(f"[{BeijingTime()}] 🎉 {sym} 止盈结束！")
            state['buy_oid'] = None
            state['entry_price'] = None

def main():
    print(f"\n=== 多币种灵活策略 (Backpack) | {BeijingTime()} ===")
    
    # 初始化
    try:
        exch, engine = pick_exchange('bp', ACCOUNT_ID, strategy="MULTI_COIN_LOOP")
        print(f"✓ 交易引擎连接成功 (账户ID: {ACCOUNT_ID})")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return

    # 初始化数据
    init_states(COIN_CONFIGS)

    # 获取精度
    print("正在同步各币种精度...")
    for conf in COIN_CONFIGS:
        sym = conf['symbol']
        limits, err = engine.cex_driver.exchange_limits(symbol=sym)
        if not err:
            TRADING_STATES[sym]['precision'] = limits.get('price_precision', 0.01)
        else:
            print(f"⚠️ 无法获取 {sym} 精度，默认使用 0.01")

    # 恢复状态
    recover_states(engine, COIN_CONFIGS)
    print("=== 策略开始运行 ===")

    try:
        while True:
            # 轮询每个配置的币种
            for conf in COIN_CONFIGS:
                process_single_coin(engine, conf)
            
            # 生成状态监控条
            status_list = []
            for conf in COIN_CONFIGS:
                sym = conf['symbol'].split('_')[0]
                d = conf['direction'][0] # L 或 S
                st = TRADING_STATES[conf['symbol']]
                
                icon = "⚪"
                if st['buy_oid']: icon = "🟢买"
                elif st['sell_oid']: icon = "🔴卖"
                
                status_list.append(f"{sym}({d}):{icon}")
            
            print(f"\r监控: {' | '.join(status_list)}", end="")
            time.sleep(LOOP_INTERVAL)

    except KeyboardInterrupt:
        print("\n程序已手动停止。")

if __name__ == "__main__":
    main()