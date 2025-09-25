#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime, timedelta


def add_project_paths(project_name="ctos", subpackages=None):
    """
    自动查找项目根目录，并将其及常见子包路径添加到 sys.path。
    :param project_name: 项目根目录标识（默认 'ctos'）
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = None
    # 向上回溯，找到项目根目录
    path = current_dir
    while path != os.path.dirname(path):  # 一直回溯到根目录
        if os.path.basename(path) == project_name or os.path.exists(os.path.join(path, ".git")):
            project_root = path
            break
        path = os.path.dirname(path)
    if not project_root:
        raise RuntimeError(f"未找到项目根目录（包含 {project_name} 或 .git）")
    # 添加根目录
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root
# 执行路径添加
PROJECT_ROOT = add_project_paths()
print('PROJECT_ROOT: ', PROJECT_ROOT, 'CURRENT_DIR: ', os.path.dirname(os.path.abspath(__file__)))


from ctos.drivers.backpack.util import align_decimal_places, round_dynamic, round_to_two_digits, rate_price2order, cal_amount
from ctos.core.runtime.ExecutionEngine import pick_exchange


def main1_test(engine, ):
    bp = engine.cex_driver
    pos, _ = bp.get_position()

    now_position = {x['symbol']:float(x['netCost']) for x in pos}
    print(json.dumps(now_position, indent=4))

    all_coins, _  = bp.symbols()

    all_coins = [x[:x.find('_')].lower() for x in all_coins if x[:x.find('_')].lower() in rate_price2order.keys()] 
    print(all_coins, len(all_coins))


    # while True:
    #     time.sleep(3)

    with open(str(PROJECT_ROOT) + '/apps/strategies/hedge/good_group' + '_bp.txt' if engine.cex_driver.cex.find('p')!=-1 else '.txt', 'r', encoding='utf8') as f:
        data = f.readlines()
        good_group = data[0].strip().split(',')
        all_rate = [float(x) for x in data[1].strip().split(',')]
        # 将good_group中不在all_coins中的元素去掉，并同步删除all_rate中对应的元素
        filtered_good_group = []
        filtered_all_rate = []
        for i, coin in enumerate(good_group):
            if coin in all_coins:
                filtered_good_group.append(coin)
                filtered_all_rate.append(all_rate[i])
        good_group = filtered_good_group
        all_rate = filtered_all_rate
        all_rate = [x for x in all_rate if x > 0]
        btc_rate = all_rate[0] / sum(all_rate)
        split_rate = {good_group[x + 1]: all_rate[x + 1] / sum(all_rate) for x in range(len(all_rate) - 1)}

    start_money = bp.fetch_balance()
    leverage_times = 0.2
    init_operate_position = start_money * leverage_times if start_money * leverage_times > len(all_coins) * 10 else len(all_coins) * 10
    new_rate_place2order = {k:v for k,v in rate_price2order.items() if k in all_coins}

    usdt_amounts = []
    coins_to_deal = []
    is_btc_failed = False
    now_position = {}
    for coin in all_coins:
        time.sleep(0.2)
        if coin in good_group:
            operate_amount = cal_amount(coin, init_operate_position, good_group, btc_rate, split_rate)
            if is_btc_failed:
                operate_amount = -operate_amount
            if bp._norm_symbol(coin)[0] in now_position:
                operate_amount = operate_amount - now_position[bp._norm_symbol(coin)[0]]
            usdt_amounts.append(operate_amount)
            coins_to_deal.append(coin)
        else:
            sell_amount = init_operate_position / (len(new_rate_place2order) - len(good_group))
            if is_btc_failed:
                sell_amount = -sell_amount
            sell_amount = -sell_amount
            if bp._norm_symbol(coin)[0] in now_position:
                sell_amount = sell_amount - now_position[bp._norm_symbol(coin)[0]]
            usdt_amounts.append(sell_amount)
            coins_to_deal.append(coin)
    print(usdt_amounts, coins_to_deal,)
    focus_orders = engine.set_coin_position_to_target(usdt_amounts, coins_to_deal, soft=True)
    engine.focus_on_orders(new_rate_place2order.keys(), focus_orders)
    while len(engine.watch_threads) > 0:
        time.sleep(1)

def get_GridPositions_storage_path(exchange: str, account: int) -> str:
    """获取GridPositions存储文件路径"""
    logging_dir = os.path.join(PROJECT_ROOT, 'ctos', 'core', 'io', 'logging')
    os.makedirs(logging_dir, exist_ok=True)
    default_strategy = os.path.splitext(os.path.basename(__file__))[0].upper()
    return os.path.join(logging_dir, f'{exchange}_Account{account}_{default_strategy}_GridPositions.json')

def save_GridPositions(GridPositions: dict, exchange: str, account: int) -> None:
    """保存GridPositions到本地文件"""
    try:
        storage_path = get_GridPositions_storage_path(exchange, account)
        data = {
            'timestamp': datetime.now().isoformat(),
            'exchange': exchange,
            'GridPositions': GridPositions
        }
        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\r ✓ 持仓数据已保存到: {storage_path}", end='')
    except Exception as e:
        print(f"\r ✗ 保存持仓数据失败: {e}", end='')

def load_GridPositions(exchange: str, account: int) -> tuple[dict, bool]:
    """
    从本地文件加载GridPositions
    返回: (GridPositions_dict, is_valid)
    如果文件不存在或超过1小时，返回空字典和False
    """
    try:
        storage_path = get_GridPositions_storage_path(exchange, account)
        if not os.path.exists(storage_path):
            return {}, False
        
        with open(storage_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 检查时间戳
        saved_time = datetime.fromisoformat(data['timestamp'])
        current_time = datetime.now()
        time_diff = current_time - saved_time
        
        # 如果超过1小时，返回无效
        if time_diff > timedelta(hours=6):
            print(f"⚠ 持仓数据已过期 ({time_diff}), 将重新获取")
            return {}, False
        
        # 检查交易所是否匹配
        if data.get('exchange') != exchange:
            print(f"⚠ 交易所不匹配 (文件: {data.get('exchange')}, 当前: {exchange}), 将重新获取")
            return {}, False
        
        print(f"✓ 从本地加载持仓数据 (保存时间: {saved_time.strftime('%Y-%m-%d %H:%M:%S')})")
        return data.get('GridPositions', {}), True
        
    except Exception as e:
        print(f"✗ 加载持仓数据失败: {e}")
        return {}, False



def get_all_GridPositions(engine, exchange: str, use_cache: bool = True):
    """
    获取所有持仓，支持本地缓存
    返回 {symbol: {init_price, entryPrice, side, size, buy_order_id, sell_order_id}} 的字典
    """
    # 尝试从本地加载
    if use_cache:
        cached_GridPositions, is_valid = load_GridPositions(exchange, engine.account)
        if is_valid and cached_GridPositions:
            return cached_GridPositions
    # 从API获取最新持仓
    GridPositions = {}
    try:
        print("正在从API获取最新持仓数据...")
        unified, err = engine.cex_driver.get_position(symbol=None, keep_origin=False)
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
                    GridPositions[sym] = {
                        "init_price": mark,
                        "avg_cost": entry,
                        "size": size,
                        "side": side,
                        'pnlUnrealized': pnlUnrealized,
                        "buy_order_id": None,  # 买单订单ID
                        "sell_order_id": None,  # 卖单订单ID
                    }
        
        # 保存到本地
        if GridPositions:
            save_GridPositions(GridPositions, exchange, engine.account)
            
    except Exception as e:
        print("get_all_GridPositions 异常:", e)
    return GridPositions

def manage_grid_orders(engine, sym, data, open_orders, price_precision, size_precision, base_amount):
    """
    管理网格订单逻辑
    1. 检查买单和卖单是否在open_orders中
    2. 如果都不在，则下新订单
    3. 如果只有一个消失，则处理成交逻辑
    4. 如果两个都在，则等待
    """
    buy_order_id = data.get("buy_order_id")
    sell_order_id = data.get("sell_order_id")
    init_price = data["init_price"]
    # 检查订单是否存在
    buy_exists = buy_order_id and buy_order_id in open_orders
    sell_exists = sell_order_id and sell_order_id in open_orders
    
    # 计算目标价格
    buy_price = align_decimal_places(price_precision, init_price * 0.975)
    sell_price = align_decimal_places(price_precision, init_price * 1.015)
    
    # 情况1: 两个订单都不存在，下新订单
    if not buy_exists and not sell_exists:
        print(f"\n[{sym}] 两个订单都不存在，下新订单...")
        
        # 下买单
        buy_qty = align_decimal_places(size_precision, base_amount / buy_price)
        # 使用place_order直接下单，指定价格
        buy_oid, buy_err = engine.cex_driver.place_order(
            symbol=sym, 
            side="buy", 
            order_type="limit", 
            size=buy_qty, 
            price=buy_price
        )
        if buy_err:
            print(f"[{sym}] 买单失败: {buy_err}")
        else:
            data["buy_order_id"] = buy_oid
            print(f"[{sym}] 买单已下: {buy_qty} @ {buy_price}, id={buy_oid}")
        
        # 下卖单
        sell_qty = align_decimal_places(size_precision, base_amount / sell_price)
        # 使用place_order直接下单，指定价格
        sell_oid, sell_err = engine.cex_driver.place_order(
            symbol=sym, 
            side="sell", 
            order_type="limit", 
            size=sell_qty, 
            price=sell_price
        )
        if sell_err:
            print(f"[{sym}] 卖单失败: {sell_err}")
        else:
            data["sell_order_id"] = sell_oid
            print(f"[{sym}] 卖单已下: {sell_qty} @ {sell_price}, id={sell_oid}")
        
        return True
    
    # 情况2: 买单成交，卖单还在
    elif not buy_exists and sell_exists:
        print(f"\n[{sym}] 买单成交！调整策略...")
        
        # 更新初始价格
        data["init_price"] = init_price * 0.99
        new_init_price = data["init_price"]
        
        # 计算新价格
        new_buy_price = align_decimal_places(price_precision,  new_init_price * 0.975)
        new_sell_price = align_decimal_places(price_precision,  new_init_price * 1.015)
        
        # 下新买单
        buy_qty = align_decimal_places(size_precision, base_amount / new_buy_price)
        buy_oid, buy_err = engine.cex_driver.place_order(
            symbol=sym, 
            side="buy", 
            order_type="limit", 
            size=buy_qty, 
            price=new_buy_price
        )
        if buy_err:
            print(f"[{sym}] 新买单失败: {buy_err}")
        else:
            data["buy_order_id"] = buy_oid
            print(f"[{sym}] 新买单已下: {buy_qty} @ {new_buy_price}, id={buy_oid}")
        
        # 改单现有卖单
        if sell_order_id:
            sell_qty = align_decimal_places(size_precision, base_amount / new_sell_price)
            new_sell_oid, amend_err = engine.cex_driver.amend_order(
                order_id=sell_order_id,
                symbol=sym,
                price=new_sell_price,
                size=sell_qty
            )
            if amend_err:
                print(f"[{sym}] 改单失败: {amend_err}")
            else:
                data["sell_order_id"] = new_sell_oid
                print(f"[{sym}] 卖单已改单: {sell_qty} @ {new_sell_price}, 新id={new_sell_oid}")
        
        return True
    
    # 情况3: 卖单成交，买单还在
    elif buy_exists and not sell_exists:
        print(f"\n[{sym}] 卖单成交！调整策略...")
        
        # 更新初始价格
        data["init_price"] = init_price * 1.01
        new_init_price = data["init_price"]
        
        # 计算新价格
        new_buy_price = align_decimal_places(price_precision,  new_init_price * 0.975)
        new_sell_price = align_decimal_places(price_precision,  new_init_price * 1.015)
        
        # 改单现有买单
        if buy_order_id:
            buy_qty = align_decimal_places(size_precision, base_amount / new_buy_price)
            new_buy_oid, amend_err = engine.cex_driver.amend_order(
                order_id=buy_order_id,
                symbol=sym,
                price=new_buy_price,
                size=buy_qty
            )
            if amend_err:
                print(f"[{sym}] 改单失败: {amend_err}")
            else:
                data["buy_order_id"] = new_buy_oid
                print(f"[{sym}] 买单已改单: {buy_qty} @ {new_buy_price}, 新id={new_buy_oid}")
        
        # 下新卖单
        sell_qty = align_decimal_places(size_precision, base_amount / new_sell_price)
        sell_oid, sell_err = engine.cex_driver.place_order(
            symbol=sym, 
            side="sell", 
            order_type="limit", 
            size=sell_qty, 
            price=new_sell_price
        )
        if sell_err:
            print(f"[{sym}] 新卖单失败: {sell_err}")
        else:
            data["sell_order_id"] = sell_oid
            print(f"[{sym}] 新卖单已下: {sell_qty} @ {new_sell_price}, id={sell_oid}")
        
        return True
    
    # 情况4: 两个订单都在，无事发生
    else:
        return False

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
    if not pos:
        output = f"=== [仓位监控] 当前没有仓位： {sym} | Uptime {hh:02d}:{mm:02d}:{ss:02d} ==="
    else:
        # 从仓位数据里拿需要的字段
        price_now = float(pos.get("markPrice", 0) or 0)
        avg_cost = float(pos.get("entryPrice", 0) or 0)
        size = float(pos.get("quantity", 0) or 0)
        side = pos.get("side", "?")
        pnlUnrealized = float(pos.get("pnlUnrealized", 0) or 0)

        change_pct = (price_now - init_price) / init_price * 100 if init_price else 0.0

        header = f"=== [仓位监控] {sym} | Uptime {hh:02d}:{mm:02d}:{ss:02d} ==="
        line = (
            f"现价={round_dynamic(price_now)} | "
            f"起步价_init_price={round_dynamic(init_price)} | "
            f"均价_avg_cost={avg_cost:.4f} | "
            f"数量={round_to_two_digits(size)} | "
            f"方向={side} | "
            f"浮盈={pnlUnrealized:+.2f} | "
            f"涨跌幅={change_pct:+.2f}%"
        )
        output = header + line + '===='
    if len(output) < 180:
        output += ' ' * (180 - len(output))
    print('\r' + output, end='')

def show_help():
    """显示帮助信息"""
    print("""
