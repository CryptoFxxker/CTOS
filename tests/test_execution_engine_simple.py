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


from ctos.core.runtime.ExecutionEngine import ExecutionEngine


def quick_test(exchange_type, coin, amount=10):
    """快速测试单个币种的下单功能"""
    print(f"\n{'='*50}")
    print(f"快速测试 {exchange_type.upper()} - {coin.upper()} - {amount} USDT")
    print(f"{'='*50}")
    
    try:
        # 创建引擎
        engine = ExecutionEngine(account=0, exchange_type=exchange_type)
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
            direction='sell',
            price=price*1.01,
            soft=True 
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


def main():
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


if __name__ == '__main__':
    main()
