import sys
import os

from pathlib import Path
# Ensure project root (which contains the `ctos/` package directory) is on sys.path
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parents[1]  # repo root containing the top-level `ctos/` package dir
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ctos', 'drivers', 'okx'))
import logging
from ctos.drivers.okx.driver import OkxDriver, init_OkxClient
from ctos.drivers.okx.util import BeijingTime, align_decimal_places, save_para, rate_price2order, cal_amount, get_min_amount_to_trade
import time
# from average_method import get_good_bad_coin_group  # 暂时注释掉，文件不存在
import json
from .SystemMonitor import SystemMonitor
import threading


class OkexExecutionEngine:
    def __init__(self, account=0, strategy='Classical', strategy_detail="StrategyAdjustment", symbol='eth'):
        """
        Initialize the execution engine with API credentials and setup logging.
        """
        self.account = account
        self.okex_spot =  OkxDriver()
        self.strategy_detail = strategy_detail
        self.monitor = SystemMonitor(self, strategy)
        self.logger = self.monitor.logger
        # self.setup_logger()
        self.init_balance = float(self.okex_spot.fetch_balance('USDT'))
        self.watch_threads = []  # 存储所有监控线程
        self.soft_orders_to_focus = []
        self.min_amount_to_trade = get_min_amount_to_trade(
            init_OkxClient, 
            path=os.path.join(_PROJECT_ROOT, 'apps', 'strategies', 'hedge', 'trade_log_okex', 'min_amount_to_trade.json')
        )

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
        batch_size = 10
        epoch = len(coins) // batch_size + 1
        position_infos = self.okex_spot.get_position(keep_origin=False)
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
                                                              "order_price": self.okex_spot.get_price_now(symbol_full),
                                                              "amount": usdt_amount
                                                          })
                        else:
                            self.place_incremental_orders(abs(usdt_amount), coin, 'buy', soft=soft if coin.lower().find(
                                'xaut') == -1 or coin.lower().find('trx') == -1 else False)
                            self.monitor.record_operation("SetCoinPosition KaiCang",
                                                          self.strategy_detail + "not position_info",
                                                          {
                                                              "symbol": symbol_full, "action": "buy",
                                                              "order_price": self.okex_spot.get_price_now(symbol_full),
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
                                                          "order_price": self.okex_spot.get_price_now(symbol_full),
                                                          "amount": usdt_amount
                                                      })
                    else:
                        self.place_incremental_orders(abs(usdt_amount), coin, 'buy',
                                                      soft=soft if coin.lower().find('xaut') == -1 or coin.lower().find(
                                                          'trx') == -1 else False)
                        self.monitor.record_operation("SetCoinPosition BaoCuoChuli",
                                                      self.strategy_detail + "ExceptionFallback", {
                                                          "symbol": symbol_full, "action": "buy",
                                                          "order_price": self.okex_spot.get_price_now(symbol_full),
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
        exchange = self.okex_spot
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
        self.okex_spot.symbol = symbol_full
        exchange = self.okex_spot
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
                    order_id, _ = exchange.buy(price, round(order_amount, 2), 'MARKET')
            else:
                if order_amount > 0:
                    order_id, _ = exchange.buy(align_decimal_places(price, price * 0.9999), round(order_amount, 2))
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
                    order_id, _ = exchange.sell(price, round(order_amount, 2), 'MARKET')
            else:
                if order_amount > 0:
                    order_id, _ = exchange.sell(align_decimal_places(price, price * 1.0001), round(order_amount, 2))
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


def init_all_thing():
    engine = OkexExecutionEngine()
    eth = init_OkxClient('eth', engine.account)
    btc = init_OkxClient('btc', engine.account)
    return engine, eth, btc



if __name__ == '__main__':
    # Example usage
    engine = OkexExecutionEngine()
    engine.okex_spot.symbol = 'ETH-USDT-SWAP'
    engine.okex_spot.get_price_now()
    exit()