=== 网格策略使用说明 (订单管理版) ===

用法: python Grid_with_more_gap.py [选项] [交易所]

选项:
  --refresh, -r, --force    强制刷新持仓缓存，忽略本地存储
  --help, -h                显示此帮助信息

交易所:
  okx, ok, o, ox, okex      欧易交易所 (默认)
  bp, backpack, b, back     Backpack交易所

示例:
  python Grid_with_more_gap.py                    # 交互式选择交易所
  python Grid_with_more_gap.py okx                # 使用欧易交易所
  python Grid_with_more_gap.py --refresh okx      # 强制刷新缓存
  python Grid_with_more_gap.py bp                 # 使用Backpack交易所

策略特性:
  ✓ 订单管理策略 (基于get_open_orders)
  ✓ 自动网格下单 (买单@0.975x, 卖单@1.015x)
  ✓ 成交后自动调整 (买单成交→0.99x, 卖单成交→1.01x)
  ✓ 智能改单机制 (存在订单直接改单，不存在则下新单)
  ✓ 订单状态监控 (实时检查订单存在性)
  ✓ 本地持仓缓存 (6小时内自动加载)
  ✓ 完整操作日志记录

策略逻辑:
  1. 获取全局所有订单
  2. 检查每个币种的买单和卖单是否存在
  3. 如果都不存在 → 下新订单
  4. 如果买单成交 → 下新买单 + 改单现有卖单
  5. 如果卖单成交 → 改单现有买单 + 下新卖单
  6. 如果都在 → 等待下一轮

