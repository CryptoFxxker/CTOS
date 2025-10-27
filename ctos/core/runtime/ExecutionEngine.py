import sys
import os
import re
import decimal
import time 
from concurrent.futures import ThreadPoolExecutor, as_completed
import multiprocessing

# 动态添加bpx包路径到sys.path
def _add_bpx_path():
    """添加bpx包路径到sys.path，支持多种运行方式"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 添加项目根目录的bpx路径（如果存在）
    project_root = os.path.abspath(os.path.join(current_dir, '../../..'))
    if os.path.exists(project_root) and project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root
# 执行路径添加
_PROJECT_ROOT = _add_bpx_path()
print('PROJECT_ROOT: ', _PROJECT_ROOT, 'CURRENT_DIR: ', os.path.dirname(os.path.abspath(__file__)))




import logging
from ctos.drivers.okx.util import BeijingTime, align_decimal_places, save_para, rate_price2order, cal_amount, round_like, fuzzy_exchange_input
import time
# from average_method import get_good_bad_coin_group  # 暂时注释掉，文件不存在
import json
from ctos.core.runtime.SystemMonitor import SystemMonitor
from ctos.core.runtime.AccountManager import AccountManager, ExchangeType, get_account_manager
import threading

def pick_exchange(cex, account, strategy='NONAME', strategy_detail='COMMON'):
    ex = cex if cex else ''
    if ex not in ('okx', 'bp'):
        ex = input("选择交易所 exchange [okx/bp] (默认 okx): ").strip()
    ex = fuzzy_exchange_input(ex)
    if account is None:
        user_input = input("请输入账户ID: ")
        if user_input:
            account = int(user_input)
        else:
            account = 0
    # 创建ExecutionEngine实例
    # INSERT_YOUR_CODE
    # 增加对strategy和strategy_detail参数的交互式输入，允许回车使用默认值
    
    if strategy:
        pass
    else:
        strategy = input(f"请输入策略名称 strategy (默认 {strategy if strategy else 'GRID_EXE_TEST'}): ").strip()

    if strategy_detail:
        pass
    else:
        strategy_detail = input(f"请输入策略详情 strategy_detail (默认 {strategy_detail if strategy_detail else 'COMMON'}): ").strip()
    engine = ExecutionEngine(account=account, strategy=strategy, strategy_detail=strategy_detail, exchange_type=ex)
    return ex, engine

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
        self.cex_driver.order_id_to_symbol = {}

        # 初始化监控和日志
        self.monitor = SystemMonitor(self, strategy)
        self.logger = self.monitor.logger
        
        
        # 初始化余额（如果支持）
        try:
            self.init_balance = float(self.cex_driver.fetch_balance())
        except Exception as e:
            self.logger.warning(f"Failed to fetch initial balance: {e}")
            self.init_balance = 0.0
        
        # 初始化其他属性
        self.watch_threads = []  # 存储所有监控线程
        self.soft_orders_to_focus = []
        
        self.logger.info(f"ExecutionEngine initialized for {self.exchange_type} account {account}")


    def set_coin_position_to_target(self, usdt_amounts=[10], coins=['eth'], soft=False, async_mode=False, max_workers= multiprocessing.cpu_count(), stack_mode=False):
        start_time = time.time()
        position_infos, err = self.cex_driver.get_position(keep_origin=False)
        if err:
            self.logger.warning(f"Failed to get position: {err}")
            return None, err
        all_pos_info = {}
        for x in position_infos:
            if float(x['quantity']) != 0:
                all_pos_info[x['symbol']] = x
        print('all_pos_info.keys: ', all_pos_info.keys())
        
        # 如果启用异步模式，使用并发处理
        if async_mode:
            if max_workers is None:
                max_workers = 5  # 默认5个并发线程
            print(f"🚀 启动异步模式，最大并发数: {max_workers}")
            
            # 准备任务数据
            tasks = []
            for coin, usdt_amount in zip(coins, usdt_amounts):
                tasks.append((coin, usdt_amount, soft, all_pos_info, stack_mode))
            time.sleep(0.033)
            # 使用线程池并发执行
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for coin, usdt_amount, soft, all_pos_info, stack_mode in tasks:
                    future = executor.submit(self._process_single_coin_async, coin, usdt_amount, soft, all_pos_info, stack_mode)
                    futures.append(future)
                
                # 等待所有任务完成
                for future in as_completed(futures):
                    try:
                        result = future.result(timeout=60)
                        if result:
                            print(f"\r✅ {result['coin'].upper()} 处理完成", end=' ')
                    except Exception as e:
                        print(f"❌ 任务执行异常: {e}")
            
            print(f'本次异步初始化耗时: {round(time.time() - start_time)}')
            return self.soft_orders_to_focus
        
        # 原有同步逻辑
        for coin, usdt_amount in zip(coins, usdt_amounts):
            try:
                symbol_full, _, _ = self.cex_driver._norm_symbol(coin)
                # exchange = init_CexClient(coin)
                if stack_mode:
                    data = None
                else:
                    data = all_pos_info.get(symbol_full, None)
                if not data:
                    if not stack_mode:
                        print('！！！！！！！！！！还没开仓呢哥！')
                        self.monitor.record_operation("SetCoinPosition  OpenPosition", self.strategy_detail,
                                                    {"symbol": symbol_full, "error": "无法获取持仓信息"})
                    try:
                        # if 1>0:
                        _, err = self.place_incremental_orders(abs(usdt_amount), coin, 'sell' if usdt_amount < 0 else 'buy', async_mode=async_mode,
                                                        soft=soft if coin.lower().find(
                                                            'xaut') == -1 or coin.lower().find(
                                                            'trx') == -1 else False)
                        if err:
                            self.logger.warning(f"Failed to place incremental orders: {err}")
                            return None, err
                    except Exception as ex:
                        print('！！！！！！！！！！！！！艹了！怎么出这种问题', ex)
                        self.monitor.handle_error(str(ex),
                                                  context=f" OpenPosition Fallback in set_coin_position_to_target for {coin}")
                    continue
                if data:
                    side = data['side']
                    open_position = float(data['quantityUSD']) if  side == 'long' else -float(data['quantityUSD'])
                    diff = open_position - usdt_amount
                    # if abs(diff) < 1:
                    #     continue
                    print(f"【{coin.upper()} 】需要补齐差额: {round(diff, 2)} = 现有:{round(open_position, 2)} - Target:{round(usdt_amount)}")
                    # 记录操作开始
                    
                    oid, err = self.place_incremental_orders(abs(diff), coin, 'sell' if diff > 0 else 'buy', soft=soft if coin.lower().find('xaut') == -1 or coin.lower().find('trx') == -1 else False)
                    if oid:
                        self.monitor.record_operation("SetCoinPosition AlignTo", self.strategy_detail, {
                        "symbol": symbol_full,
                        "target_amount": usdt_amount,
                        "open_position": open_position,
                        "diff": diff,
                        'order_id': oid,
                        'status': 'success'
                    })
                    else:
                        self.monitor.record_operation("SetCoinPosition AlignTo", self.strategy_detail, {
                        "symbol": symbol_full,
                        "target_amount": usdt_amount,
                        "open_position": open_position,
                        "diff": diff,
                        'error': err,
                        'status': 'failed'
                    })
            except Exception as e:
                print('！！！！！！！！！！！倒霉催的', e)
                self.monitor.handle_error(str(e), context=f"set_coin_position_to_target for {coin}")
                try:
                    oid, err = self.place_incremental_orders(abs(usdt_amount), coin, 'sell' if usdt_amount < 0 else 'buy', soft=soft if coin.lower().find('xaut') == -1 else False)
                    if oid:
                        self.monitor.record_operation("Handle Error", self.strategy_detail, {"symbol": symbol_full,
                        "target_amount": coin,
                        'order_id': oid,
                        'status': 'success'})
                    else:
                        self.monitor.record_operation("SetCoinPosition AlignTo", self.strategy_detail, {
                        "symbol": symbol_full,
                        "target_amount": coin,
                        'error': err,
                        'status': 'failed',
                    })
                    if err:
                        self.logger.warning(f"Failed to place incremental orders: {err}")
                        return None, err
                except Exception as ex:
                    print('！！！！！！！！！！！！！艹了！', e)
                    self.monitor.handle_error(str(ex), context=f"ErrorHandle Fallback in set_coin_position_to_target for {coin} after handle error to {'sell' if usdt_amount < 0 else 'buy'} {usdt_amount}")
                continue
        print(f'本次初始化耗时: {round(time.time() - start_time)}')
        return self.soft_orders_to_focus

    def _order_tracking_logic(self, coins, soft_orders_to_focus):
        start_time = time.time()
        done_coin = []
        # time.sleep(10)
        coin_process_times = {}
        exchange = self.cex_driver
        watch_times_for_all_coins = 0
        while True:
            need_to_watch = False
            for coin in coins:
                try:
                # if True:
                    if coin in done_coin:
                        # if coin in done_coin or coin == 'btc':
                        continue
                    if coin_process_times.get(coin):
                        coin_process_times[coin] += 1
                    else:
                        coin_process_times[coin] = 1
                    symbol = exchange._norm_symbol(coin)[0]
                    exist_orders_for_coin, err = exchange.get_open_orders(symbol=symbol, onlyOrderId=True)
                    # print(f'exist_orders_for_coin: {exist_orders_for_coin}, err: {err}')
                    if err or not exist_orders_for_coin:
                        done_coin.append(coin)
                        continue
                    if len(exist_orders_for_coin) == 0 or len([x for x in exist_orders_for_coin if x in soft_orders_to_focus]) == 0:
                        done_coin.append(coin)
                        continue
                    for order in exist_orders_for_coin:
                        if order in soft_orders_to_focus:
                            # print(f'order: {order} is still opening')
                            data, err = exchange.get_order_status(order_id=order, symbol=exchange._norm_symbol(coin)[0], keep_origin=False)
                            if err or not data:
                                print(f'data: {data}, err: {err}')
                                continue
                            now_price = exchange.get_price_now(symbol)
                            if now_price <= float(data['price']):
                                tmp_price = align_decimal_places(now_price, now_price * (1 + 0.0001 * (200 - watch_times_for_all_coins) / 200))
                                if tmp_price == float(data['price']):
                                    continue
                                new_price = tmp_price if tmp_price < float(data['price']) else float(data['price'])
                            else:
                                tmp_price = align_decimal_places(now_price, now_price * (1 - 0.0001 * (200 - watch_times_for_all_coins) / 200))
                                if tmp_price == float(data['price']):
                                    continue
                                new_price = tmp_price if tmp_price > float(data['price']) else float(data['price'])
                            # 解决 TypeError: 'str' object cannot be interpreted as an integer
                            # pop() 需要传入索引时是整数，但这里 order 是订单号（字符串），应使用 remove
                            need_to_watch = True
                            new_order, err = exchange.amend_order(order_id=order,  symbol=self.cex_driver._norm_symbol(coin)[0], price=new_price, quantity=float(data['quantity']))
                            if new_order is None and err is None:
                                soft_orders_to_focus.remove(order)
                                print(f"\n  {order} is deal: {self.cex_driver._norm_symbol(coin)[0]}")
                                done_coin.append(coin)
                                time.sleep(2.88)
                            else:
                                if err is None and exchange.cex.lower() == 'backpack':
                                    soft_orders_to_focus[soft_orders_to_focus.index(order)] = new_order
                                print(f"\n\namend_order  {order} to {new_order}: {self.cex_driver._norm_symbol(coin)[0]} {new_price}, {float(data['quantity'])}")
                                time.sleep(6.66)
                    print(f'\r共有{len(coins)}个币种，完成了{len(done_coin)}个, 正追踪【{coin}】中，它目前还有{len(exist_orders_for_coin)}个订单', end=' ')
                except Exception as e:
                    try:
                        print('❌ 订单追踪失败000：', coin, exist_orders_for_coin, len(soft_orders_to_focus), e, data)
                    except Exception as e1:
                        print('❌ 订单追踪失败111：', coin, exist_orders_for_coin, len(soft_orders_to_focus), e, e1)
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

    def revoke_all_orders(self):
        open_orders, err = self.cex_driver.get_open_orders(onlyOrderId=True)
        if err:
            print('❌ 获取未完成订单失败: {err}')
            return
        for order_id in open_orders:
            if order_id in self.cex_driver.order_id_to_symbol.keys():
                self.cex_driver.revoke_order(order_id, self.cex_driver.order_id_to_symbol[order_id])
        self.cex_driver.order_id_to_symbol = {}

    def place_incremental_orders(self, usdt_amount, coin, direction, soft=False, price=None, async_mode=False):
        """
        根据usdt_amount下分步订单，并通过 SystemMonitor 记录审核信息
        操作中调用内部封装的买卖接口（本版本建议使用 HTTP 接口下单的方式）。
        """
        symbol_full, _, _ = self.cex_driver._norm_symbol(coin)
        if price:
            soft=True
        exchange = self.cex_driver
        soft_orders_to_focus = []
        exchange_limits_info, err = self.cex_driver.exchange_limits(symbol=symbol_full)
        if err:
            print('CEX DRIVER.exchange_limits error ', err)
            return None, err
        size_precision = exchange_limits_info['size_precision']
        price_precision = exchange_limits_info['price_precision']
        min_order_size = exchange_limits_info['min_order_size']
        contract_value = exchange_limits_info['contract_value']

        # 获取当前市场价格
        price = exchange.get_price_now(coin) if price is None else price
        if price is None:
            self.monitor.record_operation("PlaceIncrementalOrders", self.strategy_detail,
                                          {"symbol": symbol_full, "error": "获取当前价格失败", "async_mode":async_mode})
            return None, "获取当前价格失败"
        base_order_money = price * contract_value
        
        # print(base_order_money, order_amount)
        order_amount = round_like(min_order_size , usdt_amount / base_order_money)
        add_amount_times = 1
        while order_amount == 0 and add_amount_times < 4:
            add_amount_times += 1
            order_amount = round_like(min_order_size , usdt_amount * pow(1.25, add_amount_times) / base_order_money)
        if order_amount == 0:
            self.monitor.record_operation("PlaceIncrementalOrders", self.strategy_detail,
                                          {"symbol": symbol_full, "error": "订单金额过小，无法下单", "async_mode":async_mode})
            if async_mode:
                print(f"\r订单金额过小，无法下单", end=' ')
            else:
                print('订单金额过小，无法下单')
            return None, "订单金额过小，无法下单"
        order_id = None
        if direction.lower() == 'buy':
            if not soft:
                order_id, err_msg = self.cex_driver.place_order(symbol_full, 'buy', 'MARKET', order_amount)
                if order_id:
                    self.cex_driver.order_id_to_symbol[order_id] = coin
                    soft_orders_to_focus.append(order_id)
            else:
                if price:
                    limit_price = round_like(price_precision, price)
                else:
                    limit_price = round_like(price_precision, price * 0.9995)
                print(f"limit_price: {limit_price}, order_amount:{order_amount}")
                order_id, err_msg = self.cex_driver.place_order(symbol_full, 'buy', 'limit', order_amount, limit_price)
                if order_id:
                    self.cex_driver.order_id_to_symbol[order_id] = coin
                    soft_orders_to_focus.append(order_id)
            if order_id:
                print(f"\r{BeijingTime()} {self.cex_driver.cex.upper()}-{self.account} **BUY** order for {order_amount if order_id else 0} units of 【{coin.upper()}】 at price {price}", end=' ' if async_mode else '')
                self.monitor.record_operation("PlaceIncrementalOrders", self.strategy_detail, {
                    "symbol": symbol_full, "action": "buy", "price": price, "sizes": order_amount, 'order_id': order_id})
            else:
                print(f"❌ 订单创建失败: {err_msg}")
                self.monitor.record_operation("Failed PlaceIncrementalOrders", self.strategy_detail, {
                    "symbol": symbol_full, "action": "buy", "price": price, "sizes": order_amount, "error": err_msg, "async_mode":async_mode})

        elif direction.lower() == 'sell':
            if not soft:
                order_id, err_msg = self.cex_driver.place_order(symbol_full, 'sell', 'MARKET', order_amount)
                if order_id:
                    soft_orders_to_focus.append(order_id)
            else:
                if price:
                    limit_price =  round_like(price_precision, price)
                else:
                    limit_price = round_like(price_precision, price * 1.0005)
                print(f"limit_price: {limit_price}, order_amount:{order_amount}")
                order_id, err_msg = self.cex_driver.place_order(symbol_full, 'sell', 'limit', order_amount, limit_price)
                if order_id:
                    self.cex_driver.order_id_to_symbol[order_id] = coin
                    soft_orders_to_focus.append(order_id)
                else:
                    self.cex_driver.order_id_to_symbol[order_id] = coin
            if order_id:
                print(f"\r {BeijingTime()} {self.cex_driver.cex.upper()}-{self.account} **SELL**  order for {order_amount if order_id else 0} units of 【{coin.upper()}】 at price {price} for $ {usdt_amount}", end=' ' if async_mode else '')
                self.monitor.record_operation("PlaceIncrementalOrders", self.strategy_detail, {
                    "symbol": symbol_full, "action": "sell", "price": price, "sizes": order_amount, 'order_id': order_id, "async_mode":async_mode})
            else:
                print(f"❌ 订单创建失败: {err_msg}")
                self.monitor.record_operation("Failed PlaceIncrementalOrders", self.strategy_detail, {
                    "symbol": symbol_full, "action": "sell", "price": price, "sizes": order_amount, "error": err_msg, "async_mode":async_mode})

        remaining_usdt = usdt_amount - (base_order_money * order_amount)
        # 任何剩余的资金如果无法形成更多订单，结束流程
        if remaining_usdt > 0:
            print(f"\rRemaining USDT {round(remaining_usdt, 4)} ", end='')
        if soft:
            self.soft_orders_to_focus += soft_orders_to_focus
        return soft_orders_to_focus, None

    def _process_single_coin_async(self, coin, usdt_amount, soft, all_pos_info, stack_mode=False):
        """
        异步处理单个币种的持仓调整
        """
        try:
            symbol_full, _, _ = self.cex_driver._norm_symbol(coin)
            if stack_mode:
                data = None
            else:
                data = all_pos_info.get(symbol_full, None)
            
            if not data:
                if not stack_mode:
                    print(f'🆕 {coin.upper()} 还没开仓呢哥！')
                try:
                    _, err = self.place_incremental_orders(abs(usdt_amount), coin, 'sell' if usdt_amount < 0 else 'buy',
                                                    soft=soft if coin.lower().find('xaut') == -1 or coin.lower().find('trx') == -1 else False)
                    if err:
                        return {'coin': coin, 'success': False, 'error': err}
                except Exception as ex:
                    print(f'❌ {coin.upper()} 开仓失败: {ex}')
                    return {'coin': coin, 'success': False, 'error': str(ex)}
            else:
                side = data['side']
                open_position = float(data['quantityUSD']) if side == 'long' else -float(data['quantityUSD'])
                diff = open_position - usdt_amount
                
                if abs(diff) < 1:
                    return {'coin': coin, 'success': True, 'message': '差额太小，跳过'}
                print(f"\r📊 【{coin.upper()}】需要补齐差额: {round(diff, 2)} = 现有:{round(open_position, 2)} - Target:{round(usdt_amount)}", end=' ')
                oid, err = self.place_incremental_orders(abs(diff), coin, 'sell' if diff > 0 else 'buy', 
                                                        soft=soft if coin.lower().find('xaut') == -1 or coin.lower().find('trx') == -1 else False)
                if oid:
                    return {'coin': coin, 'success': True, 'order_id': oid}
                else:
                    return {'coin': coin, 'success': False, 'error': err}
                    
        except Exception as e:
            print(f'❌ {coin.upper()} 处理异常: {e}')
            return {'coin': coin, 'success': False, 'error': str(e)}


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
            from ctos.drivers.okx.driver import init_CexClient
            eth = init_CexClient('eth', account)
            btc = init_CexClient('btc', account)
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