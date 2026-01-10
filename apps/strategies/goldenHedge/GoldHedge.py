# -*- coding: utf-8 -*-
# 黄金对冲策略：跨交易所xautt/PAXG价格比马丁网格 + 资金费套利

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
config_file = os.path.join(current_dir, "gold_hedge_config.json")

def load_strategy_config():
    """加载策略配置"""
    default_config = {
        "okx_account_id": 0,
        "bp_account_id": 0,
        "okx_symbol": "xauttt",
        "bp_symbol": "paxg",
        "base_balance_okx": 1000.0,
        "base_balance_bp": 1000.0,
        "current_balance_okx": 1000.0,
        "current_balance_bp": 1000.0,
        "leverage_okx": 1.0,
        "leverage_bp": 1.0,
        "add_times": 0,
        "reduce_times": 0,
        "max_leverage": 3.0,
        "min_leverage": 0.3,
        "add_position_rate": 0.005,
        "reduce_position_rate": 0.005,
        "leverage_change_rate": 0.05,
        "price_ratio_base": 1.0,  # 价格比基准值（xautt/PAXG）
        "price_ratio_threshold": 0.01,  # 价格比偏离阈值（1%）
        "funding_rate_diff_threshold": 0.0001,  # 资金费率差异阈值（0.01%每小时）
        "funding_arbitrage_amount": 100.0,  # 资金费套利金额（USDT）
        "funding_history_max_size": 100,  # 资金费率历史记录最大数量
        "check_interval": 30,  # 检查间隔（秒）
        "need_to_init": True,
        "need_to_reset_base_balance": False,
        "funding_rate_history": [],  # 资金费率历史数据（自动更新）
        "funding_rate_stats": {},  # 资金费率统计信息（自动更新）
        "funding_arbitrage_log": [],  # 资金费套利操作日志（自动更新）
        "description": "黄金对冲策略：xautt/PAXG价格比马丁网格 + 资金费套利"
    }
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            # 合并默认配置，确保新字段存在
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

def get_funding_rate_full(engine, symbol, instType='SWAP'):
    """
    获取完整的资金费率信息，包括结算时间
    返回: (funding_rate_hourly, funding_rate_period, period_hours, funding_time_ms, next_funding_time_ms, error)
    """
    try:
        # 先获取原始数据以获取nextFundingTime
        fees_result_raw, err_raw = engine.cex_driver.fees(symbol=symbol, instType=instType, keep_origin=True)
        if err_raw:
            return None, None, None, None, None, err_raw
        
        # 再获取标准化数据
        fees_result, err = engine.cex_driver.fees(symbol=symbol, instType=instType, keep_origin=False)
        if err:
            return None, None, None, None, None, err
        
        if fees_result:
            funding_rate_hourly = fees_result.get('fundingRate_hourly')
            funding_rate_period = fees_result.get('fundingRate_period')
            period_hours = fees_result.get('period_hours', 8.0)
            funding_time_ms = fees_result.get('fundingTime')
            
            # 如果hourly为空，尝试从period计算
            if funding_rate_hourly is None and funding_rate_period is not None and period_hours:
                funding_rate_hourly = funding_rate_period / period_hours
            
            # 从原始数据中提取nextFundingTime
            next_funding_time_ms = None
            try:
                # OKX格式：{'code': '0', 'data': [{ 'nextFundingTime', ... }]}
                if isinstance(fees_result_raw, dict):
                    data_list = fees_result_raw.get('data')
                    if isinstance(data_list, list) and data_list:
                        d0 = data_list[0]
                        next_funding_time_ms = d0.get('nextFundingTime')
                        if next_funding_time_ms:
                            next_funding_time_ms = int(next_funding_time_ms)
                    # 如果没有nextFundingTime，尝试从intervalEndTimestamp计算（Backpack格式）
                    if not next_funding_time_ms:
                        # Backpack可能返回的是列表格式，包含intervalEndTimestamp
                        if isinstance(data_list, list) and data_list:
                            latest = data_list[-1] if data_list else {}
                            interval_end = latest.get('intervalEndTimestamp')
                            if interval_end:
                                from datetime import datetime, timezone
                                try:
                                    dt = datetime.strptime(str(interval_end), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=timezone.utc)
                                    next_funding_time_ms = int(dt.timestamp() * 1000)
                                except:
                                    pass
                        # 如果还是没有，根据period_hours计算下一个结算时间
                        if not next_funding_time_ms and funding_time_ms and period_hours:
                            next_funding_time_ms = int(funding_time_ms + period_hours * 3600 * 1000)
            except Exception as e:
                # 如果解析失败，根据period_hours计算下一个结算时间
                if funding_time_ms and period_hours:
                    next_funding_time_ms = int(funding_time_ms + period_hours * 3600 * 1000)
            
            return funding_rate_hourly, funding_rate_period, period_hours, funding_time_ms, next_funding_time_ms, None
        return None, None, None, None, None, "未获取到资金费率数据"
    except Exception as e:
        return None, None, None, None, None, str(e)

