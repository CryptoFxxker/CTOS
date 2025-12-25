# -*- coding: utf-8 -*-
# 资金费率套利策略
# 在资金费率收取时进行套利操作

import os
import sys
import time
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import os
import multiprocessing
cpu_count = multiprocessing.cpu_count()
def add_project_paths(project_name="ctos"):
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
_PROJECT_ROOT = add_project_paths()
print('_PROJECT_ROOT: ', _PROJECT_ROOT, 'CURRENT_DIR: ', os.path.dirname(os.path.abspath(__file__)))

from ctos.core.runtime.ExecutionEngine import pick_exchange
from ctos.drivers.okx.util import BeijingTime


def get_current_time():
    """获取当前北京时间"""
    return datetime.now()


def wait_until_time(target_minute, target_second=0):
    """等待到指定的分钟和秒"""
    while True:
        now = get_current_time()
        current_minute = now.minute
        current_second = now.second
        current_microsecond = now.microsecond
        
        # 如果已经过了目标时间，等待下一小时
        if current_minute > target_minute or (current_minute == target_minute and current_second >= target_second):
            # 计算到下一个目标时间的秒数
            next_hour = now.replace(minute=target_minute, second=target_second, microsecond=0) + timedelta(hours=1)
            wait_seconds = (next_hour - now).total_seconds()
            if wait_seconds > 0:
                time.sleep(min(wait_seconds, 60))  # 最多等待60秒，然后重新检查
            continue
        
        # 如果还没到目标时间，计算等待时间
        target_time = now.replace(minute=target_minute, second=target_second, microsecond=0)
        wait_seconds = (target_time - now).total_seconds()
        
        if wait_seconds > 0:
            # 如果等待时间较长，分段等待以便及时响应
            if wait_seconds > 10:
                time.sleep(wait_seconds - 5)  # 先等待大部分时间
            else:
                time.sleep(wait_seconds)  # 剩余时间较短，直接等待
        
        # 精确等待到目标秒
        now = get_current_time()
        if now.minute == target_minute and now.second >= target_second:
            break


