#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import math


def add_project_paths(project_name="ctos", subpackages=None):
    """
    自动查找项目根目录，并将其及常见子包路径添加到 sys.path。
    :param project_name: 项目根目录标识（默认 'ctos')
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

from ctos.drivers.backpack.util import align_decimal_places, round_dynamic, round_to_two_digits, rate_price2order, cal_amount, BeijingTime
from ctos.core.runtime.ExecutionEngine import pick_exchange


def get_PinPositions_storage_path(exchange: str, account: int) -> str:
    """获取PinPositions存储文件路径（统一放到 PinPositions 文件夹下）"""
    logging_dir = os.path.dirname(os.path.abspath(__file__))
    default_strategy = os.path.splitext(os.path.basename(__file__))[0].upper()
    folder = os.path.join(logging_dir, "PinPositions")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f'{exchange}_Account{account}_{default_strategy}_PinPositions.json')


def save_PinPositions(PinPositions: dict, exchange: str, account: int) -> None:
    """保存PinPositions到本地文件"""
    try:
        storage_path = get_PinPositions_storage_path(exchange, account)
        data = {
            'timestamp': datetime.now().isoformat(),
            'exchange': exchange,
            'PinPositions': PinPositions
        }
        with open(storage_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\r ✓ 接针持仓数据已保存到: {storage_path}", end='')
    except Exception as e:
        print(f"\r ✗ 保存接针持仓数据失败: {e}", end='')


def load_PinPositions(exchange: str, account: int) -> tuple[dict, bool]:
    """
    从本地文件加载PinPositions
    返回: (PinPositions_dict, is_valid)
    如果文件不存在或超过6小时，返回空字典和False
    """
    try:
        storage_path = get_PinPositions_storage_path(exchange, account)
        if not os.path.exists(storage_path):
            print(f"⚠ 接针持仓数据文件不存在: {storage_path}, 将重新获取")
            return {}, False
        
        with open(storage_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 检查时间戳
        saved_time = datetime.fromisoformat(data['timestamp'])
        current_time = datetime.now()
        time_diff = current_time - saved_time
        
        # 如果超过6小时，返回无效
        if time_diff > timedelta(hours=6):
            print(f"⚠ 接针持仓数据已过期 ({time_diff}), 将重新获取")
            return {}, False
        
        # 检查交易所是否匹配
        if data.get('exchange').lower() != exchange.lower():
            print(f"⚠ 交易所不匹配 (文件: {data.get('exchange')}, 当前: {exchange}), 将重新获取")
            return {}, False
        
        print(f"✓ 从本地加载接针持仓数据 (保存时间: {saved_time.strftime('%Y-%m-%d %H:%M:%S')})")
        return data.get('PinPositions', {}), True
        
    except Exception as e:
        print(f"✗ 加载接针持仓数据失败: {e}")
        return {}, False


def get_all_PinPositions(engine, exchange: str, use_cache: bool = True):
    """
    获取所有持仓，支持本地缓存
    返回 {symbol: {current_price, entryPrice, side, size, orders}} 的字典
    """
    # 尝试从本地加载
    if use_cache:
        cached_PinPositions, is_valid = load_PinPositions(exchange, engine.account)
        if is_valid and cached_PinPositions:
            print(f"从本地加载接针持仓数据:")
            return cached_PinPositions
    
    # 从API获取最新持仓
    PinPositions = {}
    try:
        print("正在从API获取最新接针持仓数据...")
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
                    PinPositions[sym] = {
                        "current_price": mark,
                        "avg_cost": entry,
                        "size": size,
                        "side": side,
                        'pnlUnrealized': pnlUnrealized,
                        "orders": [],  # 存储所有订单ID
                        "last_check_time": time.time(),
                        "pin_caught": False,  # 是否接到针
                        "profit_threshold": 0.0,  # 盈利阈值
                    }
        
        # 保存到本地
        if PinPositions:
            save_PinPositions(PinPositions, exchange, engine.account)
            
    except Exception as e:
        print("get_all_PinPositions 异常:", e)
    return PinPositions


def calculate_order_prices(current_price: float, config: dict) -> Tuple[List[float], List[float]]:
    """
    计算买单和卖单的价格列表
    支持等差和等比数列
    """
    buy_prices = []
    sell_prices = []
    
    # 获取配置参数
    k_orders = config.get("k_orders", 3)  # 每个方向K个订单
    price_gap_pct = config.get("price_gap_pct", 0.01)  # 距离现价的比例差距
    order_gap_pct = config.get("order_gap_pct", 0.005)  # 订单之间的gap
    gap_type = config.get("gap_type", "arithmetic")  # arithmetic 或 geometric
    
    # 计算买单价格（低于现价）
    if gap_type == "arithmetic":
        # 等差数列
        for i in range(k_orders):
            price = current_price * (1 - price_gap_pct - i * order_gap_pct)
            buy_prices.append(price)
    else:
        # 等比数列
        for i in range(k_orders):
            price = current_price * ((1 - price_gap_pct) * ((1 - order_gap_pct) ** i))
            buy_prices.append(price)
    
    # 计算卖单价格（高于现价）
    if gap_type == "arithmetic":
        # 等差数列
        for i in range(k_orders):
            price = current_price * (1 + price_gap_pct + i * order_gap_pct)
            sell_prices.append(price)
    else:
        # 等比数列
        for i in range(k_orders):
            price = current_price * ((1 + price_gap_pct) * ((1 + order_gap_pct) ** i))
            sell_prices.append(price)
    
    return buy_prices, sell_prices


def calculate_order_sizes(config: dict, price: float) -> float:
    """
    计算订单数量
    支持等量、等金额、递增模式
    """
    size_mode = config.get("size_mode", "equal_amount")  # equal_amount, equal_quantity, increasing
    base_amount = config.get("base_amount", 10.0)  # 基础金额
    base_quantity = config.get("base_quantity", 0.0)  # 基础数量
    increasing_factor = config.get("increasing_factor", 1.2)  # 递增因子
    
    if size_mode == "equal_amount":
        # 等金额模式
        return base_amount 
    elif size_mode == "equal_quantity":
        # 等数量模式
        return base_quantity * price
    elif size_mode == "increasing":
        # 递增模式（这里简化处理，实际可以根据订单索引计算）
        return base_quantity * increasing_factor * price
    else:
        return base_amount


def place_pin_orders(engine, sym: str, config: dict, price_precision: int) -> Tuple[List[str], List[str]]:
    """
    布置接针订单
    返回: (buy_order_ids, sell_order_ids)
    """
    current_price = engine.cex_driver.get_price_now(sym)
    if not current_price:
        print(f"[{sym}] 无法获取当前价格")
        return [], []
    
    buy_prices, sell_prices = calculate_order_prices(current_price, config)
    buy_order_ids = []
    sell_order_ids = []
    
    # 下买单
    for i, price in enumerate(buy_prices):
        aligned_price = align_decimal_places(price_precision, price)
        size = calculate_order_sizes(config, aligned_price)
        
        try:
            orders, err = engine.place_incremental_orders(
                usdt_amount=size,
                coin=sym,
                direction="buy",
                soft=True,
                price=aligned_price
            )
            if err:
                print(f"[{sym}] 买单{i+1}失败: {err}")
                engine.monitor.record_operation("OrderPlaceFail", sym, {
                    "type": "buy",
                    "index": i+1,
                    "err": str(err),
                    "price": aligned_price,
                    "size": size
                })
            else:
                buy_order_ids.append(orders[0])
                print(f"[{sym}] 买单{i+1}已下: {size} @ {aligned_price}, id={orders[0]}")
                engine.monitor.record_operation("OrderPlaced", sym, {
                    "type": "buy",
                    "index": i+1,
                    "order_id": orders[0],
                    "price": aligned_price,
                    "size": size
                })
        except Exception as e:
            print(f"[{sym}] 买单{i+1}异常: {e}")
    
    # 下卖单
    for i, price in enumerate(sell_prices):
        aligned_price = align_decimal_places(price_precision, price)
        size = calculate_order_sizes(config, aligned_price)
        
        try:
            orders, err = engine.place_incremental_orders(
                usdt_amount=size,
                coin=sym,
                direction="sell",
                soft=True,
                price=aligned_price
            )
            if err:
                print(f"[{sym}] 卖单{i+1}失败: {err}")
                engine.monitor.record_operation("OrderPlaceFail", sym, {
                    "type": "sell",
                    "index": i+1,
                    "err": str(err),
                    "price": aligned_price,
                    "size": size
                })
            else:
                sell_order_ids.append(orders[0])
                print(f"[{sym}] 卖单{i+1}已下: {size} @ {aligned_price}, id={orders[0]}")
                engine.monitor.record_operation("OrderPlaced", sym, {
                    "type": "sell",
                    "index": i+1,
                    "order_id": orders[0],
                    "price": aligned_price,
                    "size": size
                })
        except Exception as e:
            print(f"[{sym}] 卖单{i+1}异常: {e}")
    
    return buy_order_ids, sell_order_ids


def cancel_all_orders(engine, sym: str, order_ids: List[str]) -> None:
    """撤销所有订单"""
    for order_id in order_ids:
        if order_id:
            try:
                cancel_result, cancel_err = engine.cex_driver.revoke_order(order_id=order_id, symbol=sym)
                if cancel_err:
                    print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 撤销订单 {order_id} 失败: {cancel_err}")
                else:
                    print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 已撤销订单 {order_id}")
            except Exception as e:
                print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 撤销订单 {order_id} 异常: {e}")


def check_pin_caught(engine, sym: str, data: dict, open_orders: List[str]) -> bool:
    """
    检查是否接到针（订单消失）
    返回: True if pin caught, False otherwise
    """
    current_orders = data.get("orders", [])
    if not current_orders:
        return False
    
    # 检查哪些订单消失了
    missing_orders = []
    for order_id in current_orders:
        if order_id not in open_orders:
            missing_orders.append(order_id)
    
    if missing_orders:
        print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 检测到接针！消失的订单: {missing_orders}")
        data["pin_caught"] = True
        data["caught_orders"] = missing_orders
        engine.monitor.record_operation("PinCaught", sym, {
            "missing_orders": missing_orders,
            "time": BeijingTime()
        })
        return True
    
    return False


def calculate_profit_and_close(engine, sym: str, data: dict, config: dict) -> bool:
    """
    计算盈利并平仓
    返回: True if closed, False otherwise
    """
    if not data.get("pin_caught", False):
        return False
    
    # 获取当前持仓
    try:
        positions, err = engine.cex_driver.get_position(symbol=sym, keep_origin=False)
        if err or not positions:
            print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 无法获取持仓信息")
            return False
        
        position = positions[0] if isinstance(positions, list) else positions
        current_price = float(position.get("markPrice", 0))
        entry_price = float(position.get("entryPrice", 0))
        size = float(position.get("quantity", 0))
        side = position.get("side", "long")
        
        if size == 0:
            print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 无持仓")
            return False
        
        # 计算盈利
        if side == "long":
            profit_pct = (current_price - entry_price) / entry_price
        else:
            profit_pct = (entry_price - current_price) / entry_price
        
        profit_threshold = config.get("profit_threshold", 0.01)  # 默认1%盈利阈值
        
        if profit_pct >= profit_threshold:
            print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 盈利{profit_pct:.2%} >= 阈值{profit_threshold:.2%}，开始平仓")
            
            # 平仓
            close_side = "sell" if side == "long" else "buy"
            try:
                close_order_id, err = engine.cex_driver.place_order(
                    symbol=sym,
                    side=close_side,
                    order_type="market",
                    size=size,
                    price=current_price
                )
                if err:
                    print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 平仓失败: {err}")
                    return False
                else:
                    print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 平仓成功: {size} @ {current_price}, 盈利{profit_pct:.2%}")
                    engine.monitor.record_operation("PositionClosed", sym, {
                        "profit_pct": profit_pct,
                        "profit_threshold": profit_threshold,
                        "close_order_id": close_order_id,
                        "time": BeijingTime()
                    })
                    return True
            except Exception as e:
                print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 平仓异常: {e}")
                return False
        else:
            print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 盈利{profit_pct:.2%} < 阈值{profit_threshold:.2%}，不平仓")
            return False
            
    except Exception as e:
        print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 计算盈利异常: {e}")
        return False


def manage_pin_strategy(engine, sym: str, data: dict, open_orders: List[str], price_precision: int, config: dict) -> bool:
    """
    管理接针策略逻辑
    返回: True if updated, False otherwise
    """
    current_time = time.time()
    last_check_time = data.get("last_check_time", 0)
    
    # 检查是否接到针
    pin_caught = check_pin_caught(engine, sym, data, open_orders)
    
    if pin_caught:
        # 接到针了，检查盈利并平仓
        closed = calculate_profit_and_close(engine, sym, data, config)
        if closed:
            print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 平仓成功")
            # 平仓成功，重置状态
            data["pin_caught"] = False
            data["caught_orders"] = []
            data["orders"] = []
            return True
    else:
        # 没接到针，检查是否需要重新下单
        check_interval = config.get("check_interval", 300)  # 5分钟检查一次
        if current_time - last_check_time > check_interval:
            print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 检查间隔到期，撤销所有订单重新下单")
            
            # 撤销所有订单
            cancel_all_orders(engine, sym, data.get("orders", []))
            
            # 重新下单
            buy_order_ids, sell_order_ids = place_pin_orders(engine, sym, config, price_precision)
            data["orders"] = buy_order_ids + sell_order_ids
            data["last_check_time"] = current_time
            return True
    
    return False


def print_position(account, sym, pos, start_ts):
    """打印实时仓位信息"""
    uptime = int(time.time() - start_ts)
    time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))
    
    if not pos:
        output = f"=== [接针监控] | Account {account} | 当前没有仓位： {sym} | Uptime {uptime}s | Time {time_str} ==="
    else:
        price_now = float(pos.get("markPrice", 0) or 0)
        avg_cost = float(pos.get("entryPrice", 0) or 0)
        size = float(pos.get("quantity", 0) or 0)
        side = pos.get("side", "?")
        pnlUnrealized = float(pos.get("pnlUnrealized", 0) or 0)
        
        profit_pct = (price_now - avg_cost) / avg_cost * 100 if avg_cost else 0.0
        
        hh, mm, ss = uptime // 3600, (uptime % 3600) // 60, uptime % 60
        header = f"[接针监控] {sym} | Account {account} | Uptime {hh:02d}:{mm:02d}:{ss:02d} | "
        line = (
            f"现价={round_dynamic(price_now)} | "
            f"成本={round_dynamic(avg_cost)} | "
            f"数量={round_to_two_digits(size)} | "
            f"方向={side} | "
            f"盈亏={profit_pct:+.2f}%"
        )
        output = header + line 
    
    if len(output) < 110:
        output += ' ' * (110 - len(output))
    print('\r' + output, end='')


def load_config():
    """
    加载配置文件
    支持多交易所多账户配置
    配置文件格式: pin_config_{exchange}_{account}.json
    """
    configs = []
    
    # 默认配置
    default_config = {
        "exchange": "bp",
        "account": 0,
        "k_orders": 3,  # 每个方向K个订单
        "price_gap_pct": 0.01,  # 距离现价的比例差距
        "order_gap_pct": 0.005,  # 订单之间的gap
        "gap_type": "arithmetic",  # arithmetic 或 geometric
        "size_mode": "equal_amount",  # equal_amount, equal_quantity, increasing
        "base_amount": 10.0,  # 基础金额
        "base_quantity": 0.0,  # 基础数量
        "increasing_factor": 1.2,  # 递增因子
        "profit_threshold": 0.01,  # 盈利阈值
        "check_interval": 300,  # 检查间隔（秒）
        "force_refresh": False,
        "MODE": "DEACTIVATED",
        "description": "接针策略配置 - 请根据实际情况修改参数"
    }
    
    # 尝试加载多个配置文件
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_dir = os.path.join(current_dir, "configs")
    
    # 创建配置文件夹（如果不存在）
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
        print(f"✓ 创建配置文件夹: {config_dir}")
    
    # 自适应查找交易所和账户组合
    exchange_accounts = []
    
    # 支持的交易所列表
    supported_exchanges = ["bp", "okx", "bnb"]
    
    # 支持的账户ID范围
    account_range = range(0, 7)  # 0-6
    
    # 生成所有可能的组合
    for exchange in supported_exchanges:
        for account in account_range:
            exchange_accounts.append((exchange, account))
    
    print(f"✓ 生成 {len(exchange_accounts)} 个可能的交易所-账户组合")
    
    for exchange, account in exchange_accounts:
        config_file = os.path.join(config_dir, f"pin_config_{exchange}_{account}.json")
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                if config["MODE"] == 'DEACTIVATED':
                    continue
                # 验证必要字段
                required_fields = ["exchange", "account", "k_orders", "price_gap_pct", "order_gap_pct", "profit_threshold"]
                if all(field in config for field in required_fields):
                    configs.append(config)
                    print(f"✓ 加载配置: {exchange}-{account}")
                else:
                    print(f"⚠ 配置文件缺少必要字段: {config_file}")
                    
            except Exception as e:
                print(f"✗ 加载配置文件失败 {config_file}: {e}")
        else:
            pass
    # 如果没有找到任何配置文件，使用默认配置
    if not configs:
        print("⚠ 未找到配置文件，使用默认配置")
        configs = []
    
    # 检查是否为首次运行（通过标记文件）
    first_run_flag = os.path.join(config_dir, ".first_run_flag")
    need_confirm = True
    if os.path.exists(first_run_flag):
        try:
            with open(first_run_flag, "r") as f:
                flag_content = f.read().strip()
            current_file_path = os.path.abspath(__file__)
            if flag_content == current_file_path:
                need_confirm = False
        except Exception as e:
            print(f"读取首次运行标记文件异常: {e}")
    
    if need_confirm:
        print("\n=== 检测到首次运行！请确认以下配置文件是否需要启用 ===\n")
        confirmed_configs = []
        for config in configs:
            print(f"\n------------------------------")
            print(f"配置文件: pin_config_{config['exchange']}_{config['account']}.json")
            print(json.dumps(config, ensure_ascii=False, indent=2))
            resp = input("是否启用该配置？(y/n, 默认y): ").strip().lower()
            if resp in ["", "y", "yes", "是"]:
                config["MODE"] = "ACTIVATED"
                confirmed_configs.append(config)
                print("✓ 已启用该配置。")
            else:
                config["MODE"] = "DEACTIVATED"
                confirmed_configs.append(config)
                print("✗ 已设置为未激活（MODE=DEACTIVATED）。")
            
            # 将修改后的配置写回文件
            config_file = os.path.join(config_dir, f"pin_config_{config['exchange']}_{config['account']}.json")
            try:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                print(f"✓ 配置已保存到: {config_file}")
            except Exception as e:
                print(f"✗ 保存配置文件失败: {e}")
        
        configs = confirmed_configs
        # 创建标记文件，表示已完成首次确认
        with open(first_run_flag, "w") as f:
            f.write(os.path.abspath(__file__))
        print("\n首次配置确认已完成，后续将不再提示。")
    
    return configs


def show_help():
    """显示帮助信息"""
    print("""
