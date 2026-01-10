#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
本用例用来检验 TradingSyscalls 的基本功能。
并测试运行环境是否正确

测试 API 如下：
#### 行情相关
- **`get_price_now(symbol)`** - 获取最新成交价
- **`get_orderbook(symbol, level)`** - 获取订单簿（bids/asks）
- **`get_klines(symbol, timeframe, limit, start_time, end_time)`** - 获取K线数据
- **`fees(symbol, limit, offset)`** - 获取资金费率

#### 交易相关
- **`place_order(symbol, side, order_type, size, price=None, **kwargs)`** - 下单
- **`revoke_order(order_id, symbol)`** - 撤单
- **`amend_order(order_id, symbol, ...)`** - 改单（查单→撤单→下单）                 - 本示例中未测试该功能
- **`get_open_orders(symbol=None, instType='SWAP')`** - 获取未完成订单
- **`get_order_status(order_id, keep_origin=False)`** - 查询订单状态
- **`cancel_all(symbol)`** - 撤销指定交易对全部订单

#### 账户/仓位
- **`fetch_balance(currency)`** - 获取余额（支持多币种）
- **`get_position(symbol=None, keep_origin=False)`** - 获取仓位信息
- **`close_all_positions(symbol=None)`** - 平仓所有仓位                             - 本示例中用实仓且没有仓位，暂不测试该功能

