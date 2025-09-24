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


from ctos.drivers.backpack.util import align_decimal_places, round_dynamic, round_to_two_digits
from ctos.core.runtime.ExecutionEngine import pick_exchange

def get_positions_storage_path(exchange: str, account: int) -> str:
    """获取positions存储文件路径"""
    logging_dir = os.path.join(PROJECT_ROOT, 'ctos', 'core', 'io', 'logging')
    os.makedirs(logging_dir, exist_ok=True)
    return os.path.join(logging_dir, f'{exchange}_Account{account}_Grid-All-Coin_positions.json')

def save_positions(positions: dict, exchange: str, account: int) -> None:
    """保存positions到本地文件"""
    try:
        storage_path = get_positions_storage_path(exchange, account)
        data = {
            'timestamp': datetime.now().isoformat(),
            'exchange': exchange,
            'positions': positions
        }
        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\r ✓ 持仓数据已保存到: {storage_path}", end='')
    except Exception as e:
        print(f"\r ✗ 保存持仓数据失败: {e}", end='')

def load_positions(exchange: str, account: int) -> tuple[dict, bool]:
    """
    从本地文件加载positions
    返回: (positions_dict, is_valid)
    如果文件不存在或超过1小时，返回空字典和False
    """
    try:
        storage_path = get_positions_storage_path(exchange, account)
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
        return data.get('positions', {}), True
        
    except Exception as e:
        print(f"✗ 加载持仓数据失败: {e}")
        return {}, False



def get_all_positions(engine, exchange: str, use_cache: bool = True):
    """
    获取所有持仓，支持本地缓存
    返回 {symbol: {init_price, entryPrice, side, size}} 的字典
    """
    # 尝试从本地加载
    if use_cache:
        cached_positions, is_valid = load_positions(exchange, engine.account)
        if is_valid and cached_positions:
            return cached_positions
    # 从API获取最新持仓
    positions = {}
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
                    positions[sym] = {
                        "init_price": mark,
                        "avg_cost": entry,
                        "size": size,
                        "side": side,
                        'pnlUnrealized':pnlUnrealized,
                    }
        
        # 保存到本地
        if positions:
            save_positions(positions, exchange, engine.account)
            
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
=== 网格策略使用说明 ===

用法: python Grid-All-Coin.py [选项] [交易所]

选项:
  --refresh, -r, --force    强制刷新持仓缓存，忽略本地存储
  --help, -h                显示此帮助信息

交易所:
  okx, ok, o, ox, okex      欧易交易所 (默认)
  bp, backpack, b, back     Backpack交易所

示例:
  python Grid-All-Coin.py                    # 交互式选择交易所
  python Grid-All-Coin.py okx                # 使用欧易交易所
  python Grid-All-Coin.py --refresh okx      # 强制刷新缓存
  python Grid-All-Coin.py bp                 # 使用Backpack交易所

特性:
  ✓ 模糊输入支持 (支持多种输入方式)
  ✓ 本地持仓缓存 (1小时内自动加载)
  ✓ 定期缓存更新 (30分钟自动刷新)
  ✓ 区分交易所存储
  ✓ 完整操作日志记录
""")

def main():
    print("\n=== 动态监控策略 (涨跌买卖 8.88) ===")
    
    # 解析命令行参数
    force_refresh = False
    arg_ex = None
    show_help_flag = False
    acount_id = 0
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
    
    if show_help_flag:
        show_help()
        return
    
    exch, engine = pick_exchange(arg_ex, acount_id)
    print(f"使用交易所: {exch}")
    
    if force_refresh:
        print("🔄 强制刷新模式：忽略本地缓存")

    # 记录策略启动
    engine.monitor.record_operation("StrategyStart", "Grid-All-Coin", {
        "exchange": exch,
        "strategy": "Grid-All-Coin",
        "version": "2.0",
        "force_refresh": force_refresh
    })

    # 获取持仓（支持缓存）
    positions = get_all_positions(engine, exch, use_cache=True if not force_refresh else False)
    if not positions:
        print("没有持仓，退出。")
        engine.monitor.record_operation("StrategyExit", "Grid-All-Coin", {
            "reason": "No positions found"
        })
        return
    print("初始持仓:", positions)
    start_ts = time.time()
    sleep_time = 1.68
    try:
        while True:
            for sym, data in positions.items():
                try:
                    time.sleep(sleep_time)
                    pos, err = engine.cex_driver.get_position(symbol=sym, keep_origin=False)
                    if err or not pos:
                        continue
                    price_now = float(pos["markPrice"])
                    entryPrice = float(pos["entryPrice"])
                    size = float(pos["quantity"])
                    side = pos["side"]
                    init_price = data["init_price"]
                    print_position(sym, pos, init_price, start_ts)
                
                    change_pct = (price_now - init_price) / init_price
                    # 涨幅 >= 1% → 卖出
                    if change_pct >= 0.01:
                        qty = 8.88 / price_now
                        if (side == "long" and price_now > entryPrice) or side == "short":
                            oid, err = engine.place_incremental_orders(8.88, sym, "sell", soft=True)
                            if err is not None:
                                print(f"\n[{sym}] 卖单失败:", err, '\n')
                            else:
                                print(f"\n[{sym}] 卖出 {qty}, px={price_now}, id={oid}\n")
                                data["init_price"] = price_now
                                save_positions(positions, exch, engine.account)

                    # 跌幅 >= 1.11% → 买入
                    elif change_pct <= -0.0111:
                        qty = 8.88 / price_now
                        if (side == "short" and price_now < entryPrice) or side == "long":
                            qty = round_to_two_digits(qty)
                            oid, err = engine.place_incremental_orders(8.88, sym, "buy", soft=True)
                            if err is not None:
                                print(f"\n[{sym}] 买单失败:", err, '\n')
                            else:
                                print(f"\n[{sym}] 买入 {qty}, px={price_now}, id={oid}\n")
                                data["init_price"] = price_now
                                data["size"] += qty
                                save_positions(positions, exch, engine.account)
                except Exception as e:
                    print(f"[{sym}] 循环异常:", e)
                    break
            if time.time() - start_ts % 1800 < sleep_time * len(positions):
                save_positions(positions, exch, engine.account)
    except KeyboardInterrupt:
        print("手动退出。")
        engine.monitor.record_operation("StrategyExit", "Grid-All-Coin", {
            "reason": "Manual interrupt",
            "uptime": time.time() - start_ts
        })

if __name__ == '__main__':
    main()