def calculate_price_ratio(xautt_price, paxg_price):
    """计算价格比（xautt/PAXG）"""
    if paxg_price and paxg_price > 0:
        return xautt_price / paxg_price
    return None

def execute_martin_grid(engine_okx, engine_bp, config):
    """
    执行马丁网格逻辑：根据价格比偏离进行加仓/减仓
    """
    try:
        # 获取当前价格
        xaut_price = engine_okx.cex_driver.get_price_now(config['okx_symbol'])
        paxg_price = engine_bp.cex_driver.get_price_now(config['bp_symbol'])
        
        if not xaut_price or not paxg_price:
            return False, "无法获取价格"
        
        # 计算价格比
        price_ratio = calculate_price_ratio(xaut_price, paxg_price)
        if price_ratio is None:
            return False, "价格比计算失败"
        
        # 计算偏离度
        base_ratio = config.get('price_ratio_base', 1.0)
        if base_ratio <= 0:
            # 首次运行，设置基准价格比
            config['price_ratio_base'] = price_ratio
            save_strategy_config(config)
            return False, f"设置基准价格比: {price_ratio:.6f}"
        
        ratio_deviation = (price_ratio - base_ratio) / base_ratio
        threshold = config.get('price_ratio_threshold', 0.01)
        
        # 获取当前余额
        balance_okx = engine_okx.cex_driver.fetch_balance()
        balance_bp = engine_bp.cex_driver.fetch_balance()
        
        leverage_okx = config.get('leverage_okx', 1.0)
        leverage_bp = config.get('leverage_bp', 1.0)
        base_balance_okx = config.get('base_balance_okx', balance_okx)
        base_balance_bp = config.get('base_balance_bp', balance_bp)
        
        add_times = config.get('add_times', 0)
        reduce_times = config.get('reduce_times', 0)
        add_position_rate = config.get('add_position_rate', 0.005)
        reduce_position_rate = config.get('reduce_position_rate', 0.005)
        max_leverage = config.get('max_leverage', 3.0)
        min_leverage = config.get('min_leverage', 0.3)
        leverage_change_rate = config.get('leverage_change_rate', 0.05)
        
        # 计算目标余额
        down_target_okx = base_balance_okx - base_balance_okx * leverage_okx * add_position_rate * (1 + add_times / 10)
        down_target_bp = base_balance_bp - base_balance_bp * leverage_bp * add_position_rate * (1 + add_times / 10)
        up_target_okx = base_balance_okx + 2 * base_balance_okx * leverage_okx * reduce_position_rate * (1 + reduce_times / 10)
        up_target_bp = base_balance_bp + 2 * base_balance_bp * leverage_bp * reduce_position_rate * (1 + reduce_times / 10)
        
        # 判断加仓/减仓条件
        should_add = (ratio_deviation > threshold or balance_okx < down_target_okx or balance_bp < down_target_bp) and leverage_okx < max_leverage
        should_reduce = (ratio_deviation < -threshold or balance_okx > up_target_okx or balance_bp > up_target_bp) and leverage_okx > min_leverage
        
        if should_add:
            # 加仓逻辑
            add_times += 1
            reduce_times = max(0, reduce_times - 1)
            leverage_change = leverage_change_rate * pow(2, add_times / 10)
            config['leverage_okx'] = min(max_leverage, leverage_okx + leverage_change)
            config['leverage_bp'] = min(max_leverage, leverage_bp + leverage_change)
            config['add_times'] = add_times
            config['reduce_times'] = reduce_times
            config['base_balance_okx'] = balance_okx
            config['base_balance_bp'] = balance_bp
            
            # 执行加仓：OKX做多XAUT，BP做空PAXG（或相反，取决于价格比）
            amount_okx = balance_okx * leverage_okx * add_position_rate * (1 + add_times / 10)
            amount_bp = balance_bp * leverage_bp * add_position_rate * (1 + add_times / 10)
            
            if ratio_deviation > threshold:
                # XAUT相对PAXG偏高，做多XAUT，做空PAXG
                oid_okx, err_okx = engine_okx.place_incremental_orders(amount_okx, config['okx_symbol'], 'buy', soft=False)
                oid_bp, err_bp = engine_bp.place_incremental_orders(amount_bp, config['bp_symbol'], 'sell', soft=False)
                if err_okx or err_bp:
                    return False, f"加仓下单失败: OKX={err_okx}, BP={err_bp}"
            else:
                # 余额下降，加仓对冲（两个都做多）
                oid_okx, err_okx = engine_okx.place_incremental_orders(amount_okx, config['okx_symbol'], 'buy', soft=False)
                oid_bp, err_bp = engine_bp.place_incremental_orders(amount_bp, config['bp_symbol'], 'buy', soft=False)
                if err_okx or err_bp:
                    return False, f"加仓下单失败: OKX={err_okx}, BP={err_bp}"
            
            print(f"{BeijingTime()} ✅ 加仓完成 | 价格比: {price_ratio:.6f} (偏离: {ratio_deviation*100:.2f}%) | 杠杆: {config['leverage_okx']:.2f}")
            return True, "加仓完成"
        
        elif should_reduce:
            # 减仓逻辑
            reduce_times += 1
            add_times = max(0, add_times - 1)
            leverage_change = leverage_change_rate * pow(2, reduce_times / 10)
            config['leverage_okx'] = max(min_leverage, leverage_okx - leverage_change)
            config['leverage_bp'] = max(min_leverage, leverage_bp - leverage_change)
            config['add_times'] = add_times
            config['reduce_times'] = reduce_times
            config['base_balance_okx'] += base_balance_okx * leverage_okx * reduce_position_rate * (1 + reduce_times / 10)
            config['base_balance_bp'] += base_balance_bp * leverage_bp * reduce_position_rate * (1 + reduce_times / 10)
            
            # 执行减仓
            amount_okx = base_balance_okx * leverage_okx * reduce_position_rate * (1 + reduce_times / 10)
            amount_bp = base_balance_bp * leverage_bp * reduce_position_rate * (1 + reduce_times / 10)
            oid_okx, err_okx = engine_okx.place_incremental_orders(amount_okx, config['okx_symbol'], 'sell', soft=False)
            oid_bp, err_bp = engine_bp.place_incremental_orders(amount_bp, config['bp_symbol'], 'sell', soft=False)
            if err_okx or err_bp:
                return False, f"减仓下单失败: OKX={err_okx}, BP={err_bp}"
            
            print(f"{BeijingTime()} ✅ 减仓完成 | 价格比: {price_ratio:.6f} (偏离: {ratio_deviation*100:.2f}%) | 杠杆: {config['leverage_okx']:.2f}")
            return True, "减仓完成"
        
        return False, f"价格比: {price_ratio:.6f} (偏离: {ratio_deviation*100:.2f}%)，无需操作"
    
    except Exception as e:
        return False, f"马丁网格执行失败: {str(e)}"