=== 接针策略使用说明 (配置文件版) ===

用法: python PinCatchingStrategy.py

配置文件:
  策略使用配置文件进行参数设置，配置文件位于 configs/ 文件夹下:
  configs/pin_config_{exchange}_{account}.json
  
  示例配置文件:
  - configs/pin_config_bp_0.json    # Backpack账户0
  - configs/pin_config_bp_3.json    # Backpack账户3  
  - configs/pin_config_okx_0.json   # OKX账户0

配置文件格式:
{
  "exchange": "bp",           # 交易所名称 (bp/okx)
  "account": 0,               # 账户ID (0-6)
  "k_orders": 3,              # 每个方向K个订单
  "price_gap_pct": 0.01,      # 距离现价的比例差距
  "order_gap_pct": 0.005,     # 订单之间的gap
  "gap_type": "arithmetic",   # arithmetic 或 geometric
  "size_mode": "equal_amount", # equal_amount, equal_quantity, increasing
  "base_amount": 10.0,        # 基础金额
  "profit_threshold": 0.01,   # 盈利阈值
  "check_interval": 300,      # 检查间隔（秒）
  "MODE": "ACTIVATED"         # 激活状态
}

策略特性:
  ✓ 接针策略 (基于订单消失检测)
  ✓ 上下K个订单布置 (可配置等差/等比)
  ✓ 多种数量模式 (等量/等金额/递增)
  ✓ 智能盈利检测和平仓
  ✓ 自动订单刷新机制
  ✓ 本地持仓缓存 (6小时内自动加载)
  ✓ 完整操作日志记录
  ✓ 多账户配置文件支持