def check_funding_rate(engine, symbol, current_hour_timestamp_ms, debug=False):
    """
    检查币种的资金费率是否符合套利条件
    :param engine: 交易引擎
    :param symbol: 币种符号
    :param current_hour_timestamp_ms: 当前小时的开始时间戳（毫秒）
    :param debug: 是否输出调试信息
    :return: (is_qualified, fee_info, direction) - (是否符合条件, 费率信息, 操作方向)
    """
    try:
        # 获取标准化数据（包含raw字段）
        fee_info, error = engine.cex_driver.fees(symbol, keep_origin=False)
        if error or not fee_info:
            if debug:
                print(f"  [DEBUG] {symbol}: 获取费率失败 error={error}, fee_info={fee_info}")
            return False, None, None
        
        funding_rate_period = fee_info.get('fundingRate_period', 0)
        period_hours = fee_info.get('period_hours', 8.0)
        funding_time_ms = fee_info.get('fundingTime', 0)
        
        if debug:
            print(f"  [DEBUG] {symbol}: fee_info keys = {list(fee_info.keys())}")
            print(f"  [DEBUG] {symbol}: funding_rate_period = {funding_rate_period}")
            print(f"  [DEBUG] {symbol}: period_hours = {period_hours}")
            print(f"  [DEBUG] {symbol}: funding_time_ms = {funding_time_ms}")
        
        # 从raw数据中提取nextFundingTime
        next_funding_time_ms = None
        try:
            raw_data = fee_info.get('raw', {})
            if debug:
                print(f"  [DEBUG] {symbol}: raw_data keys = {list(raw_data.keys()) if isinstance(raw_data, dict) else 'not dict'}")
            if isinstance(raw_data, dict):
                data_list = raw_data.get('data', [])
                if debug:
                    print(f"  [DEBUG] {symbol}: data_list length = {len(data_list) if isinstance(data_list, list) else 'not list'}")
                if isinstance(data_list, list) and len(data_list) > 0:
                    first_item = data_list[0]
                    if debug:
                        print(f"  [DEBUG] {symbol}: first_item keys = {list(first_item.keys()) if isinstance(first_item, dict) else 'not dict'}")
                        print(f"  [DEBUG] {symbol}: first_item = {first_item}")
                    next_funding_time_str = first_item.get('nextFundingTime', '')
                    if debug:
                        print(f"  [DEBUG] {symbol}: nextFundingTime (str) = '{next_funding_time_str}'")
                    if next_funding_time_str:
                        next_funding_time_ms = int(next_funding_time_str)
                        if debug:
                            print(f"  [DEBUG] {symbol}: nextFundingTime (ms) = {next_funding_time_ms}")
        except Exception as e:
            if debug:
                print(f"  [DEBUG] {symbol}: 提取nextFundingTime异常: {e}")
                import traceback
                traceback.print_exc()
        
        # 如果无法从raw获取nextFundingTime，使用fundingTime + period_hours计算
        if not next_funding_time_ms and funding_time_ms > 0:
            next_funding_time_ms = int(funding_time_ms + period_hours * 3600 * 1000)
            if debug:
                print(f"  [DEBUG] {symbol}: 使用fundingTime计算nextFundingTime: {funding_time_ms} + {period_hours*3600*1000} = {next_funding_time_ms}")
        
        # 计算下一个整点的时间戳
        next_hour_timestamp_ms = current_hour_timestamp_ms + 3600000  # 下一小时的时间戳
        
        # 按照周期判断下一个整点是否在结算周期节点上
        from datetime import datetime
        next_hour_dt = datetime.fromtimestamp(next_hour_timestamp_ms / 1000)
        next_hour_hour = next_hour_dt.hour  # 下一个整点的小时数（0-23）
        
        # 判断下一个整点是否在结算周期节点上
        is_settlement_hour = False
        
        if period_hours == 1.0:
            # 每1小时周期：每个整点都是结算时间
            is_settlement_hour = True
        elif period_hours == 8.0:
            # 每8小时周期：只有00:00, 08:00, 16:00是结算时间
            is_settlement_hour = (next_hour_hour % 8 == 0)
        else:
            # 其他周期：根据周期计算
            # 例如4小时周期：00:00, 04:00, 08:00, 12:00, 16:00, 20:00
            is_settlement_hour = (next_hour_hour % int(period_hours) == 0)
        
        if debug:
            current_hour_str = datetime.fromtimestamp(current_hour_timestamp_ms/1000).strftime('%Y-%m-%d %H:%M:%S')
            next_hour_str = datetime.fromtimestamp(next_hour_timestamp_ms/1000).strftime('%Y-%m-%d %H:%M:%S')
            print(f"  [DEBUG] {symbol}: current_hour={current_hour_str}, next_hour={next_hour_str} (小时数={next_hour_hour})")
            print(f"  [DEBUG] {symbol}: period_hours={period_hours}, is_settlement_hour={is_settlement_hour}")
        
        if not is_settlement_hour:
            if debug:
                print(f"  [DEBUG] {symbol}: ❌ 下一个整点不在结算周期节点上!")
            return False, None, None
        
        # 检查资金费率绝对值是否大于千分之一
        abs_funding_rate = abs(funding_rate_period)
        if debug:
            print(f"  [DEBUG] {symbol}: funding_rate_period={funding_rate_period}, abs={abs_funding_rate}, threshold=0.001")
        
        if abs_funding_rate <= 0.0015:
            if debug:
                print(f"  [DEBUG] {symbol}: 资金费率绝对值 {abs_funding_rate} <= 0.001，不符合条件")
            return False, None, None
        
        # 确定操作方向
        # fundingRate_period > 0: 做多支付资金费，做空收取资金费 -> 应该做空（在59分58秒做空，0分1秒平空）
        # fundingRate_period < 0: 做多收取资金费，做空支付资金费 -> 应该做多（在59分58秒做多，0分1秒平多）
        direction = 'short' if funding_rate_period > 0 else 'long'
        
        if debug:
            print(f"  [DEBUG] {symbol}: ✓ 符合条件! 费率={funding_rate_period*100:.4f}%, 方向={direction}")
        
        return True, fee_info, direction
        
    except Exception as e:
        print(f"✗ 检查 {symbol} 资金费率失败: {e}")
        import traceback
        traceback.print_exc()
        return False, None, None