def update_funding_rate_history(config, okx_fr_hourly, bp_fr_hourly, okx_fr_period, bp_fr_period, 
                                okx_period, bp_period, timestamp, is_settlement=False):
    """
    更新资金费率历史数据，实现遗忘机制
    为预测模型准备特征数据
    """
    if 'funding_rate_history' not in config:
        config['funding_rate_history'] = []
    
    history = config['funding_rate_history']
    
    # 计算实际费率差（按最长周期）
    max_period = max(okx_period or 8.0, bp_period or 1.0)
    okx_actual_rate = okx_fr_period if okx_fr_period is not None else (okx_fr_hourly * (okx_period or 8.0))
    bp_actual_rate = bp_fr_period if bp_fr_period is not None else (bp_fr_hourly * (bp_period or 1.0))
    
    # 转换为最长周期的费率
    okx_rate_for_max_period = okx_actual_rate * (max_period / (okx_period or 8.0))
    bp_rate_for_max_period = bp_actual_rate * (max_period / (bp_period or 1.0))
    actual_rate_diff = okx_rate_for_max_period - bp_rate_for_max_period
    
    # 添加新数据点（包含更多特征，为预测模型准备）
    history.append({
        'timestamp': timestamp,
        'okx_rate_hourly': okx_fr_hourly,
        'bp_rate_hourly': bp_fr_hourly,
        'okx_rate_period': okx_fr_period,
        'bp_rate_period': bp_fr_period,
        'okx_rate_actual': okx_rate_for_max_period,  # 按最长周期转换后的实际费率
        'bp_rate_actual': bp_rate_for_max_period,
        'okx_period_hours': okx_period,
        'bp_period_hours': bp_period,
        'max_period_hours': max_period,
        'rate_diff_hourly': okx_fr_hourly - bp_fr_hourly if okx_fr_hourly and bp_fr_hourly else None,
        'rate_diff_actual': actual_rate_diff,  # 实际费率差（按最长周期）
        'is_settlement': is_settlement  # 标记是否为结算时刻
    })
    
    # 遗忘机制：只保留最近N条记录（默认保留最近200条，约16-20天的数据）
    max_history_size = config.get('funding_history_max_size', 200)
    if len(history) > max_history_size:
        history = history[-max_history_size:]
        config['funding_rate_history'] = history
    
    # 计算统计信息（为预测模型提供特征）
    if len(history) > 0:
        # 结算时刻的数据
        settlement_data = [h for h in history if h.get('is_settlement', False)]
        # 所有数据
        all_data = history
        
        # 计算实际费率差的统计
        valid_actual_diffs = [h['rate_diff_actual'] for h in all_data if h.get('rate_diff_actual') is not None]
        valid_hourly_diffs = [h['rate_diff_hourly'] for h in all_data if h.get('rate_diff_hourly') is not None]
        
        if valid_actual_diffs:
            mean_actual = sum(valid_actual_diffs) / len(valid_actual_diffs)
            config['funding_rate_stats'] = {
                # 实际费率差统计（按最长周期）
                'mean_diff_actual': mean_actual,
                'max_diff_actual': max(valid_actual_diffs),
                'min_diff_actual': min(valid_actual_diffs),
                'std_diff_actual': (sum((x - mean_actual)**2 for x in valid_actual_diffs) / len(valid_actual_diffs))**0.5 if len(valid_actual_diffs) > 1 else 0,
                # 小时费率差统计
                'mean_diff_hourly': sum(valid_hourly_diffs) / len(valid_hourly_diffs) if valid_hourly_diffs else None,
                'max_diff_hourly': max(valid_hourly_diffs) if valid_hourly_diffs else None,
                'min_diff_hourly': min(valid_hourly_diffs) if valid_hourly_diffs else None,
                # 数据量
                'count_total': len(all_data),
                'count_settlement': len(settlement_data),
                'last_update': timestamp,
                # 最近N条数据的趋势（为预测模型提供）
                'recent_trend': None
            }
            
            # 计算最近10条数据的趋势（简单线性回归斜率）
            if len(valid_actual_diffs) >= 10:
                recent_diffs = valid_actual_diffs[-10:]
                recent_indices = list(range(len(recent_diffs)))
                n = len(recent_diffs)
                sum_x = sum(recent_indices)
                sum_y = sum(recent_diffs)
                sum_xy = sum(x * y for x, y in zip(recent_indices, recent_diffs))
                sum_x2 = sum(x * x for x in recent_indices)
                slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x) if (n * sum_x2 - sum_x * sum_x) != 0 else 0
                config['funding_rate_stats']['recent_trend'] = slope