策略逻辑:
  1. 自动加载所有配置文件
  2. 获取当前持仓
  3. 在现价上下布置K个订单
  4. 监控订单存活情况
  5. 如果接到针（订单消失）→ 检查盈利 → 平仓
  6. 如果没接到针 → 定期撤销重下
  7. 循环执行

配置文件优势:
  ✓ 支持多交易所多账户
  ✓ 参数持久化保存
  ✓ 自动创建默认配置
  ✓ 独立配置管理
""")


def pin_catching_strategy(engines=None, exchs=None, force_refresh=None, configs=None):
    """接针策略主函数"""
    print(f"使用交易所: {exchs}")
    if force_refresh is None:
        force_refresh = [False] * len(engines)
    
    for fr, engine, exch in zip(force_refresh, engines, exchs):
        if fr:
            print(f"🔄 强制刷新模式：忽略本地缓存 {exch}-{engine.account}")
    
    # 记录策略启动
    for engine, exch, fr in zip(engines, exchs, force_refresh):
        engine.monitor.record_operation("StrategyStart", "Pin-Catching", {
            "exchange": exch,
            "strategy": "Pin-Catching",
            "version": "1.0",
            "force_refresh": fr,
        })

    # 获取持仓（支持缓存）
    PinPositions_all = [get_all_PinPositions(engine, exch, use_cache=True if not fr else False) for engine, exch, fr in zip(engines, exchs, force_refresh)]
    for engine, PinPositions in zip(engines, PinPositions_all):
        print("初始持仓:", len(PinPositions))

    # 创建关注币种文件夹
    current_dir = os.path.dirname(os.path.abspath(__file__))
    symbols_dir = os.path.join(current_dir, "symbols")
    
    if not os.path.exists(symbols_dir):
        os.makedirs(symbols_dir)
        print(f"✓ 创建关注币种文件夹: {symbols_dir}")

    # 为每个交易所和账户组合处理关注币种
    focus_symbols_all = {}
    
    for engine, exch, PinPositions in zip(engines, exchs, PinPositions_all):
        symbols_file = f"{exch}_Account{engine.account}_focus_symbols.json"
        symbols_file_path = os.path.join(symbols_dir, symbols_file)
        
        # 读取关注币种集合
        if os.path.exists(symbols_file_path):
            try:
                with open(symbols_file_path, "r", encoding="utf-8") as f:
                    focus_symbols = set(json.load(f))
                print(f"✓ 加载关注币种: {exch}-{engine.account}", focus_symbols)
            except Exception as e:
                print(f"✗ 读取关注币种文件失败 {symbols_file_path}: {e}")
                focus_symbols = set()
        else:
            # 文件不存在，使用当前PinPositions的币种
            focus_symbols = set(PinPositions.keys())
            # 保存币种集合到文件
            try:
                with open(symbols_file_path, "w", encoding="utf-8") as f:
                    json.dump(list(focus_symbols), f, ensure_ascii=False, indent=2)
                print(f"✓ 创建关注币种文件: {symbols_file_path}")
            except Exception as e:
                print(f"✗ 保存关注币种文件失败 {symbols_file_path}: {e}")
        
        focus_symbols_all[f"{exch}_{engine.account}"] = focus_symbols
    
    # 对齐PinPositions到关注币种集合
    for engine, exch, PinPositions in zip(engines, exchs, PinPositions_all):
        key = f"{exch}_{engine.account}"
        focus_symbols = focus_symbols_all.get(key, set())
        
        # 1. 如果少了币种，则币种置空仓位
        for sym in focus_symbols:
            if sym not in PinPositions:
                print(f"{key}  [{sym}] 币种不存在，置空仓位")
                price_now = engine.cex_driver.get_price_now(sym)
                PinPositions[sym] = {
                    "current_price": price_now,
                    "avg_cost": price_now,
                    "size": 0,
                    "side": 0,
                    'pnlUnrealized': 0,
                    "orders": [],
                    "last_check_time": time.time(),
                    "pin_caught": False,
                    "profit_threshold": 0.0,
                }
        
        # 2. 如果多了币种，则撤销该仓位的订单并移除
        remove_syms = []
        for sym in list(PinPositions.keys()):
            if sym not in focus_symbols:
                # 撤销该币种的订单
                print(f" [{engine.cex_driver.cex}-{engine.account}] [{sym}] 撤销该币种的订单")
                orders = PinPositions[sym].get("orders", [])
                cancel_all_orders(engine, sym, orders)
                remove_syms.append(sym)
        
        for sym in remove_syms:
            del PinPositions[sym]

    start_ts = time.time()
    sleep_time = 2.0  # 每个账户查询间隙
    account_sleep_time = 5.0  # 所有账户查询后到下一轮的时间间隙
    need_to_update = False
    
    while True:
        try:
            for engine, PinPositions, config in zip(engines, PinPositions_all, configs):
                if config["MODE"] == "DEACTIVATED":
                    print(f"{BeijingTime()} | [{config['exchange']}-{config['account']}] 策略曾出现故障，已禁用，跳过处理")
                    continue
                print(f"\r [{engine.cex_driver.cex}-{engine.account}] 获取所有订单\r", end='')
                # 获取全局所有订单
                try:
                    open_orders, err = engine.cex_driver.get_open_orders(symbol=None, onlyOrderId=True, keep_origin=False)
                    if err:
                        print(f"\r [{engine.cex_driver.cex}-{engine.account}] 获取订单失败: {err}\r", end='')
                        time.sleep(sleep_time)
                        continue
                except Exception as e:
                    print(f"\r [{engine.cex_driver.cex}-{engine.account}] 获取订单失败: {e}\r", end='')
                    engine.monitor.record_operation("OrderGetFail", str(e), {"err": str(e), "time": BeijingTime()})
                    time.sleep(sleep_time)
                    continue
              
                if not isinstance(open_orders, list) or not open_orders:
                    open_orders = []
                
                try:
                    origin_pos, err = engine.cex_driver.get_position(symbol=None, keep_origin=False)
                except Exception as e:
                    engine.monitor.record_operation("PositionGetFail", str(e), {"err": str(e), "time": BeijingTime()})
                    print(f"获取持仓失败: {e}")
                    time.sleep(sleep_time)
                    continue
                
                if origin_pos is None:
                    origin_pos = {}
                
                poses = {}
                for pos in origin_pos:
                    poses[pos["symbol"]] = pos
                
                for sym, data in PinPositions.items():
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
                        
                        print_position(engine.account, sym, pos, start_ts)
                        
                        # 使用接针策略逻辑
                        order_updated = manage_pin_strategy(engine, sym, data, open_orders, price_precision, config)
                        if order_updated is None:
                            config["MODE"] = "DEACTIVATED"
                            need_to_update = True
                        
                        # 如果有订单更新，保存数据
                        if order_updated:
                            need_to_update = True
                            
                    except Exception as e:
                        print(f"[{sym}] 循环异常:", e)
                        engine.monitor.record_operation("LoopException", str(e), {"err": str(e), "time": BeijingTime(), "sym": sym})
                        break
                
                if need_to_update:
                    save_PinPositions(PinPositions, engine.cex_driver.cex.lower(), engine.account)
                    need_to_update = False
                
                # 定期保存数据
                if time.time() - start_ts % 1800 < sleep_time * len(PinPositions):
                    save_PinPositions(PinPositions, engine.cex_driver.cex.lower(), engine.account)
            
            # 所有账户查询后等待
            time.sleep(account_sleep_time)

        except KeyboardInterrupt:
            print("手动退出。")
            for engine in engines:
                engine.monitor.record_operation("StrategyExit", "Pin-Catching", {
                    "reason": "Manual interrupt",
                    "uptime": time.time() - start_ts
                })
            sys.exit()
        except Exception as e:
            print(f"接针策略异常:", e)
            for engine in engines:
                engine.monitor.record_operation("StrategyException", str(e), {"err": str(e), "time": BeijingTime()})
            time.sleep(account_sleep_time)
            continue


if __name__ == '__main__':
    print("\n=== 接针策略 (配置文件版) ===")

    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h']:
        show_help()
        sys.exit()
    
    # 加载配置文件
    configs = load_config()
    
    if not configs:
        print("❌ 未找到有效配置文件，退出")
        sys.exit(1)
    else:
        print(f"✓ 加载 {len(configs)} 个配置文件")
        for config in configs:
            print(f"  - {config['exchange']}-{config['account']}")
            print(json.dumps(config, ensure_ascii=False, indent=2))
            print(f"  - {config['exchange']}-{config['account']}\n")
    
    # 自动用当前文件名（去除后缀）作为默认策略名，细节默认为COMMON
    default_strategy = os.path.splitext(os.path.basename(__file__))[0].upper()
    
    # 根据配置文件初始化交易所和引擎
    engines = []
    exchs = []
    force_refresh = []    
    for config in configs:
        try:
            exchange, account = config["exchange"], config["account"]
            exch, engine = pick_exchange(exchange, account, strategy=default_strategy, strategy_detail="COMMON")
            engines.append(engine)
            exchs.append(exch)
            force_refresh.append(config.get("force_refresh", False))
            print(f"✓ 初始化 {exchange}-{account} 成功")
        except Exception as e:
            print(f"✗ 初始化 {config['exchange']}-{config['account']} 失败: {e}")
    
    if not engines:
        print("❌ 没有成功初始化任何交易所，退出")
        sys.exit(1)
    
    print(f"🚀 启动接针策略，共 {len(engines)} 个账户, {exchs}")
    pin_catching_strategy(engines, exchs, force_refresh, configs)