def scan_qualified_coins(engine, usdt_amount=500):
    """
    扫描所有符合条件的币种
    :param engine: 交易引擎
    :param usdt_amount: 每个币种操作的USDT金额，默认500
    :return: list of (symbol, direction, size, price) - 符合条件的币种列表
    """
    qualified_coins = []
    
    try:
        # 获取所有交易对
        symbols, error = engine.cex_driver.symbols()
        if error or not symbols:
            print(f"✗ 获取交易对列表失败: {error}")
            return []
        print(f"{BeijingTime()} 🔍 开始扫描 {len(symbols)} 个币种的资金费率...")
        
        # 计算当前小时的开始时间戳（毫秒）
        now = get_current_time()
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        current_hour_timestamp_ms = int(current_hour_start.timestamp() * 1000)
        
        # 需要详细调试的币种列表
        debug_symbols = []# ['pippin', 'api3', 'ksm', 'jellyjelly', 'night']
        debug_symbols_upper = [s.upper() for s in debug_symbols]
        
        # 扫描所有币种
        debug_count = 0
        for symbol in symbols:
            # 检查是否是需要debug的币种（不区分大小写）
            symbol_base = symbol.split('-')[0].split('_')[0].upper()
            debug = (symbol_base in debug_symbols_upper) 
            is_qualified, fee_info, direction = check_funding_rate(engine, symbol, current_hour_timestamp_ms, debug=debug)
            debug_count += 1
            
            if is_qualified:
                try:
                    # 提取基础币种名称（去掉 -USDT-SWAP 等后缀）
                    coin_base = symbol.split('-')[0].split('_')[0].lower()
                    qualified_coins.append({
                        'symbol': symbol,
                        'coin': coin_base,  # 基础币种名称，用于 place_incremental_orders
                        'direction': direction,
                        'usdt_amount': usdt_amount,
                        'funding_rate': fee_info.get('fundingRate_period', 0),
                        'funding_rate_hourly': fee_info.get('fundingRate_hourly', 0)
                    })
                    print(f"  ✓ {symbol}: 费率={fee_info.get('fundingRate_period', 0)*100:.4f}%, 方向={direction}, 金额={usdt_amount} USDT")
                except Exception as e:
                    print(f"  ✗ {symbol} 处理失败: {e}")
            else:
                # 只输出简要信息，避免刷屏
                if debug_count <= 5:
                    print(f"\r  ✗ {symbol} 不符合条件", end="")
                elif debug_count % 10 == 0:
                    print(f"\r  已扫描 {debug_count}/{len(symbols)} 个币种...", end="")
        print(f"{BeijingTime()} ✓ 扫描完成，找到 {len(qualified_coins)} 个符合条件的币种")
        return qualified_coins
        
    except Exception as e:
        print(f"✗ 扫描币种失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def execute_trade(engine, coin, direction, usdt_amount, operation_type='open'):
    """
    执行交易操作，使用 place_incremental_orders 直接按 USDT 金额下单
    :param engine: 交易引擎
    :param coin: 基础币种名称（如 'btc', 'eth'）
    :param direction: 方向 'long' 或 'short'
    :param usdt_amount: USDT 金额
    :param operation_type: 操作类型 'open' 或 'close'
    :return: (success, order_id, error)
    """
    try:
        # 确定交易方向
        # direction='long' 且 operation_type='open': 做多开仓 -> 买入
        # direction='long' 且 operation_type='close': 做多平仓 -> 卖出
        # direction='short' 且 operation_type='open': 做空开仓 -> 卖出
        # direction='short' 且 operation_type='close': 做空平仓 -> 买入
        if direction == 'long':
            trade_direction = 'buy' if operation_type == 'open' else 'sell'
        else:  # short
            trade_direction = 'sell' if operation_type == 'open' else 'buy'
        
        # 使用 place_incremental_orders 下单
        orders, error = engine.place_incremental_orders(
            usdt_amount=usdt_amount,
            coin=coin,
            direction=trade_direction,
            soft=False  # 资金费率套利使用市价单
        )
        
        if error:
            return False, None, error
        
        # place_incremental_orders 返回订单列表，取第一个订单ID
        order_id = orders[0] if orders else None
        return True, order_id, None
        
    except Exception as e:
        return False, None, str(e)


def execute_trades_concurrent(engine, qualified_coins, operation_type='open'):
    """
    多线程并发执行交易
    :param engine: 交易引擎
    :param qualified_coins: 符合条件的币种列表
    :param operation_type: 操作类型 'open' 或 'close'
    """
    if not qualified_coins:
        return
    
    op_name = '开仓' if operation_type == 'open' else '平仓'
    print(f"{BeijingTime()} 🚀 开始{op_name}操作，共 {len(qualified_coins)} 个币种")
    
    results = []
    
    def trade_worker(coin_info):
        symbol = coin_info['symbol']
        coin = coin_info['coin']
        direction = coin_info['direction']
        usdt_amount = coin_info['usdt_amount']
        
        success, order_id, error = execute_trade(engine, coin, direction, usdt_amount, operation_type)
        return {
            'symbol': symbol,
            'success': success,
            'order_id': order_id,
            'error': error,
            'direction': direction,
            'usdt_amount': usdt_amount
        }
    
    # 使用线程池并发执行
    max_workers = min(len(qualified_coins), cpu_count, 20)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(trade_worker, coin) for coin in qualified_coins]
        for future in as_completed(futures):
            try:
                result = future.result(timeout=10)
                results.append(result)
                if result['success']:
                    print(f"  ✓ {result['symbol']} {op_name}成功: 订单ID={result['order_id']}, 方向={result['direction']}, 金额={result['usdt_amount']} USDT")
                else:
                    print(f"  ✗ {result['symbol']} {op_name}失败: {result['error']}")
            except Exception as e:
                print(f"  ✗ 交易执行异常: {e}")
    
    success_count = sum(1 for r in results if r['success'])
    print(f"{BeijingTime()} ✓ {op_name}完成: 成功 {success_count}/{len(qualified_coins)}")
    
    return results


