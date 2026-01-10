#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
from pathlib import Path

# ==========================================
# 策略配置区
# ==========================================
STRATEGY_CONFIG = {
    "exchange": "bp",              # 交易所: Backpack
    "account_id": 0,               # 账户ID: 1 (对应 account.yaml 中的 grid 账户)
    "symbol": "PAXG_USDC_PERP",    # 交易对
    "trade_size": 0.5,             # 单笔交易数量
    "profit_margin": 0.0004,       # 利润目标 (0.04%)
    "loop_interval": 5          # 循环检测频率 (秒)
}
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

def main():
    conf = STRATEGY_CONFIG
    print(f"\n=== PAXG 合约循环策略 (最终修复版) | {BeijingTime()} ===")
    print(f"当前配置: 账户ID={conf['account_id']} | 数量={conf['trade_size']} | 目标利润={conf['profit_margin']*100}%")
    
    # 1. 初始化交易引擎
    try:
        exch, engine = pick_exchange(conf['exchange'], conf['account_id'], strategy="PAXG_PERP_LOOP")
        print(f"✓ 交易驱动初始化成功 (账户ID: {conf['account_id']})")
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        return

    # 2. 获取交易对精度信息
    limits, err = engine.cex_driver.exchange_limits(symbol=conf['symbol'])
    if err:
        print(f"❌ 获取交易对信息失败: {err}")
        return
    price_precision = limits.get('price_precision', 0.01)

    # 策略状态变量
    buy_oid = None    
    sell_oid = None   
    entry_price = None

    # ==============================================================================
    # 🟢 状态恢复模块 (已修复 Bid/Ask 识别问题)
    # ==============================================================================
    print(f"[{BeijingTime()}] 正在检查遗留订单以恢复状态...")
    try:
        # keep_origin=False 让驱动返回标准化的数据
        existing_orders, err = engine.cex_driver.get_open_orders(
            symbol=conf['symbol'], 
            onlyOrderId=False, 
            keep_origin=False
        )
        
        if not err and existing_orders:
            for order in existing_orders:
                oid = str(order.get('orderId') or order.get('id'))
                # 获取方向并转小写
                side = str(order.get('side', '')).lower() 
                price = float(order.get('price', 0))
                
                # 🔥 关键修复：同时检查 'buy'/'bid' 和 'sell'/'ask'
                if side in ['buy', 'bid', 'long']:
                    buy_oid = oid
                    entry_price = price
                    print(f"  -> 📥 发现遗留【买单】: {oid} @ {price} (Side: {side})")
                
                elif side in ['sell', 'ask', 'short']:
                    sell_oid = oid
                    print(f"  -> 📤 发现遗留【卖单】: {oid} @ {price} (Side: {side})")
        
        # 打印恢复结果
        if buy_oid:
            print("  => 状态已恢复：持有买单，等待成交...")
        elif sell_oid:
            print("  => 状态已恢复：持有卖单，等待成交...")
        else:
            # 🔥 修复：检查是否已有持仓（防止重启后重复买入）
            try:
                pos, err = engine.cex_driver.get_position(symbol=conf['symbol'], keep_origin=False)
                if not err and pos and float(pos.get('quantity', 0)) > 0:
                    buy_oid = "RECOVERED_POSITION"  # 设置伪ID，触发卖出逻辑
                    entry_price = float(pos.get('entryPrice', 0))
                    print(f"  => 状态已恢复：发现现有持仓 {pos.get('quantity')} @ {entry_price}，将挂出卖单...")
                else:
                    print("  => 未识别到有效挂单或持仓，将按空仓逻辑启动。")
            except Exception as e:
                print(f"  => 检查持仓异常: {e}，按空仓逻辑启动。")

    except Exception as e:
        print(f"⚠️ 状态恢复检查异常: {e}，将尝试以空仓状态启动")
    # ==============================================================================

    # 3. 进入主循环
    try:
        while True:
            # 获取当前挂单ID列表 (用于快速判断成交)
            open_orders, err = engine.cex_driver.get_open_orders(symbol=conf['symbol'], onlyOrderId=True)
            
            if err:
                if "Invalid X-API-Key" in str(err):
                    print(f"\n❌ API 秘钥无效！请检查 account.yaml 配置。")
                    break
                time.sleep(conf['loop_interval'])
                continue

            # --- 核心交易逻辑 ---

            # A. 空仓状态：无买单也无卖单 -> 挂买单
            if not buy_oid and not sell_oid:
                try:
                    price_now = engine.cex_driver.get_price_now(conf['symbol'])
                    target_buy_price = align_decimal_places(price_precision, price_now)
                    
                    print(f"[{BeijingTime()}] 现价: {price_now} | 下买单: {target_buy_price}")
                    oid, err = engine.cex_driver.place_order(
                        symbol=conf['symbol'], 
                        side='buy', 
                        order_type='limit', 
                        size=conf['trade_size'], 
                        price=target_buy_price
                    )
                    
                    if not err:
                        buy_oid = oid
                        entry_price = target_buy_price
                    else:
                        print(f"❌ 下单失败: {err}")
                except Exception as e:
                    print(f"⚠️ 获取行情或下单异常: {e}")

            # B. 持有买单但订单消失 -> 视为成交 -> 挂卖单
            elif buy_oid and buy_oid not in open_orders:
                print(f"[{BeijingTime()}] ✅ 买单({buy_oid})已成交！正在挂出卖单...")
                
                # 兜底：如果 entry_price 意外为空，用现价
                if not entry_price:
                     entry_price = engine.cex_driver.get_price_now(conf['symbol'])

                target_sell_price = align_decimal_places(
                    price_precision, 
                    entry_price * (1 + conf['profit_margin'])
                )
                
                print(f"[{BeijingTime()}] 下卖单: {target_sell_price}")
                oid, err = engine.cex_driver.place_order(
                    symbol=conf['symbol'], 
                    side='sell', 
                    order_type='limit', 
                    size=conf['trade_size'], 
                    price=target_sell_price
                )
                
                if not err:
                    sell_oid = oid
                    buy_oid = None
                else:
                    print(f"❌ 下卖单失败: {err}")

            # C. 持有卖单但订单消失 -> 视为成交 -> 循环结束，重置
            elif sell_oid and sell_oid not in open_orders:
                print(f"[{BeijingTime()}] 🎉 卖单({sell_oid})已成交！本轮获利结束，准备下一轮。")
                sell_oid = None
                entry_price = None

            # 状态监控
            state_msg = "🔴 持卖单" if sell_oid else "🟢 持买单" if buy_oid else "⚪ 空仓"
            print(f"\r状态: {state_msg} | 标的: {conf['symbol']}", end="")
            
            time.sleep(conf['loop_interval'])

    except KeyboardInterrupt:
        print("\n手动停止程序。")

if __name__ == "__main__":
    main()