def calculate_next_common_settlement_time(okx_next_time, bp_next_time, okx_period_hours, bp_period_hours):
    """
    计算下一个共同的结算时间点
    选择最长的周期作为基准，确保两个交易所都在结算时刻
    例如：OKX是8h结算，BP是1h结算，则选择8h的结算时间点
    """
    if not okx_next_time or not bp_next_time:
        return None
    
    current_time_ms = int(time.time() * 1000)
    okx_period_ms = int((okx_period_hours or 8.0) * 3600 * 1000)
    bp_period_ms = int((bp_period_hours or 1.0) * 3600 * 1000)
    
    # 选择最长的周期作为基准（例如：8h > 1h，选择8h）
    max_period_ms = max(okx_period_ms, bp_period_ms)
    max_period_hours = max(okx_period_hours or 8.0, bp_period_hours or 1.0)
    
    # 如果最长周期是OKX的，使用OKX的结算时间
    if max_period_ms == okx_period_ms:
        # 检查BP是否也会在这个时间点结算
        # 计算从当前时间到OKX结算时间，BP会结算几次
        bp_cycles = int((okx_next_time - current_time_ms) / bp_period_ms)
        bp_aligned_time = current_time_ms + bp_cycles * bp_period_ms
        
        # 如果BP对齐时间与OKX结算时间接近（允许5分钟误差），返回OKX结算时间
        tolerance_ms = 5 * 60 * 1000  # 5分钟
        if abs(okx_next_time - bp_aligned_time) <= tolerance_ms:
            return okx_next_time
        # 否则，找到下一个OKX结算时间，同时确保BP也会结算
        # 计算下一个OKX结算时间
        next_okx_time = okx_next_time + okx_period_ms
        # 检查BP是否会在该时间点结算
        bp_cycles_next = int((next_okx_time - current_time_ms) / bp_period_ms)
        bp_aligned_time_next = current_time_ms + bp_cycles_next * bp_period_ms
        if abs(next_okx_time - bp_aligned_time_next) <= tolerance_ms:
            return next_okx_time
        # 如果还是不对齐，返回OKX的下一个结算时间（至少OKX会结算）
        return next_okx_time
    else:
        # 最长周期是BP的，使用BP的结算时间
        # 检查OKX是否也会在这个时间点结算
        okx_cycles = int((bp_next_time - current_time_ms) / okx_period_ms)
        okx_aligned_time = current_time_ms + okx_cycles * okx_period_ms
        
        tolerance_ms = 5 * 60 * 1000  # 5分钟
        if abs(bp_next_time - okx_aligned_time) <= tolerance_ms:
            return bp_next_time
        # 否则，找到下一个BP结算时间，同时确保OKX也会结算
        next_bp_time = bp_next_time + bp_period_ms
        okx_cycles_next = int((next_bp_time - current_time_ms) / okx_period_ms)
        okx_aligned_time_next = current_time_ms + okx_cycles_next * okx_period_ms
        if abs(next_bp_time - okx_aligned_time_next) <= tolerance_ms:
            return next_bp_time
        return next_bp_time