"""

import sys
import os
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from tkinter import N
import argparse
import time
import requests


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


from ctos.drivers.simulateokx.util import align_decimal_places, round_dynamic, round_to_two_digits, rate_price2order, cal_amount, BeijingTime
from ctos.core.runtime.ExecutionEngine import pick_exchange


def main():
    # 由于 okx 的 api 位于墙外，需要配置科学上网代理
    print("API example strategy would run here and call TradingSyscalls.")
    
    # # 读取 Args 
    argparser = argparse.ArgumentParser(description="API Example Strategy")
    argparser.add_argument("--mode", type=str, default="simulate", help="实仓/模拟")
    args = argparser.parse_args()
    mode = args.mode
    
    # 支持多交易所多账户 - 此处仅演示单账户
    cex = 'okx'
    account = 1 # 默认读取 account.yaml 中第 0 个账户配置 第 1 个账户为虚拟盘api
    if mode == "real":
        account = 0 # 默认读取 account.yaml 中第 0 个账户配置 第 0 个账户为实盘api
        
    # 初始化交易引擎
    # 命名策略名称
    example_strategy = "api_example"
    example_strategy_detail = "this is an example strategy to test TradingSyscalls API"

    
    try :
        # 使用 pick_exchange 方法初始化交易所和引擎 cex_driver 类型为 OkxDriver 相关 api 接口见 ctos\drivers\okx\driver.py
        exch, engine = pick_exchange(cex, account, strategy=example_strategy, strategy_detail=example_strategy_detail)
        
        # -------------------------行情相关 API 测试-------------------------
        # 获取 关注交易对 的最新价格
        start_time = time.time()
        btc_price_now = engine.cex_driver.get_price_now('BTC-USDT-SWAP') # 可以传入不同的 symbol
        eth_price_now = engine.cex_driver.get_price_now('ETH-USDT-SWAP')
        end_time = time.time()
        print(f"Take time {end_time - start_time} seconds. BTC price now: {btc_price_now}, ETH price now: {eth_price_now}")
        print("-----")
        
       # 获取 关注交易对 的订单簿
        start_time = time.time()
        btc_orderbook = engine.cex_driver.get_orderbook('BTC-USDT-SWAP', level=50) # level 可选 1, 5, 20
        end_time = time.time()
        print(f"Take time {end_time - start_time} seconds. BTC orderbook (top 5):")
        print(btc_orderbook)
        print("-----")
        
        # 获取 关注交易对 的 K 线数据
        start_time = time.time()
        btc_klines = engine.cex_driver.get_klines('BTC-USDT-SWAP', timeframe='1m', limit=10)
        end_time = time.time()
        print(f"Take time {end_time - start_time} seconds. BTC 1m klines (last 10):")
        print(btc_klines)
        print("-----")
        
        # 获取 关注交易对 的资金费率
        start_time = time.time()
        btc_funding_rate = engine.cex_driver.fees('BTC-USDT-SWAP', instType='SWAP', keep_origin=False)
        eth_funding_rate = engine.cex_driver.fees('ETH-USDT-SWAP', instType='SWAP', keep_origin=False)
        end_time = time.time()
        print(f"Take time {end_time - start_time} seconds.\n BTC funding rate: {btc_funding_rate}\n ETH funding rate: {eth_funding_rate}")
        print("-----")
        
        # -------------------------账户仓位相关 API 测试-------------------------
        # 获取 关注币种 的余额
        start_time = time.time()
        usdt_balance = engine.cex_driver.fetch_balance('USDT')
        btc_balance = engine.cex_driver.fetch_balance('BTC')
        end_time = time.time()
        print(f"Take time {end_time - start_time} seconds. USDT balance:{usdt_balance}, BTC balance:{btc_balance}")
        print("-----")
        
        # 获取 关注交易对/全部 的仓位信息
        start_time = time.time()
        all_positions = engine.cex_driver.get_position()
        end_time = time.time()
        print(f"Take time {end_time - start_time} seconds. ALL position:{all_positions}")
        print("-----")

        # 暂不测试平仓功能
        # start_time = time.time()
        # # engine.cex_driver.close_all_positions(symbol='BTC-USDT-SWAP')
        # end_time = time.time()
        # print(f"Take time {end_time - start_time} seconds. close all positions skipped.")
        # print("-----")
        
        # -------------------------交易相关 API 测试-------------------------
        # 下单 - 官方 api 接口下单以张为单位 下一个当前价格 0.5 倍的多头限价单
        start_time = time.time()
        # 调用逻辑： ctos\drivers\okx\driver.py 中的 place_order 方法 -> ctos\drivers\okx\okex.py 中的 place_order 方法
        order_id, err = engine.cex_driver.place_order(
            symbol='BTC-USDT-SWAP',                     # 交易对
            side='buy',                                 # 买入
            order_type='limit',                         # 限价单
            size=0.03,                                  # 单位：张
            price=round_dynamic(btc_price_now * 0.5),   # 价格
            posSide='long'                              # 持仓方向：多头
        )
        end_time = time.time()
        print(f"Take time {end_time - start_time} seconds. Placed order id: {order_id}, err: {err}")
        print("-----")
        
        # 查询订单状态
        start_time = time.time()
        order_status = engine.cex_driver.get_order_status(order_id)
        end_time = time.time()
        print(f"Take time {end_time - start_time} seconds. Order status: {order_status}")
        print("-----")
        
        # 获取未完成订单
        start_time = time.time()
        open_orders = engine.cex_driver.get_open_orders(symbol='BTC-USDT-SWAP')
        end_time = time.time()
        print(f"Take time {end_time - start_time} seconds. Open orders:")
        print(open_orders)
        print("-----")
        
        # 撤单
        start_time = time.time()
        revoke_err = engine.cex_driver.revoke_order(order_id, symbol='BTC-USDT-SWAP')
        end_time = time.time()
        print(f"Take time {end_time - start_time} seconds. Revoke order err: {revoke_err}")
        print("-----")
        
        # 撤掉全部订单 - 此处演示下单两个单子(一个0.5倍多单，一个1.5倍空单)后撤单
        order_id1, err1 = engine.cex_driver.place_order(
            symbol='BTC-USDT-SWAP',                     # 交易对
            side='buy',                                 # 买入
            order_type='limit',                         # 限价单
            size=0.02,                                  # 单位：张
            price=round_dynamic(btc_price_now * 0.5),   # 价格
            posSide='long'                              # 持仓方向：多头
        )
        order_id2, err2 = engine.cex_driver.place_order(
            symbol='BTC-USDT-SWAP',                     # 交易对
            side='sell',                                # 卖出
            order_type='limit',                         # 限价单
            size=0.01,                                  # 单位：张
            price=round_dynamic(btc_price_now * 1.5),   # 价格
            posSide='short'                             # 持仓方向：空头
        )
        print("Placed 2 more orders, now cancelling all...")
        
        open_orders = engine.cex_driver.get_open_orders(symbol='BTC-USDT-SWAP')
        print(open_orders)
        
        start_time = time.time()
        cancel_all_err = engine.cex_driver.cancel_all(symbol='BTC-USDT-SWAP')
        end_time = time.time()
        print(f"Take time {end_time - start_time} seconds. Cancel all orders err: {cancel_all_err}")
        print("-----")
        
        open_orders = engine.cex_driver.get_open_orders(symbol='BTC-USDT-SWAP')
        print(open_orders)
        print("-----")

    except Exception as e:
        print("Error occurred:", e)

    # 结束
    print("API example strategy finished.")

    

if __name__ == "__main__":
    main()