改单优势:
  ✓ 减少API调用次数
  ✓ 保持订单优先级
  ✓ 避免订单丢失风险
  ✓ 提高执行效率
""")

def main():
    print("\n=== 网格策略 (订单管理版) ===")
    
    # 解析命令行参数
    force_refresh = False
    arg_ex = None
    show_help_flag = False
    acount_id = None
    base_amount = 8.88
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg in ['--refresh', '-r', '--force']:
                force_refresh = True
            elif arg in ['--help', '-h']:
                show_help_flag = True
            elif arg in ['okx', 'bp', 'ok', 'backpack']:
                arg_ex = arg
            elif arg in ['01234']:
                acount_id = int(arg)
            elif arg in ['8.88', '888', '8888', '6.66', '66.6', '6666']:
                base_amount = float(arg)
    
    if show_help_flag:
        show_help()
        return
    
    # 自动用当前文件名（去除后缀）作为默认策略名，细节默认为COMMON
    default_strategy = os.path.splitext(os.path.basename(__file__))[0].upper()
    exch, engine = pick_exchange(arg_ex, acount_id, strategy=default_strategy, strategy_detail="COMMON")
    print(f"使用交易所: {exch}")
    
    if force_refresh:
        print("🔄 强制刷新模式：忽略本地缓存")

    # 记录策略启动
    engine.monitor.record_operation("StrategyStart", "Grid-Order-Management", {
        "exchange": exch,
        "strategy": "Grid-Order-Management",
        "version": "3.0",
        "force_refresh": force_refresh
    })

    # 获取持仓（支持缓存）
    GridPositions = get_all_GridPositions(engine, exch, use_cache=True if not force_refresh else False)
    if not GridPositions:
        print("没有持仓，退出。")
        engine.monitor.record_operation("StrategyExit", "Grid-Order-Management", {
            "reason": "No GridPositions found"
        })
        return
    print("初始持仓:", GridPositions)
    start_ts = time.time()
    sleep_time = 0.88
    need_to_update = False
    try:
        while True:
            # 获取全局所有订单
            open_orders, err = engine.cex_driver.get_open_orders(symbol=None, onlyOrderId=True, keep_origin=False)
            if err:
                print(f"获取订单失败: {err}")
                time.sleep(sleep_time)
                continue
            
            if not isinstance(open_orders, list) or not open_orders:
                open_orders = []
            origin_pos, err = engine.cex_driver.get_position(symbol=None, keep_origin=False)
            poses = {}
            for pos in origin_pos:
                poses[pos["symbol"]] = pos
            if err or not poses:
                continue
            for sym, data in GridPositions.items():
                try:
                    time.sleep(sleep_time)
                    # 获取当前持仓信息用于显示
                    if sym not in poses:
                        pos = {}
                    else:
                        pos = poses[sym]
                    exchange_limits_info, err = engine.cex_driver.exchange_limits(symbol=sym)
                    if err:
                        print('CEX DRIVER.exchange_limits error ', err)
                        return None, err
                    price_precision = exchange_limits_info['price_precision']
                    min_order_size = exchange_limits_info['min_order_size']
                    init_price = data["init_price"]
                    print_position(sym, pos, init_price, start_ts)
                    
                    # 使用新的订单管理逻辑
                    order_updated = manage_grid_orders(engine, sym, data, open_orders, price_precision, min_order_size, base_amount)
                    
                    # 如果有订单更新，保存数据
                    if order_updated:
                        need_to_update = True

                except Exception as e:
                    print(f"[{sym}] 循环异常:", e)
                    break
            if need_to_update:
                save_GridPositions(GridPositions, exch, engine.account)
                need_to_update = False
            # 定期保存数据
            if time.time() - start_ts % 1800 < sleep_time * len(GridPositions):
                save_GridPositions(GridPositions, exch, engine.account)
    except KeyboardInterrupt:
        print("手动退出。")
        engine.monitor.record_operation("StrategyExit", "Grid-Order-Management", {
            "reason": "Manual interrupt",
            "uptime": time.time() - start_ts
        })

if __name__ == '__main__':
    main()