def execute_funding_arbitrage(engine_okx, engine_bp, config):
    """
    执行资金费套利逻辑：只在结算时刻执行，计算实际费率差
    """
    try:
        # 获取完整的资金费率信息
        okx_fr_hourly, okx_fr_period, okx_period_hours, okx_ts, okx_next_ts, okx_err = get_funding_rate_full(
            engine_okx, config['okx_symbol'], 'SWAP'
        )
        bp_fr_hourly, bp_fr_period, bp_period_hours, bp_ts, bp_next_ts, bp_err = get_funding_rate_full(
            engine_bp, config['bp_symbol'], 'PERP'
        )
        
        if okx_err or bp_err:
            return False, f"获取资金费率失败: OKX={okx_err}, BP={bp_err}"
        
        if okx_fr_hourly is None or bp_fr_hourly is None:
            return False, "资金费率为空"
        
        # 计算下一个共同结算时间（选择最长周期）
        next_settlement_time = calculate_next_common_settlement_time(
            okx_next_ts, bp_next_ts, okx_period_hours or 8.0, bp_period_hours or 1.0
        )
        
        # 检查是否到了结算时间（只在结算瞬间执行，允许2分钟误差窗口）
        settlement_tolerance_ms = 2 * 60 * 1000  # 2分钟误差窗口
        current_time_ms = int(time.time() * 1000)
        is_settlement_time = False
        
        if next_settlement_time:
            time_until_settlement = next_settlement_time - current_time_ms
            time_until_settlement_sec = time_until_settlement / 1000
            
            # 检查是否在结算时间窗口内（结算时间前后各1分钟）
            if abs(time_until_settlement) <= settlement_tolerance_ms:
                is_settlement_time = True
            elif time_until_settlement > settlement_tolerance_ms:
                # 还没到结算时间，更新历史数据但不执行套利
                update_funding_rate_history(
                    config, okx_fr_hourly, bp_fr_hourly, 
                    okx_fr_period, bp_fr_period,
                    okx_period_hours, bp_period_hours, 
                    current_time_ms, is_settlement=False
                )
                hours = int(time_until_settlement_sec // 3600)
                minutes = int((time_until_settlement_sec % 3600) // 60)
                return False, f"等待结算时间: {hours}时{minutes}分后"
            else:
                # 已经过了结算时间，可能是刚错过，更新历史数据
                update_funding_rate_history(
                    config, okx_fr_hourly, bp_fr_hourly, 
                    okx_fr_period, bp_fr_period,
                    okx_period_hours, bp_period_hours, 
                    current_time_ms, is_settlement=True
                )
                return False, "已过结算时间窗口，等待下一个结算周期"
        
        # 更新历史数据（标记是否为结算时刻）
        update_funding_rate_history(
            config, okx_fr_hourly, bp_fr_hourly, 
            okx_fr_period, bp_fr_period,
            okx_period_hours, bp_period_hours, 
            current_time_ms, is_settlement=is_settlement_time
        )
        
        # 只在结算瞬间执行套利
        if not is_settlement_time:
            return False, "非结算时刻，不执行套利"
        
        # 计算实际费率差（使用周期费率，按最长周期统一计算）
        # 例如：OKX是8h结算，BP是1h结算，选择8h作为基准周期
        max_period = max(okx_period_hours or 8.0, bp_period_hours or 1.0)
        
        # 获取周期费率（如果API返回的是周期费率，直接使用；否则从小时费率计算）
        okx_actual_rate = okx_fr_period if okx_fr_period is not None else (okx_fr_hourly * (okx_period_hours or 8.0))
        bp_actual_rate = bp_fr_period if bp_fr_period is not None else (bp_fr_hourly * (bp_period_hours or 1.0))
        
        # 将两个费率都转换为最长周期的费率（这样可以直接比较）
        # 例如：如果最长周期是8h，OKX本身就是8h，BP是1h，需要将BP的1h费率转换为8h费率
        okx_rate_for_max_period = okx_actual_rate * (max_period / (okx_period_hours or 8.0))
        bp_rate_for_max_period = bp_actual_rate * (max_period / (bp_period_hours or 1.0))
        
        # 实际费率差 = 在最长周期内，两个交易所实际产生的费率差异
        actual_funding_diff = okx_rate_for_max_period - bp_rate_for_max_period
        
        threshold = config.get('funding_rate_diff_threshold', 0.0001)
        # 阈值也需要按最长周期调整
        threshold_for_period = threshold * max_period
        arbitrage_amount = config.get('funding_arbitrage_amount', 100.0)
        
        # 判断套利机会
        if abs(actual_funding_diff) < threshold_for_period:
            return False, f"实际费率差异不足: {actual_funding_diff*100:.4f}% (阈值: {threshold_for_period*100:.4f}%)"
        
        # 执行套利：在资金费率高的交易所做空，在资金费率低的交易所做多
        if actual_funding_diff > threshold_for_period:
            # OKX实际费率更高，在OKX做空，在BP做多
            oid_okx, err_okx = engine_okx.place_incremental_orders(arbitrage_amount, config['okx_symbol'], 'sell', soft=False)
            oid_bp, err_bp = engine_bp.place_incremental_orders(arbitrage_amount, config['bp_symbol'], 'buy', soft=False)
            if err_okx or err_bp:
                return False, f"资金费套利下单失败: OKX={err_okx}, BP={err_bp}"
            
            # 记录套利操作
            if 'funding_arbitrage_log' not in config:
                config['funding_arbitrage_log'] = []
            config['funding_arbitrage_log'].append({
                'timestamp': current_time_ms,
                'direction': 'okx_sell_bp_buy',
                'okx_rate': okx_actual_rate,
                'bp_rate': bp_actual_rate,
                'actual_diff': actual_funding_diff,
                'amount': arbitrage_amount
            })
            # 只保留最近50条记录
            if len(config['funding_arbitrage_log']) > 50:
                config['funding_arbitrage_log'] = config['funding_arbitrage_log'][-50:]
            
            print(f"{BeijingTime()} ✅ 资金费套利 | OKX实际费率: {okx_actual_rate*100:.4f}% > BP实际费率: {bp_actual_rate*100:.4f}% | 实际差异: {actual_funding_diff*100:.4f}%")
        elif actual_funding_diff < -threshold_for_period:
            # BP实际费率更高，在BP做空，在OKX做多
            oid_okx, err_okx = engine_okx.place_incremental_orders(arbitrage_amount, config['okx_symbol'], 'buy', soft=False)
            oid_bp, err_bp = engine_bp.place_incremental_orders(arbitrage_amount, config['bp_symbol'], 'sell', soft=False)
            if err_okx or err_bp:
                return False, f"资金费套利下单失败: OKX={err_okx}, BP={err_bp}"
            
            # 记录套利操作
            if 'funding_arbitrage_log' not in config:
                config['funding_arbitrage_log'] = []
            config['funding_arbitrage_log'].append({
                'timestamp': current_time_ms,
                'direction': 'bp_sell_okx_buy',
                'okx_rate': okx_actual_rate,
                'bp_rate': bp_actual_rate,
                'actual_diff': actual_funding_diff,
                'amount': arbitrage_amount
            })
            # 只保留最近50条记录
            if len(config['funding_arbitrage_log']) > 50:
                config['funding_arbitrage_log'] = config['funding_arbitrage_log'][-50:]
            
            print(f"{BeijingTime()} ✅ 资金费套利 | BP实际费率: {bp_actual_rate*100:.4f}% > OKX实际费率: {okx_actual_rate*100:.4f}% | 实际差异: {abs(actual_funding_diff)*100:.4f}%")
        
        return True, "资金费套利执行完成"
    
    except Exception as e:
        return False, f"资金费套利执行失败: {str(e)}"

def initialize_positions(engine_okx, engine_bp, config):
    """初始化仓位"""
    try:
        leverage_okx = config.get('leverage_okx', 1.0)
        leverage_bp = config.get('leverage_bp', 1.0)
        balance_okx = engine_okx.cex_driver.fetch_balance()
        balance_bp = engine_bp.cex_driver.fetch_balance()
        
        # 设置初始仓位
        amount_okx = balance_okx * leverage_okx * 0.5  # 初始50%仓位
        amount_bp = balance_bp * leverage_bp * 0.5
        
        oid_okx, err_okx = engine_okx.place_incremental_orders(amount_okx, config['okx_symbol'], 'buy', soft=False)
        oid_bp, err_bp = engine_bp.place_incremental_orders(amount_bp, config['bp_symbol'], 'buy', soft=False)
        if err_okx or err_bp:
            print(f"初始化下单失败: OKX={err_okx}, BP={err_bp}")
            return False
        
        # 更新配置
        config['base_balance_okx'] = balance_okx
        config['base_balance_bp'] = balance_bp
        config['current_balance_okx'] = balance_okx
        config['current_balance_bp'] = balance_bp
        config['add_times'] = 0
        config['reduce_times'] = 0
        config['need_to_init'] = False
        
        # 设置初始价格比基准
        xaut_price = engine_okx.cex_driver.get_price_now(config['okx_symbol'])
        paxg_price = engine_bp.cex_driver.get_price_now(config['bp_symbol'])
        if xaut_price and paxg_price:
            config['price_ratio_base'] = calculate_price_ratio(xaut_price, paxg_price)
        
        save_strategy_config(config)
        print(f"{BeijingTime()} ✅ 初始化完成 | OKX余额: {balance_okx:.2f} | BP余额: {balance_bp:.2f} | 价格比基准: {config.get('price_ratio_base', 0):.6f}")
        return True
    except Exception as e:
        print(f"{BeijingTime()} ❌ 初始化失败: {e}")
        return False

if __name__ == '__main__':
    # 自动用当前文件名（去除后缀）作为默认策略名
    default_strategy = os.path.splitext(os.path.basename(__file__))[0].upper()
    
    # 加载配置
    config = load_strategy_config()
    last_config_mtime = os.path.getmtime(config_file) if os.path.exists(config_file) else 0
    
    # 初始化交易所和引擎
    try:
        exch_okx, engine_okx = pick_exchange('okx', config['okx_account_id'], strategy=default_strategy, strategy_detail="COMMON")
        exch_bp, engine_bp = pick_exchange('bp', config['bp_account_id'], strategy=default_strategy, strategy_detail="COMMON")
        print(f"✓ 初始化 OKX-{config['okx_account_id']} 和 BP-{config['bp_account_id']} 成功")
    except Exception as e:
        print(f"✗ 初始化交易所失败: {e}")
        sys.exit(1)
    
    # 初始化仓位（如果需要）
    if config.get('need_to_init', True):
        if not initialize_positions(engine_okx, engine_bp, config):
            print("❌ 初始化失败，退出")
            sys.exit(1)
    
    # 重置基准余额（如果需要）
    if config.get('need_to_reset_base_balance', False):
        config['base_balance_okx'] = engine_okx.cex_driver.fetch_balance()
        config['base_balance_bp'] = engine_bp.cex_driver.fetch_balance()
        config['need_to_reset_base_balance'] = False
        save_strategy_config(config)
        print(f"✓ 重置基准余额完成")
    
    print(f"🚀 启动黄金对冲策略")
    print(f"   OKX追踪: {config['okx_symbol'].upper()}")
    print(f"   BP追踪: {config['bp_symbol'].upper()}")
    print(f"   价格比基准: {config.get('price_ratio_base', 0):.6f}")
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
            
            # 检查是否需要初始化
            if config.get('need_to_init', False):
                if not initialize_positions(engine_okx, engine_bp, config):
                    print("❌ 初始化失败")
                continue
            
            # 检查是否需要重置基准余额
            if config.get('need_to_reset_base_balance', False):
                config['base_balance_okx'] = engine_okx.cex_driver.fetch_balance()
                config['base_balance_bp'] = engine_bp.cex_driver.fetch_balance()
                config['need_to_reset_base_balance'] = False
                save_strategy_config(config)
            
            # 执行资金费套利（优先级更高，只在结算时刻执行）
            funding_success, funding_msg = execute_funding_arbitrage(engine_okx, engine_bp, config)
            if funding_success:
                save_strategy_config(config)
                time.sleep(5)  # 套利后等待
            # 即使不执行套利，也要保存更新的历史数据
            elif "等待结算时间" not in funding_msg:
                # 如果不是等待结算时间，说明可能是数据更新，保存配置
                save_strategy_config(config)
            
            # 执行马丁网格
            grid_success, grid_msg = execute_martin_grid(engine_okx, engine_bp, config)
            if grid_success:
                save_strategy_config(config)
                time.sleep(5)  # 交易后等待
            
            # 更新当前余额
            config['current_balance_okx'] = engine_okx.cex_driver.fetch_balance()
            config['current_balance_bp'] = engine_bp.cex_driver.fetch_balance()
            
            # 显示状态
            elapsed_seconds = int(time.time() - start_time)
            days, remainder = divmod(elapsed_seconds, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, _ = divmod(remainder, 60)
            
            xaut_price = engine_okx.cex_driver.get_price_now(config['okx_symbol'])
            paxg_price = engine_bp.cex_driver.get_price_now(config['bp_symbol'])
            price_ratio = calculate_price_ratio(xautt_price, paxg_price) if xautt_price and paxg_price else 0
            ratio_deviation = ((price_ratio - config.get('price_ratio_base', 1.0)) / config.get('price_ratio_base', 1.0) * 100) if price_ratio and config.get('price_ratio_base', 0) > 0 else 0
            
            status_msg = (
                f"{BeijingTime()} 💰 OKX:{config['current_balance_okx']:.2f} | "
                f"BP:{config['current_balance_bp']:.2f} | "
                f"杠杆:{config['leverage_okx']:.2f} | "
                f"价格比:{price_ratio:.6f}({ratio_deviation:+.2f}%) | "
                f"运行:{days}天{hours:02d}时{minutes:02d}分"
            )
            print(f"\r{status_msg}", end='')
            
            # 等待下一轮检查
            check_interval = config.get('check_interval', 30)
            time.sleep(check_interval)
    
    except KeyboardInterrupt:
        print(f"\n{BeijingTime()} ⏹️ 手动停止策略")
        save_strategy_config(config)
        print("✓ 策略状态已保存")
        sys.exit(0)
    except Exception as e:
        print(f"\n{BeijingTime()} ❌ 策略运行异常: {e}")
        import traceback
        traceback.print_exc()
        save_strategy_config(config)
        print("✓ 异常状态已保存")
        sys.exit(1)