def main_loop(cex_name='okx', account_id=0, usdt_amount=500):
    """
    主循环
    :param cex_name: 交易所名称
    :param account_id: 账户ID
    :param usdt_amount: 每个币种操作的USDT金额
    """
    # 初始化交易所和引擎
    default_strategy = os.path.splitext(os.path.basename(__file__))[0].upper()
    try:
        exch, engine = pick_exchange(cex_name, account_id, strategy=default_strategy, strategy_detail="COMMON")
        print(f"✓ 初始化 {cex_name}-{account_id} 成功")
    except Exception as e:
        print(f"✗ 初始化 {cex_name}-{account_id} 失败: {e}")
        return
    
    print(f"🚀 启动资金费率套利策略 - {cex_name}-{account_id}")
    print(f"   每个币种操作金额: {usdt_amount} USDT")
    
    current_qualified_coins = []
    last_scan_hour = -1  # 记录上次扫描的小时，避免重复扫描
    
    try:
        while True:
            now = get_current_time()
            current_minute = now.minute
            current_second = now.second
            current_hour = now.hour
            
            # 在55-59分钟之间，检测资金费率（每个小时只检测一次）
            if 55 <= current_minute < 59 and current_hour != last_scan_hour:
                print(f"{BeijingTime()} ⏰ 进入检测窗口 (55-59分钟)")
                last_scan_hour = current_hour
                
                # 扫描符合条件的币种
                qualified_coins = scan_qualified_coins(engine, usdt_amount)
                
                if qualified_coins:
                    coin_names = [coin['symbol'] for coin in qualified_coins]
                    print(f"{BeijingTime()} ✓ 找到 {len(qualified_coins)} 个符合条件的币种: {', '.join(coin_names)}")
                    
                    # 等待到59分0秒进行二次检查
                    wait_until_time(59, 0)
                    
                    # 在59分0秒重新检查资金费率
                    now = get_current_time()
                    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
                    current_hour_timestamp_ms = int(current_hour_start.timestamp() * 1000)
                    
                    print(f"{BeijingTime()} 🔍 二次检查资金费率...")
                    still_qualified = []
                    for coin_info in qualified_coins:
                        is_qualified, _, _ = check_funding_rate(engine, coin_info['symbol'], current_hour_timestamp_ms, debug=False)
                        if is_qualified:
                            still_qualified.append(coin_info)
                    
                    if not still_qualified:
                        print(f"{BeijingTime()} ⚠️ 二次检查后没有符合条件的币种，跳过本次操作")
                        wait_until_time(0, 0)
                        time.sleep(60)
                        continue
                    
                    print(f"{BeijingTime()} ✓ 二次检查完成: {len(still_qualified)}/{len(qualified_coins)} 个币种仍然符合条件")
                    
                    # 等待到59分30秒
                    wait_until_time(59, 30)
                    
                    # 在59分30秒确认币种列表（使用 place_incremental_orders 不需要更新价格和数量）
                    print(f"{BeijingTime()} 📊 确认币种列表，共 {len(still_qualified)} 个币种")
                    current_qualified_coins = still_qualified
                    
                    # 等待到59分58秒
                    wait_until_time(59, 58)
                    
                    # 在59分58秒执行开仓操作
                    if current_qualified_coins:
                        # 记录开仓时的秒数
                        open_time = get_current_time()
                        open_second = open_time.second
                        print(f"{BeijingTime()} 🚀 开始开仓操作（当前秒数: {open_second}）...")
                        execute_trades_concurrent(engine, current_qualified_coins, operation_type='open')
                        
                        # 开仓后立即检查并平仓
                        print(f"{BeijingTime()} 🔄 开仓完成，等待进入下一个小时后立即平仓...")
                        while True:
                            now = get_current_time()
                            current_second = now.second
                            current_minute = now.minute
                            
                            # 如果已经进入下一个小时（分钟数为0，且秒数小于开仓时的秒数）
                            # 或者分钟数小于59（说明已经过了59分，进入下一个小时）
                            if current_minute == 0 or (current_minute < 59 and current_second < open_second):
                                print(f"{BeijingTime()} ✓ 检测到已进入下一个小时，立即平仓...")
                                execute_trades_concurrent(engine, current_qualified_coins, operation_type='close')
                                current_qualified_coins = []
                                break
                            
                            # 短暂等待后继续检查
                            time.sleep(0.01)
                else:
                    print(f"{BeijingTime()} ℹ️ 未找到符合条件的币种，等待下一个检测窗口...")
                    # 如果没找到符合条件的币种，等待到下一个小时
                    wait_until_time(0, 0)
                    time.sleep(60)  # 等待1分钟，确保进入下一个小时
                
            elif current_minute == 0 and current_second <= 5:
                # 在0分0-5秒之间，如果有未平仓的，尝试平仓
                if current_qualified_coins:
                    print(f"{BeijingTime()} ⚠️ 检测到未平仓币种，尝试平仓...")
                    try:
                        execute_trades_concurrent(engine, current_qualified_coins, operation_type='close')
                        current_qualified_coins = []
                    except Exception as e:
                        print(f"✗ 平仓失败: {e}")
                
            else:
                # 不在检测窗口，等待一段时间后继续检查
                time.sleep(10)
                
    except KeyboardInterrupt:
        print(f"\n{BeijingTime()} ⏹️ 手动停止策略")
        # 如果有未平仓的，尝试平仓
        if current_qualified_coins:
            print(f"{BeijingTime()} ⚠️ 检测到未平仓币种，尝试平仓...")
            try:
                execute_trades_concurrent(engine, current_qualified_coins, operation_type='close')
            except Exception as e:
                print(f"✗ 平仓失败: {e}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{BeijingTime()} ❌ 策略运行异常: {e}")
        import traceback
        traceback.print_exc()
        # 如果有未平仓的，尝试平仓
        if current_qualified_coins:
            print(f"{BeijingTime()} ⚠️ 检测到未平仓币种，尝试平仓...")
            try:
                execute_trades_concurrent(engine, current_qualified_coins, operation_type='close')
            except Exception as e2:
                print(f"✗ 平仓失败: {e2}")
        sys.exit(1)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='资金费率套利策略')
    parser.add_argument('--cex', type=str, default='okx', help='交易所名称 (默认: bp)')
    parser.add_argument('--account', type=int, default=0, help='账户ID (默认: 0)')
    parser.add_argument('--amount', type=float, default=500, help='每个币种操作的USDT金额 (默认: 500)')
    
    args = parser.parse_args()
    
    main_loop(cex_name=args.cex, account_id=args.account, usdt_amount=args.amount)

