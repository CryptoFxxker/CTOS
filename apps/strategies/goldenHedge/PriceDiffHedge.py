# -*- coding: utf-8 -*-
# 价差对冲策略：基于XAUT/PAXG价差均值进行对冲交易

import os
import sys
import time
import json
from pathlib import Path

def add_project_paths(project_name="ctos"):
    """自动查找项目根目录，并将其及常见子包路径添加到 sys.path"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = None
    path = current_dir
    while path != os.path.dirname(path):
        if os.path.basename(path) == project_name or os.path.exists(os.path.join(path, ".git")):
            project_root = path
            break
        path = os.path.dirname(path)
    if not project_root:
        raise RuntimeError(f"未找到项目根目录（包含 {project_name} 或 .git）")
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root

_PROJECT_ROOT = add_project_paths()

from ctos.core.runtime.ExecutionEngine import pick_exchange
from ctos.drivers.okx.util import BeijingTime, save_para, load_para

# 配置文件路径
current_dir = os.path.dirname(os.path.abspath(__file__))
config_file = os.path.join(current_dir, "price_diff_hedge_config.json")
data_file = os.path.join(current_dir, "price_diff_data.json")

def load_strategy_config():
    """加载策略配置"""
    default_config = {
        "okx_account_id": 0,
        "bp_account_id": 0,
        "okx_symbol": "xaut",
        "bp_symbol": "paxg",
        "check_interval": 30,  # 检查间隔（秒）
        "data_batch_size": 3000,  # 数据批次大小（达到此倍数时计算均值）
        "order_amount": 1000.0,  # 每次下单金额（USDT）
        "total_hedge_amount": 100000.0,  # 总对冲金额（USDT）
        "price_diff_mean": None,  # 价差均值（自动计算）
        "price_diff_threshold": 0.5,  # 价差阈值（相对于均值的百分比，50%）
        "description": "价差对冲策略：基于XAUT/PAXG价差均值进行对冲交易"
    }
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 合并默认配置
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
            print(f"✓ 加载策略配置: {config_file}")
            return config
        except Exception as e:
            print(f"✗ 加载策略配置失败: {e}，使用默认配置")
            return default_config
    else:
        save_strategy_config(default_config)
        return default_config

def save_strategy_config(config):
    """保存策略配置"""
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"✓ 保存策略配置: {config_file}")
    except Exception as e:
        print(f"✗ 保存策略配置失败: {e}")

def load_price_data():
    """加载价格数据"""
    default_data = {
        "data_points": [],
        "last_update": None
    }
    
    if os.path.exists(data_file):
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # 确保数据结构完整
            if "data_points" not in data:
                data["data_points"] = []
            if "last_update" not in data:
                data["last_update"] = None
            return data
        except Exception as e:
            print(f"✗ 加载价格数据失败: {e}，使用默认数据")
            return default_data
    else:
        save_price_data(default_data)
        return default_data

def save_price_data(data):
    """保存价格数据"""
    try:
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"✗ 保存价格数据失败: {e}")

def collect_price_and_funding_data(engine_okx, engine_bp, config):
    """
    收集价格和资金费率数据
    返回: (okx_price, okx_funding_rate, bp_price, bp_funding_rate, error)
    """
    try:
        # 获取价格
        okx_price = engine_okx.cex_driver.get_price_now(config['okx_symbol'])
        bp_price = engine_bp.cex_driver.get_price_now(config['bp_symbol'])
        
        if not okx_price or not bp_price:
            return None, None, None, None, "无法获取价格"
        
        # 获取资金费率
        okx_fees_result, okx_fees_err = engine_okx.cex_driver.fees(symbol=config['okx_symbol'], instType='SWAP', keep_origin=False)
        bp_fees_result, bp_fees_err = engine_bp.cex_driver.fees(symbol=config['bp_symbol'], instType='PERP', keep_origin=False)
        
        if okx_fees_err or bp_fees_err:
            return None, None, None, None, f"获取资金费率失败: OKX={okx_fees_err}, BP={bp_fees_err}"
        
        okx_funding_rate = okx_fees_result.get('fundingRate_hourly') if okx_fees_result else None
        bp_funding_rate = bp_fees_result.get('fundingRate_hourly') if bp_fees_result else None
        
        if okx_funding_rate is None or bp_funding_rate is None:
            return None, None, None, None, "资金费率为空"
        
        return okx_price, okx_funding_rate, bp_price, bp_funding_rate, None
    
    except Exception as e:
        return None, None, None, None, str(e)

def calculate_price_diff_mean(data_points, batch_size=3000):
    """
    计算价差均值
    当数据点达到batch_size的倍数时，计算均值
    """
    if len(data_points) == 0:
        return None
    
    # 检查是否是batch_size的倍数
    if len(data_points) % batch_size != 0:
        return None
    
    # 计算所有数据点的价差均值
    price_diffs = []
    for point in data_points:
        if 'price_diff' in point and point['price_diff'] is not None:
            price_diffs.append(point['price_diff'])
    
    if len(price_diffs) == 0:
        return None
    
    mean_diff = sum(price_diffs) / len(price_diffs)
    return mean_diff

def check_orders_filled(engine, symbol, order_ids):
    """
    检查订单是否全部成交
    使用get_open_orders接口检查订单是否还在未完成订单列表中
    返回: (all_filled, error)
    """
    try:
        # 使用get_open_orders接口检查未完成订单
        open_orders, err = engine.cex_driver.get_open_orders(symbol=symbol, onlyOrderId=True, keep_origin=False)
        if err:
            return False, err
        
        # 如果返回的是订单ID列表
        if isinstance(open_orders, list):
            # 转换为字符串列表以便比较
            open_order_ids = [str(oid) for oid in open_orders]
            
            # 检查指定的订单ID是否还在未完成订单列表中
            for order_id in order_ids:
                order_id_str = str(order_id)
                if order_id_str in open_order_ids:
                    return False, None  # 还有未成交的订单
            
            # 所有订单都不在未完成列表中，说明都成交了
            return True, None
        elif open_orders is None:
            # 返回None可能表示没有未完成订单
            return True, None
        
        return False, "无法解析订单状态"
    
    except Exception as e:
        return False, str(e)

def execute_hedge_orders(engine_okx, engine_bp, config, price_diff, price_diff_mean):
    """
    执行对冲订单
    每次下2个反向单（1000U），等待成交后再继续，直到总共100000U
    无论价差高于还是低于均值，都往价差收敛方向做对冲
    """
    try:
        total_amount = 0.0
        target_amount = config.get('total_hedge_amount', 100000.0)
        order_amount = config.get('order_amount', 1000.0)
        
        # 判断价差方向：无论价差高于还是低于均值，都往收敛方向做对冲
        # 如果当前价差 > 均值，说明XAUT相对PAXG更贵，需要做空XAUT，做多PAXG（让价差下降）
        # 如果当前价差 < 均值，说明XAUT相对PAXG更便宜，需要做多XAUT，做空PAXG（让价差上升）
        # 目标：让价差回归均值
        
        if price_diff > price_diff_mean:
            # 价差偏高，做空XAUT，做多PAXG（让价差收敛到均值）
            okx_side = 'sell'
            bp_side = 'buy'
            direction_desc = f"价差偏高({price_diff:.6f} > {price_diff_mean:.6f})，做空XAUT做多PAXG"
        else:
            # 价差偏低，做多XAUT，做空PAXG（让价差收敛到均值）
            okx_side = 'buy'
            bp_side = 'sell'
            direction_desc = f"价差偏低({price_diff:.6f} < {price_diff_mean:.6f})，做多XAUT做空PAXG"
        
        print(f"{BeijingTime()} 🎯 开始对冲: {direction_desc} | 当前价差: {price_diff:.6f} | 均值: {price_diff_mean:.6f}")
        
        while total_amount < target_amount:
            # 获取当前价格，用于限价单
            okx_current_price = engine_okx.cex_driver.get_price_now(config['okx_symbol'])
            bp_current_price = engine_bp.cex_driver.get_price_now(config['bp_symbol'])
            
            if not okx_current_price or not bp_current_price:
                return False, "无法获取当前价格"
            
            # 计算限价单价格（在现价基础上微调，提高挂单成交概率）
            # 买单：以当前价格略低0.01下单（买单更容易成交）
            # 卖单：以当前价格略高0.01下单（卖单更容易成交）
            if okx_side == 'buy':
                okx_order_price = okx_current_price - 0.1   
            else:
                okx_order_price = okx_current_price + 0.1
            
            if bp_side == 'buy':
                bp_order_price = bp_current_price - 0.01
            else:
                bp_order_price = bp_current_price + 0.01
            
            # 下2个反向限价单（挂价单）
            print(f"{BeijingTime()} 📤 下单: OKX {okx_side} {order_amount}U @ {okx_order_price:.4f}, BP {bp_side} {order_amount}U @ {bp_order_price:.4f}")
            
            oid_okx, err_okx = engine_okx.place_incremental_orders(order_amount, config['okx_symbol'], okx_side, soft=True, price=okx_order_price)
            oid_bp, err_bp = engine_bp.place_incremental_orders(order_amount, config['bp_symbol'], bp_side, soft=True, price=bp_order_price)
            
            if err_okx or err_bp:
                print(f"{BeijingTime()} ❌ 下单失败: OKX={err_okx}, BP={err_bp}")
                return False, f"下单失败: OKX={err_okx}, BP={err_bp}"
            
            # 获取订单ID（place_incremental_orders返回的是列表）
            okx_order_id = oid_okx[0] if isinstance(oid_okx, list) and len(oid_okx) > 0 else oid_okx
            bp_order_id = oid_bp[0] if isinstance(oid_bp, list) and len(oid_bp) > 0 else oid_bp
            
            order_ids = [okx_order_id, bp_order_id]
            print(f"{BeijingTime()} ⏳ 等待订单成交: OKX订单={okx_order_id}, BP订单={bp_order_id}")
            
            # 等待订单成交
            max_wait_time = 600  # 最多等待5分钟
            wait_start = time.time()
            all_filled = False
            
            while time.time() - wait_start < max_wait_time:
                # 检查OKX订单
                okx_filled, okx_err = check_orders_filled(engine_okx, config['okx_symbol'], [okx_order_id])
                if okx_err:
                    print(f"{BeijingTime()} ⚠️ 检查OKX订单状态失败: {okx_err}")
                
                # 检查BP订单
                bp_filled, bp_err = check_orders_filled(engine_bp, config['bp_symbol'], [bp_order_id])
                if bp_err:
                    print(f"{BeijingTime()} ⚠️ 检查BP订单状态失败: {bp_err}")
                
                if okx_filled and bp_filled:
                    all_filled = True
                    break
                
                time.sleep(2)  # 每2秒检查一次
            
            if not all_filled:
                print(f"{BeijingTime()} ⚠️ 订单未在{max_wait_time}秒内全部成交，继续下一批")
                # 可以选择继续或取消未成交订单
                # 这里选择继续，实际使用中可以根据需要调整
            
            total_amount += order_amount * 1
            print(f"{BeijingTime()} ✅ 已对冲: {total_amount:.2f}U / {target_amount:.2f}U")
            
            if total_amount >= target_amount:
                break
            
            time.sleep(1)  # 批次之间稍作等待
        
        print(f"{BeijingTime()} ✅ 对冲完成: 总计 {total_amount:.2f}U")
        return True, f"对冲完成: {total_amount:.2f}U"
    
    except Exception as e:
        return False, f"对冲执行失败: {str(e)}"

if __name__ == '__main__':
    # 自动用当前文件名（去除后缀）作为默认策略名
    default_strategy = os.path.splitext(os.path.basename(__file__))[0].upper()
    
    # 加载配置和数据
    config = load_strategy_config()
    price_data = load_price_data()
    last_config_mtime = os.path.getmtime(config_file) if os.path.exists(config_file) else 0
    
    # 初始化交易所和引擎
    try:
        exch_okx, engine_okx = pick_exchange('okx', config['okx_account_id'], strategy=default_strategy, strategy_detail="COMMON")
        exch_bp, engine_bp = pick_exchange('bp', config['bp_account_id'], strategy=default_strategy, strategy_detail="COMMON")
        print(f"✓ 初始化 OKX-{config['okx_account_id']} 和 BP-{config['bp_account_id']} 成功")
    except Exception as e:
        print(f"✗ 初始化交易所失败: {e}")
        sys.exit(1)
    
    print(f"🚀 启动价差对冲策略")
    print(f"   OKX追踪: {config['okx_symbol'].upper()}")
    print(f"   BP追踪: {config['bp_symbol'].upper()}")
    print(f"   当前数据点: {len(price_data['data_points'])}")
    print(f"   价差均值: {config.get('price_diff_mean', '未计算')}")
    start_time = time.time()
    
    try:
        while True:
            # 检查配置文件是否被修改，热更新参数
            if os.path.exists(config_file):
                current_mtime = os.path.getmtime(config_file)
                if current_mtime != last_config_mtime:
                    print(f"{BeijingTime()} 🔄 检测到配置文件更改，重新加载配置...")
                    config = load_strategy_config()
                    last_config_mtime = current_mtime
            
            # 收集价格和资金费率数据
            okx_price, okx_funding, bp_price, bp_funding, err = collect_price_and_funding_data(
                engine_okx, engine_bp, config
            )
            
            if err:
                print(f"{BeijingTime()} ⚠️ 数据收集失败: {err}")
                time.sleep(config.get('check_interval', 30))
                continue
            
            # 计算价差（XAUT价格 - PAXG价格）
            price_diff = okx_price - bp_price
            
            # 保存数据点
            current_time_ms = int(time.time() * 1000)
            data_point = {
                'timestamp': current_time_ms,
                'okx_price': okx_price,
                'bp_price': bp_price,
                'price_diff': price_diff,
                'okx_funding_rate': okx_funding,
                'bp_funding_rate': bp_funding,
                'funding_rate_diff': okx_funding - bp_funding if okx_funding and bp_funding else None
            }
            
            price_data['data_points'].append(data_point)
            price_data['last_update'] = current_time_ms
            save_price_data(price_data)
            
            # 检查是否需要计算价差均值
            batch_size = config.get('data_batch_size', 3000)
            data_count = len(price_data['data_points'])
            
            if data_count > 0 and data_count % batch_size == 0:
                # 计算价差均值
                mean_diff = calculate_price_diff_mean(price_data['data_points'], batch_size)
                if mean_diff is not None:
                    config['price_diff_mean'] = mean_diff
                    save_strategy_config(config)
                    print(f"{BeijingTime()} 📊 计算价差均值: {mean_diff:.6f} (基于 {data_count} 个数据点)")
            
            # 如果有价差均值，检查是否需要执行对冲
            price_diff_mean = config.get('price_diff_mean')
            if price_diff_mean is not None:
                threshold = config.get('price_diff_threshold', 0.5)
                
                # 判断是否需要对冲：
                # 1. 如果价差 > 均值 * (1 + threshold)，说明价差超过均值50%，执行对冲
                # 2. 如果价差 < 均值 * (1 - threshold)，说明价差小于均值50%，执行对冲
                # 两种情况都往价差收敛方向做对冲
                
                upper_bound = price_diff_mean * (1 + threshold)  # 均值 * 1.5
                lower_bound = price_diff_mean * (1 - threshold)  # 均值 * 0.5
                
                should_hedge = False
                hedge_reason = ""
                
                if price_diff > upper_bound:
                    should_hedge = True
                    deviation_pct = ((price_diff - price_diff_mean) / price_diff_mean) * 100
                    hedge_reason = f"价差超过均值{deviation_pct:.2f}% (当前: {price_diff:.6f} > 上限: {upper_bound:.6f})"
                elif price_diff < lower_bound:
                    should_hedge = True
                    deviation_pct = ((price_diff_mean - price_diff) / price_diff_mean) * 100
                    hedge_reason = f"价差小于均值{deviation_pct:.2f}% (当前: {price_diff:.6f} < 下限: {lower_bound:.6f})"
                
                if should_hedge:
                    print(f"{BeijingTime()} 🎯 触发对冲条件: {hedge_reason}")
                    hedge_success, hedge_msg = execute_hedge_orders(
                        engine_okx, engine_bp, config, price_diff, price_diff_mean
                    )
                    if hedge_success:
                        print(f"{BeijingTime()} ✅ {hedge_msg}")
                    else:
                        print(f"{BeijingTime()} ❌ {hedge_msg}")
                    # 对冲后等待一段时间，避免频繁交易
                    time.sleep(60)
                else:
                    # 显示状态
                    elapsed_seconds = int(time.time() - start_time)
                    days, remainder = divmod(elapsed_seconds, 86400)
                    hours, remainder = divmod(remainder, 3600)
                    minutes, _ = divmod(remainder, 60)
                    
                    status_msg = (
                        f"{BeijingTime()} 📊 数据: {data_count} | "
                        f"价差: {price_diff:.6f} | 均值: {price_diff_mean:.6f} | "
                        f"偏离: {deviation_pct*100:.2f}% | "
                        f"运行: {days}天{hours:02d}时{minutes:02d}分"
                    )
                    print(f"\r{status_msg}", end='')
            else:
                # 还没有价差均值，只显示数据收集状态
                elapsed_seconds = int(time.time() - start_time)
                days, remainder = divmod(elapsed_seconds, 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes, _ = divmod(remainder, 60)
                
                status_msg = (
                    f"{BeijingTime()} 📊 数据收集: {data_count}/{batch_size} | "
                    f"价差: {price_diff:.6f} | "
                    f"运行: {days}天{hours:02d}时{minutes:02d}分"
                )
                print(f"\r{status_msg}", end='')
            
            # 等待下一轮检查
            check_interval = config.get('check_interval', 30)
            time.sleep(check_interval)
    
    except KeyboardInterrupt:
        print(f"\n{BeijingTime()} ⏹️ 手动停止策略")
        save_strategy_config(config)
        save_price_data(price_data)
        print("✓ 策略状态和数据已保存")
        sys.exit(0)
    except Exception as e:
        print(f"\n{BeijingTime()} ❌ 策略运行异常: {e}")
        import traceback
        traceback.print_exc()
        save_strategy_config(config)
        save_price_data(price_data)
        print("✓ 异常状态和数据已保存")
        sys.exit(1)

