# -*- coding: utf-8 -*-
# tests/test_execution_engine_simple.py
# 简化版ExecutionEngine测试，快速验证place_incremental_orders功能

import os
import sys
import time
from pathlib import Path

# Ensure project root (which contains the `ctos/` package directory) is on sys.path
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


from ctos.core.runtime.ExecutionEngine import pick_exchange, ExecutionEngine
from ctos.drivers.okx.util import rate_price2order, align_decimal_places, cal_amount, json


def quick_test(exchange_type, coin, amount=10):
    """快速测试单个币种的下单功能"""
    print(f"\n{'='*50}")
    print(f"快速测试 {exchange_type.upper()} - {coin.upper()} - {amount} USDT")
    print(f"{'='*50}")
    
    try:
        # 创建引擎
        engine = ExecutionEngine(account=1, exchange_type=exchange_type)
        print(f"✓ 引擎创建成功")
        
        # 获取价格
        if exchange_type == 'okx':
            symbol = f"{coin.upper()}-USDT-SWAP"
        else:
            symbol = f"{coin.upper()}_USDC_PERP"
        
        price = engine.cex_driver.get_price_now(symbol)
        print(f"✓ 当前价格: {price}")
        
        # 测试exchange_limits
        limits, error = engine.cex_driver.exchange_limits(symbol=symbol)
        if error:
            print(f"❌ 获取限制信息失败: {error}")
            return False
        else:
            print(f"✓ 限制信息: 价格精度={limits['price_precision']}, 数量精度={limits['size_precision']}, 最小下单={limits['min_order_size'] * limits['contract_value']}")
        
        # 执行下单
        print(f"开始下单...")
        start_time = time.time()
        soft_orders = engine.place_incremental_orders(
            usdt_amount=amount,
            coin=coin,
            direction='buy',  # 改为买入
            soft=True  # 使用限价单
        )
        end_time = time.time()
        
        print(f"✓ 下单完成，耗时: {end_time - start_time:.2f}秒")
        if soft_orders:
            print(f"✓ 软订单ID: {soft_orders}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main_test():
    """主测试函数"""
    print("ExecutionEngine 快速测试")
    print("测试币种: ETH, PENGU, BTC, WLD")
    print("测试金额: 每个10 USDT")
    print("测试交易所: OKX 和 Backpack")
    
    # 测试币种和金额
    test_cases = [
        ('okx', 'eth', 10),
        ('okx', 'pengu', 10),
        ('okx', 'btc', 10),
        ('okx', 'wld', 10),
        ('backpack', 'eth', 10),
        ('backpack', 'pengu', 10),
        ('backpack', 'btc', 10),
        ('backpack', 'wld', 10),
    ]
    
    success_count = 0
    total_count = len(test_cases)
    
    for exchange_type, coin, amount in test_cases:
        if quick_test(exchange_type, coin, amount):
            success_count += 1
        time.sleep(2)  # 避免请求过于频繁
    
    print(f"\n{'='*50}")
    print(f"测试结果: {success_count}/{total_count} 成功")
    print(f"{'='*50}")

def main1_test():
    cex, engine = pick_exchange('bp', 1)
    bp = engine.cex_driver
    pos, _ = bp.get_position()

    now_position = {x['symbol']:float(x['netCost']) for x in pos}
    print(json.dumps(now_position, indent=4))

    all_coins, _  = bp.symbols()

    all_coins = [x[:x.find('_')].lower() for x in all_coins if x[:x.find('_')].lower() in rate_price2order.keys()] 
    print(all_coins, len(all_coins))


    # while True:
    #     time.sleep(3)

    with open(str(_PROJECT_ROOT) + '/apps/strategies/hedge/good_group_bp.txt', 'r', encoding='utf8') as f:
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
    leverage_times = 2
    init_operate_position = start_money * leverage_times
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

if __name__ == '__main__':
    main1_test()
