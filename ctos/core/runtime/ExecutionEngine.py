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

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ctos', 'drivers', 'okx'))
import logging
from ctos.drivers.okx.util import BeijingTime, align_decimal_places, save_para, rate_price2order, cal_amount, get_min_amount_to_trade
import time
# from average_method import get_good_bad_coin_group  # 暂时注释掉，文件不存在
import json
from ctos.core.runtime.SystemMonitor import SystemMonitor
from ctos.core.runtime.AccountManager import AccountManager, ExchangeType, get_account_manager
import threading


class OkexExecutionEngine:
    def __init__(self, account=0, strategy='Classical', strategy_detail="StrategyAdjustment", 
                 symbol='eth', exchange_type='okx', account_manager=None):
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
        
        # 初始化交易所特定配置
        if self.exchange_type == 'okx':
            from ctos.drivers.okx.driver import init_OkxClient
            self.min_amount_to_trade = get_min_amount_to_trade(
                init_OkxClient, 
                path=os.path.join(_PROJECT_ROOT, 'apps', 'strategies', 'hedge', 'trade_log_okex', 'min_amount_to_trade.json')
            )
        else:
            # 其他交易所的配置
            self.min_amount_to_trade = {}
        
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


    def _adjust_precision_for_error(self, value, error_msg, value_type='price'):
        """
        根据错误信息调整数值精度
        :param value: 需要调整的数值
        :param error_msg: 错误信息
        :param value_type: 'price' 或 'quantity'
        :return: 调整后的数值
        """
        if not error_msg:
            return value
            
        error_str = str(error_msg).lower()
        
        # 处理价格精度错误
        if value_type == 'price' and ('price decimal too long' in error_str or 'decimal too long' in error_str):
            # 减少价格的小数位数
            if '.' in str(value):
                decimal_places = len(str(value).split('.')[1])
                new_places = max(0, decimal_places - 1)
                return round(value, new_places)
            return value
            
        # 处理数量精度错误
        elif value_type == 'quantity' and ('quantity decimal too long' in error_str or 'decimal too long' in error_str):
            # 减少数量的小数位数
            if '.' in str(value):
                decimal_places = len(str(value).split('.')[1])
                new_places = max(0, decimal_places - 1)
                return round(value, new_places)
            return value
            
        # 处理数量过小错误
        elif value_type == 'quantity' and ('quantity is below the minimum' in error_str or 'below the minimum' in error_str):
            # 增加数量到最小允许值
            return max(value, 0.0001)  # 设置一个合理的最小值
            
        # 处理解析错误（通常是由于精度问题）
        elif 'parse request payload error' in error_str or 'invalid decimal' in error_str:
            if value_type == 'price':
                # 价格保留2位小数
                return round(value, 2)
            elif value_type == 'quantity':
                # 数量保留4位小数
                return round(value, 4)
        return value

    def _unified_place_order(self, symbol, side, order_type, size, price=None, max_retries=3, **kwargs):
        """
        统一的下单函数，处理不同CEX的错误格式并进行重试
        :param symbol: 交易对
        :param side: 买卖方向 ('buy'/'sell')
        :param order_type: 订单类型 ('limit'/'market')
        :param size: 数量
        :param price: 价格（限价单需要）
        :param max_retries: 最大重试次数
        :param kwargs: 其他参数
        :return: (order_id, error)
        """
        exchange = self.cex_driver
        original_size = size
        original_price = price
        
        for attempt in range(max_retries + 1):
            try:
                # 调用原始下单方法
                if side.lower() == 'buy':
                    order_id, error = exchange.place_order(symbol, 'buy', order_type, size, price, **kwargs)
                else:
                    order_id, error = exchange.place_order(symbol,  'sell', order_type, size, price, **kwargs)
                
                # 如果下单成功，直接返回
                if order_id and not error:
                    if attempt > 0:
                        self.logger.info(f"下单成功 (重试第{attempt}次): {symbol} {side} {size}@{price}")
                    return order_id, None
                
                # 如果还有重试机会，根据错误调整参数
                if attempt < max_retries and error:
                    error_str = str(error)
                    self.logger.warning(f"下单失败 (第{attempt + 1}次): {error_str}")
                    
                    # 记录错误信息
                    self.monitor.record_operation("UnifiedPlaceOrder_Error", self.strategy_detail, {
                        "symbol": symbol,
                        "side": side,
                        "order_type": order_type,
                        "size": size,
                        "price": price,
                        "error": error_str,
                        "attempt": attempt + 1
                    })
                    
                    # 根据错误类型调整参数
                    if order_type.lower() == 'limit' and price is not None:
                        # 调整价格精度
                        new_price = self._adjust_precision_for_error(price, error_str, 'price')
                        if new_price != price:
                            price = new_price
                            self.logger.info(f"调整价格精度: {original_price} -> {price}")
                    
                    # 调整数量精度
                    new_size = self._adjust_precision_for_error(size, error_str, 'quantity')
                    if new_size != size:
                        size = new_size
                        self.logger.info(f"调整数量精度: {original_size} -> {size}")
                    
                    # 如果调整后参数没有变化，尝试其他调整策略
                    if new_price == price and new_size == size:
                        if 'quantity is below the minimum' in error_str.lower():
                            # 数量过小，尝试增加数量
                            size = max(size * 1.1, 0.001)
                            self.logger.info(f"增加数量: {original_size} -> {size}")
                        elif 'price decimal too long' in error_str.lower():
                            # 价格精度过高，减少小数位
                            price = round(price, 2)
                            self.logger.info(f"减少价格精度: {original_price} -> {price}")
                        elif 'quantity decimal too long' in error_str.lower():
                            # 数量精度过高，减少小数位
                            size = round(size, 4)
                            self.logger.info(f"减少数量精度: {original_size} -> {size}")
                    
                    # 等待一段时间后重试
                    time.sleep(0.5)
                else:
                    # 最后一次尝试失败，返回错误
                    self.monitor.handle_error(str(error), context=f"UnifiedPlaceOrder final attempt failed for {symbol}")
                    return None, error
                    
            except Exception as e:
                if attempt < max_retries:
                    self.logger.warning(f"下单异常 (第{attempt + 1}次): {str(e)}")
                    time.sleep(0.5)
                else:
                    self.monitor.handle_error(str(e), context=f"UnifiedPlaceOrder exception for {symbol}")
                    return None, str(e)
        
        return None, "Max retries exceeded"

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

    def place_incremental_orders(self, usdt_amount, coin, direction, rap=None, soft=False):
        # @TODO 需要继续实现一个订单解决了，分拆订单实在是无奈之举的.2025.07.13 14.22 成功合并订单！以后速度能更快了~
        """
        根据usdt_amount下分步订单，并通过 SystemMonitor 记录审核信息
        操作中调用内部封装的买卖接口（本版本建议使用 HTTP 接口下单的方式）。
        """
        if coin.find('-') == -1:
            symbol_full = f"{coin.upper()}-USDT-SWAP"
        else:
            symbol_full = coin
        self.cex_driver.symbol = symbol_full
        exchange = self.cex_driver
        if soft:
            soft_orders_to_focus = []
        if rap:
            unit_price = rate_price2order[rap]
        else:
            unit_price = rate_price2order[coin]  # 获取当前币种的单位价格比重
        # 获取当前市场价格

        price = exchange.get_price_now(coin)
        if price is None:
            self.monitor.record_operation("PlaceIncrementalOrders", self.strategy_detail,
                                          {"symbol": symbol_full, "error": "获取当前价格失败"})
            return
        base_order_money = price * unit_price
        # print(base_order_money, order_amount)
        if coin.find('-') != -1:
            print(coin)
            coin = coin[:coin.find('-')].lower()
        if self.min_amount_to_trade.get(coin, None) is None:
            print('出事了！！！快暂停！改代码！')
            return
        order_amount = round(usdt_amount / base_order_money, self.min_amount_to_trade[coin])
        if order_amount == 0:
            self.monitor.record_operation("PlaceIncrementalOrders", self.strategy_detail,
                                          {"symbol": symbol_full, "error": "订单金额过小，无法下单"})
            print('订单金额过小，无法下单')
            return
        order_id = 0
        if direction.lower() == 'buy':
            if not soft:
                if order_amount > 0:
                    order_id, _ = self._unified_place_order(symbol_full, 'buy', 'MARKET', round(order_amount, 2))
            else:
                if order_amount > 0:
                    limit_price = align_decimal_places(price, price * 0.9999)
                    order_id, _ = self._unified_place_order(symbol_full, 'buy', 'limit', round(order_amount, 2), limit_price)
                    if order_id:
                        soft_orders_to_focus.append(order_id)

            print(f"\r**BUY** order for {order_amount if order_id else 0} units of 【{coin.upper()}】 at price {price}",
                  end=' -> ')
            self.monitor.record_operation("PlaceIncrementalOrders", self.strategy_detail, {
                "symbol": symbol_full, "action": "buy", "price": price, "sizes": [order_amount if order_id else 0]
            })
        elif direction.lower() == 'sell':
            if not soft:
                if order_amount > 0:
                    order_id, _ = self._unified_place_order(symbol_full, 'sell', 'MARKET', round(order_amount, 2))
            else:
                if order_amount > 0:
                    limit_price = align_decimal_places(price, price * 1.0001)
                    order_id, _ = self._unified_place_order(symbol_full, 'sell', 'limit', round(order_amount, 2), limit_price)
                    if order_id:
                        soft_orders_to_focus.append(order_id)
            print(
                f"\r **SELL**  order for {order_amount if order_id else 0} units of 【{coin.upper()}】 at price {price}",
                end=' -> ')
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
    engine = OkexExecutionEngine(account=account, exchange_type=exchange_type)
    
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
            okx_engine = OkexExecutionEngine(account=0, exchange_type='okx')
            print("✓ OKX ExecutionEngine创建成功")
            print(f"交易所类型: {okx_engine.exchange_type}")
            print(f"账户ID: {okx_engine.account}")
        except Exception as e:
            print(f"✗ OKX ExecutionEngine创建失败: {e}")
        
        # 测试Backpack ExecutionEngine
        print("\n2.2 测试Backpack ExecutionEngine:")
        try:
            bp_engine = OkexExecutionEngine(account=0, exchange_type='backpack')
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