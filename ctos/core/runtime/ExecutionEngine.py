import sys
import os
import re
import decimal

# 确保项目根目录在sys.path中
def _add_bpx_path():
    """添加bpx包路径到sys.path，支持多种运行方式"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    bpx_path = os.path.join(current_dir, 'bpx')
    if bpx_path not in sys.path:
        sys.path.insert(0, bpx_path)
    project_root = os.path.abspath(os.path.join(current_dir, '../../..'))
    root_bpx_path = os.path.join(project_root, 'bpx')
    if os.path.exists(root_bpx_path) and root_bpx_path not in sys.path:
        sys.path.insert(0, root_bpx_path)
    if os.path.exists(project_root) and project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root
# 执行路径添加
_PROJECT_ROOT = _add_bpx_path()




import logging
from ctos.drivers.okx.util import BeijingTime, align_decimal_places, save_para, rate_price2order, cal_amount, round_like
import time
# from average_method import get_good_bad_coin_group  # 暂时注释掉，文件不存在
import json
from ctos.core.runtime.SystemMonitor import SystemMonitor
from ctos.core.runtime.AccountManager import AccountManager, ExchangeType, get_account_manager
import threading


class ExecutionEngine:
    def __init__(self, account=0, strategy='Classical', strategy_detail="COMMON",  exchange_type='okx', account_manager=None):
        """
        Initialize the execution engine with API credentials and setup logging.
        
        Args:
            account: 账户ID
            strategy: 策略名称
            strategy_detail: 策略详情
            symbol: 交易对
            exchange_type: 交易所类型 ('okx', 'backpack')
            account_manager: AccountManager实例，如果为None则使用全局实例
        """
        self.account = account
        self.exchange_type = exchange_type.lower()
        self.strategy_detail = strategy_detail
        
        # 获取AccountManager
        if account_manager is None:
            self.account_manager = get_account_manager()
        else:
            self.account_manager = account_manager
        
        # 获取Driver
        self.cex_driver = self.account_manager.get_driver(
            ExchangeType(self.exchange_type), 
            account, 
            auto_create=True
        )
        
        if self.cex_driver is None:
            raise RuntimeError(f"Failed to get {self.exchange_type} driver for account {account}")
        
        # 初始化监控和日志
        self.monitor = SystemMonitor(self, strategy)
        self.logger = self.monitor.logger
        
        
        # 初始化余额（如果支持）
        try:
            self.init_balance = float(self.cex_driver.fetch_balance('USDT'))
        except Exception as e:
            self.logger.warning(f"Failed to fetch initial balance: {e}")
            self.init_balance = 0.0
        
        # 初始化其他属性
        self.watch_threads = []  # 存储所有监控线程
        self.soft_orders_to_focus = []
        
        self.logger.info(f"ExecutionEngine initialized for {self.exchange_type} account {account}")


    def setup_logger(self):
        """
        Setup the logger to record all activities, trades, and operations.
        """
        handler = logging.FileHandler('okex_execution_engine.log')
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)


    def set_coin_position_to_target(self, usdt_amounts=[10], coins=['eth'], soft=False):
        start_time = time.time()
        position_infos = self.cex_driver.get_position(keep_origin=False)
        all_pos_info = {}
        for x in position_infos:
            if float(x['quantity']) != 0:
                all_pos_info[x['symbol']] = x
        print('all_pos_info.keys: ', all_pos_info.keys())
        for coin, usdt_amount in zip(coins, usdt_amounts):
            try:
                symbol_full = f"{coin.upper()}-USDT-SWAP"
                # exchange = init_OkxClient(coin)
                data = all_pos_info.get(symbol_full, None)
                if not data:
                    print('！！！！！！！！！！还没开仓呢哥！')
                    self.monitor.record_operation("SetCoinPosition KaiCang", self.strategy_detail,
                                                  {"symbol": symbol_full, "error": "无法获取持仓信息"})
                    try:
                        # if 1>0:
                        if usdt_amount < 0:
                            self.place_incremental_orders(abs(usdt_amount), coin, 'sell',
                                                          soft=soft if coin.lower().find(
                                                              'xaut') == -1 or coin.lower().find(
                                                              'trx') == -1 else False)
                            self.monitor.record_operation("SetCoinPosition KaiCang",
                                                          self.strategy_detail + "not position_info",
                                                          {
                                                              "symbol": symbol_full, "action": "sell",
                                                              "order_price": self.cex_driver.get_price_now(symbol_full),
                                                              "amount": usdt_amount
                                                          })
                        else:
                            self.place_incremental_orders(abs(usdt_amount), coin, 'buy', soft=soft if coin.lower().find(
                                'xaut') == -1 or coin.lower().find('trx') == -1 else False)
                            self.monitor.record_operation("SetCoinPosition KaiCang",
                                                          self.strategy_detail + "not position_info",
                                                          {
                                                              "symbol": symbol_full, "action": "buy",
                                                              "order_price": self.cex_driver.get_price_now(symbol_full),
                                                              "amount": usdt_amount
                                                          })
                    except Exception as ex:
                        print('！！！！！！！！！！！！！艹了！', e)
                        self.monitor.handle_error(str(ex),
                                                  context=f"KaiCang Fallback in set_coin_position_to_target for {coin}")
                    continue
                if data:
                    position_info = {
                        '产品类型': data['instType'],
                        '保证金模式': data['mgnMode'],
                        '持仓ID': data['posId'],
                        '持仓方向': data['posSide'],
                        '持仓数量': data['pos'],
                        '仓位资产币种': data['posCcy'],
                        '可平仓数量': data['availPos'],
                        '开仓平均价': data['avgPx'],
                        '未实现收益': data['upl'],
                        '未实现收益率': data['uplRatio'],
                        '最新成交价': data['last'],
                        '预估强平价': data['liqPx'],
                        '最新标记价格': data['markPx'],
                        '初始保证金': data['imr'],
                        '保证金余额': data['margin'],
                        '保证金率': data['mgnRatio'],
                        '维持保证金': data['mmr'],
                        '产品ID': data['instId'],
                        '杠杆倍数': data['lever'],
                        '负债额': data['liab'],
                        '负债币种': data['liabCcy'],
                        '利息': data['interest'],
                        '最新成交ID': data['tradeId'],
                        '信号区': data['adl'],
                        '占用保证金的币种': data['ccy'],
                        '最新指数价格': data['idxPx']
                    }
                    mark_px = float(position_info['最新标记价格'])
                    pos_qty = float(position_info['持仓数量'])
                    unit_price = rate_price2order[coin]  # 获取当前币种的单位价格比重
                    base_order_money = unit_price * mark_px
                    open_position = pos_qty * base_order_money
                    position_info['每张价值'] = base_order_money
                    position_info['本次开仓价值'] = open_position
                    diff = open_position - usdt_amount

                    print(
                        f"【{coin.upper()} 】需要补齐差额: {round(diff, 2)} = Exist:{round(open_position, 2)} - Target:{round(usdt_amount)}",
                        end=' -> ')
                    # 记录操作开始
                    self.monitor.record_operation("SetCoinPosition BuQi", self.strategy_detail, {
                        "symbol": symbol_full,
                        "target_amount": usdt_amount,
                        "open_position": open_position,
                        "diff": diff
                    })
                    if diff > 0:
                        order_price = mark_px * 1.0001
                        self.place_incremental_orders(abs(diff), coin, 'sell',
                                                      soft=soft if coin.lower().find('xaut') == -1 or coin.lower().find(
                                                          'trx') == -1 else False)
                        self.monitor.record_operation("SetCoinPosition BuQi", self.strategy_detail, {
                            "symbol": symbol_full, "action": "sell", "order_price": order_price, "amount": abs(diff)
                        })
                    elif diff < 0:
                        order_price = mark_px * 0.9999
                        self.place_incremental_orders(abs(diff), coin, 'buy',
                                                      soft=soft if coin.lower().find('xaut') == -1 or coin.lower().find(
                                                          'trx') == -1 else False)
                        self.monitor.record_operation("SetCoinPosition BuQi", self.strategy_detail, {
                            "symbol": symbol_full, "action": "buy", "order_price": order_price, "amount": abs(diff)
                        })
            except Exception as e:
                print('！！！！！！！！！！！倒霉催的', e)
                self.monitor.handle_error(str(e), context=f"set_coin_position_to_target for {coin}")
                try:
                    # if 1>0:
                    if usdt_amount < 0:
                        self.place_incremental_orders(abs(usdt_amount), coin, 'sell',
                                                      soft=soft if coin.lower().find('xaut') == -1 or coin.lower().find(
                                                          'trx') == -1 else False)
                        self.monitor.record_operation("SetCoinPosition BaoCuoChuli",
                                                      self.strategy_detail + "ExceptionFallback", {
                                                          "symbol": symbol_full, "action": "sell",
                                                          "order_price": self.cex_driver.get_price_now(symbol_full),
                                                          "amount": usdt_amount
                                                      })
                    else:
                        self.place_incremental_orders(abs(usdt_amount), coin, 'buy',
                                                      soft=soft if coin.lower().find('xaut') == -1 or coin.lower().find(
                                                          'trx') == -1 else False)
                        self.monitor.record_operation("SetCoinPosition BaoCuoChuli",
                                                      self.strategy_detail + "ExceptionFallback", {
                                                          "symbol": symbol_full, "action": "buy",
                                                          "order_price": self.cex_driver.get_price_now(symbol_full),
                                                          "amount": usdt_amount
                                                      })
                except Exception as ex:
                    print('！！！！！！！！！！！！！艹了！', e)
                    self.monitor.handle_error(str(ex),
                                              context=f"BaoCuoChuli Fallback in set_coin_position_to_target for {coin}")
                continue
        print(f'本次初始化耗时: {round(time.time() - start_time)}')
        return self.soft_orders_to_focus

    def _order_tracking_logic(self, coins, soft_orders_to_focus):
        start_time = time.time()
        done_coin = []
        time.sleep(10)
        coin_process_times = {}
        exchange = self.cex_driver
        watch_times_for_all_coins = 0
        while True:
            need_to_watch = False
            for coin in coins:
                try:
                    if coin in done_coin:
                        # if coin in done_coin or coin == 'btc':
                        continue
                    time.sleep(3)
                    if coin_process_times.get(coin):
                        coin_process_times[coin] += 1
                    else:
                        coin_process_times[coin] = 1
                    exchange.symbol = "{}-USDT-SWAP".format(coin.upper())
                    exist_orders_for_coin = exchange.get_open_orders('SWAP')[0]
                    if len(exist_orders_for_coin) == 0:
                        done_coin.append(coin)
                        continue
                    for order in exist_orders_for_coin:
                        if order in soft_orders_to_focus:
                            data = exchange.get_order_status(order)[0]['data'][0]
                            now_price = exchange.get_price_now()
                            if now_price <= float(data['px']):
                                tmp_price = align_decimal_places(now_price, now_price * (
                                            1 + 0.0001 * (200 - watch_times_for_all_coins) / 200))
                                new_price = tmp_price if tmp_price < float(data['px']) else float(data['px'])
                            else:
                                tmp_price = align_decimal_places(now_price, now_price * (
                                            1 - 0.0001 * (200 - watch_times_for_all_coins) / 200))
                                new_price = tmp_price if tmp_price > float(data['px']) else float(data['px'])
                            exchange.amend_order(new_price, float(data['sz']), order)
                            need_to_watch = True
                    print(f'追踪【{coin}】中，它目前还有{len(exist_orders_for_coin)}个订单', end=' ')
                except Exception as e:
                    print('❌ 订单追踪失败：', coin, exist_orders_for_coin, len(soft_orders_to_focus), e)
            # 这里之前多打了个tab 差点没把我弄死，每次都只监控一个订单就退出了，绝
            if not need_to_watch or time.time() - start_time > 10800:
                print(f'✅ {"到点了" if need_to_watch else "所有订单都搞定了"}，收工！')
                self.soft_orders_to_focus = [x for x in self.soft_orders_to_focus if x not in soft_orders_to_focus]
                if len(self.watch_threads) >= 1:
                    self.watch_threads = self.watch_threads[:-1]
                return
            watch_times_for_all_coins += 1

    def focus_on_orders(self, coins, soft_orders_to_focus):
        """为每一组监控任务启动一个后台线程"""
        t = threading.Thread(
            target=self._order_tracking_logic,
            args=(coins, soft_orders_to_focus),
            daemon=True
        )
        t.start()
        self.watch_threads.append(t)
        print(f"🎯 新监控线程已启动，共 {len(self.watch_threads)} 个任务运行中")

    def place_incremental_orders(self, usdt_amount, coin, direction, soft=False, price=None):
        """
        根据usdt_amount下分步订单，并通过 SystemMonitor 记录审核信息
        操作中调用内部封装的买卖接口（本版本建议使用 HTTP 接口下单的方式）。
        """
        symbol_full, _, _ = self.cex_driver._norm_symbol(coin)
        if price:
            soft=True
        exchange = self.cex_driver
        if soft:
            soft_orders_to_focus = []
        exchange_limits_info, err = self.cex_driver.exchange_limits(symbol=symbol_full)
        if err:
            print('CEX DRIVER.exchange_limits error ', err)
            return
        size_precision = exchange_limits_info['size_precision']
        price_precision = exchange_limits_info['price_precision']
        min_order_size = exchange_limits_info['min_order_size']
        contract_value = exchange_limits_info['contract_value']

        # 获取当前市场价格
        price = exchange.get_price_now(coin)
        if price is None:
            self.monitor.record_operation("PlaceIncrementalOrders", self.strategy_detail,
                                          {"symbol": symbol_full, "error": "获取当前价格失败"})
            return
        base_order_money = price * contract_value
        
        # print(base_order_money, order_amount)
        order_amount = round_like(min_order_size , usdt_amount / base_order_money)
        if order_amount == 0:
            self.monitor.record_operation("PlaceIncrementalOrders", self.strategy_detail,
                                          {"symbol": symbol_full, "error": "订单金额过小，无法下单"})
            print('订单金额过小，无法下单')
            return
        order_id = 0
        if direction.lower() == 'buy':
            if not soft:
                if order_amount > 0:
                    order_id, _ = self.cex_driver.place_order(symbol_full, 'buy', 'MARKET', order_amount)
            else:
                if order_amount > 0:
                    if price:
                        limit_price =  round_like(price_precision, price)
                    else:
                        limit_price = round_like(price_precision, price * 0.9999)
                    print(f"limit_price: {limit_price}, order_amount:{order_amount}")
                    order_id, _ = self.cex_driver.place_order(symbol_full, 'buy', 'limit', order_amount, limit_price)
                    if order_id:
                        soft_orders_to_focus.append(order_id)

            print(f"\r**BUY** order for {order_amount if order_id else 0} units of 【{coin.upper()}】 at price {price}")
            self.monitor.record_operation("PlaceIncrementalOrders", self.strategy_detail, {
                "symbol": symbol_full, "action": "buy", "price": price, "sizes": [order_amount if order_id else 0]
            })
        elif direction.lower() == 'sell':
            if not soft:
                if order_amount > 0:
                    order_id, _ = self.cex_driver.place_order(symbol_full, 'sell', 'MARKET', order_amount)
            else:
                if order_amount > 0:
                    if price:
                        limit_price =  round_like(price_precision, price)
                    else:
                        limit_price = round_like(price_precision, price * 1.0001)
                    print(f"limit_price: {limit_price}, order_amount:{order_amount}")
                    order_id, _ = self.cex_driver.place_order(symbol_full, 'sell', 'limit', order_amount, limit_price)
                    if order_id:
                        soft_orders_to_focus.append(order_id)
            print(
                f"\r **SELL**  order for {order_amount if order_id else 0} units of 【{coin.upper()}】 at price {price}")
            self.monitor.record_operation("PlaceIncrementalOrders", self.strategy_detail, {
                "symbol": symbol_full, "action": "sell", "price": price, "sizes": [order_amount]
            })

        remaining_usdt = usdt_amount - (base_order_money * order_amount)
        # 任何剩余的资金如果无法形成更多订单，结束流程
        if remaining_usdt > 0:
            print(f"\rRemaining USDT {round(remaining_usdt, 4)} ", end='')
        if soft:
            self.soft_orders_to_focus += soft_orders_to_focus
            return soft_orders_to_focus
        else:
            return []


def init_all_thing(exchange_type='okx', account=0):
    """
    初始化所有组件
    
    Args:
        exchange_type: 交易所类型 ('okx', 'backpack')
        account: 账户ID
        
    Returns:
        (engine, eth_client, btc_client)
    """
    # 创建ExecutionEngine
    engine = ExecutionEngine(account=account, exchange_type=exchange_type)
    
    # 获取AccountManager
    account_manager = engine.account_manager
    
    # 获取ETH和BTC客户端（仅对OKX有效）
    eth = None
    btc = None
    
    if exchange_type.lower() == 'okx':
        try:
            from ctos.drivers.okx.driver import init_OkxClient
            eth = init_OkxClient('eth', account)
            btc = init_OkxClient('btc', account)
        except Exception as e:
            engine.logger.warning(f"Failed to create ETH/BTC clients: {e}")
    
    return engine, eth, btc



if __name__ == '__main__':
    # 测试AccountManager和ExecutionEngine集成
    print("=== 测试AccountManager和ExecutionEngine集成 ===")
    
    try:
        # 1. 测试AccountManager
        print("\n1. 测试AccountManager:")
        from .AccountManager import get_account_manager, ExchangeType
        
        # 获取AccountManager实例
        account_manager = get_account_manager()
        print("✓ AccountManager获取成功")
        
        # 测试创建OKX Driver
        print("\n1.1 测试创建OKX Driver:")
        okx_driver = account_manager.get_driver(ExchangeType.OKX, 0)
        if okx_driver:
            print("✓ OKX Driver创建成功")
        else:
            print("✗ OKX Driver创建失败")
        
        # 测试创建Backpack Driver
        print("\n1.2 测试创建Backpack Driver:")
        bp_driver = account_manager.get_driver(ExchangeType.BACKPACK, 0)
        if bp_driver:
            print("✓ Backpack Driver创建成功")
        else:
            print("✗ Backpack Driver创建失败")
        
        # 获取统计信息
        stats = account_manager.get_stats()
        print(f"Driver统计: {stats}")
        
        # 2. 测试ExecutionEngine
        print("\n2. 测试ExecutionEngine:")
        
        # 测试OKX ExecutionEngine
        print("\n2.1 测试OKX ExecutionEngine:")
        try:
            okx_engine = ExecutionEngine(account=0, exchange_type='okx')
            print("✓ OKX ExecutionEngine创建成功")
            print(f"交易所类型: {okx_engine.exchange_type}")
            print(f"账户ID: {okx_engine.account}")
        except Exception as e:
            print(f"✗ OKX ExecutionEngine创建失败: {e}")
        
        # 测试Backpack ExecutionEngine
        print("\n2.2 测试Backpack ExecutionEngine:")
        try:
            bp_engine = ExecutionEngine(account=0, exchange_type='backpack')
            print("✓ Backpack ExecutionEngine创建成功")
            print(f"交易所类型: {bp_engine.exchange_type}")
            print(f"账户ID: {bp_engine.account}")
        except Exception as e:
            print(f"✗ Backpack ExecutionEngine创建失败: {e}")
        
        # 3. 测试错误处理函数
        print("\n3. 测试错误处理函数:")
        
        # 使用OKX引擎测试错误处理
        if 'okx_engine' in locals():
            print("\n3.1 测试价格精度调整:")
            test_price = 4200.001
            error_msg = "Price decimal too long"
            adjusted_price = okx_engine._adjust_precision_for_error(test_price, error_msg, 'price')
            print(f"原始价格: {test_price}")
            print(f"调整后价格: {adjusted_price}")
            
            print("\n3.2 测试数量精度调整:")
            test_quantity = 0.0111
            error_msg = "Quantity decimal too long"
            adjusted_quantity = okx_engine._adjust_precision_for_error(test_quantity, error_msg, 'quantity')
            print(f"原始数量: {test_quantity}")
            print(f"调整后数量: {adjusted_quantity}")
        
        # 4. 测试init_all_thing函数
        print("\n4. 测试init_all_thing函数:")
        try:
            engine, eth, btc = init_all_thing(exchange_type='okx', account=0)
            print("✓ init_all_thing成功")
            print(f"Engine类型: {type(engine).__name__}")
            print(f"ETH客户端: {'✓' if eth else '✗'}")
            print(f"BTC客户端: {'✓' if btc else '✗'}")
        except Exception as e:
            print(f"✗ init_all_thing失败: {e}")
        
        print("\n=== 所有测试完成 ===")
        
    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    
    exit()