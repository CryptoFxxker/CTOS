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
from ctos.drivers.okx.Config import ACCESS_KEY, SECRET_KEY, PASSPHRASE
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

    def fetch_position(self, symbol='ETH-USDT-SWAP', show=True):
        """
        获取并记录给定货币的余额。
        """
        try:
            if symbol.find('-') == -1:
                symbol = f'{symbol.upper()}-USDT-SWAP'
            self.okex_spot.symbol = symbol
            response = self.okex_spot.get_position()[0]
            # 如果API返回的代码不是'0'，记录错误消息
            if response['code'] == '0' and response['data']:  # 确保响应代码为'0'且有数据
                data = response['data'][0]
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
                # 记录持仓信息
                if show:
                    print(f"成功获取持仓信息：{position_info}")
                    self.logger.info(f"成功获取持仓信息：{position_info}")
                return position_info
            else:
                # Optionally return the data for further processing
                self.logger.error(f"获取仓位失败，错误信息：{response['msg']}")
                return None
        except Exception as e:
            # 捕捉并记录任何其他异常
            self.logger.error(f"获取仓位时发生异常：{str(e)}")
            return None

    def fetch_balance(self, currency, show=False):
        """
        获取并记录给定货币的余额。
        """
        try:
            response = self.okex_spot.get_asset(currency)[0]
            if response['code'] == '0':  # 假设'0'是成功的响应代码
                data = response['data'][0]
                for i in range(len(currency.split(','))):
                    available_balance = data['details'][i]['availBal']
                    equity = data['details'][i]['eq']
                    frozenBal = data['details'][i]['frozenBal']
                    notionalLever = data['details'][i]['notionalLever']
                    total_equity = data['totalEq']
                    usd_equity = data['details'][i]['eqUsd']

                    # 日志记录成功获取的余额信息
                    if show:
                        self.logger.info(
                            f"成功获取{currency}的余额：可用余额 {available_balance}, 冻结余额：{frozenBal}, 杠杆率:{notionalLever}, 总权益 {total_equity} USD, 账户总资产折合 {usd_equity} USD")
                        print(
                            f"成功获取{currency}的余额：可用余额 {available_balance}, 冻结余额：{frozenBal}, 杠杆率:{notionalLever}, 总权益 {total_equity} USD, 账户总资产折合 {usd_equity} USD")
                    # 返回解析后的数据
                    return {
                        'available_balance': available_balance,
                        'equity': equity,
                        'total_equity_usd': usd_equity
                    }
            else:
                # 如果API返回的代码不是'0'，记录错误消息
                self.logger.error(f"获取{currency}余额失败，错误信息：{response['msg']}")
                return None
        except Exception as e:
            # 捕捉并记录任何其他异常
            self.logger.error(f"获取{currency}余额时发生异常：{str(e)}")
            return None


    def fetch_and_growth(self):
        # 获取当前的总余额
        pos = self.fetch_balance('USDT', show=False)
        current_balance = float(pos['total_equity_usd'])
        # 计算与上一次比较的增长率
        if self.previous_balance > 0:
            growth_rate = (current_balance - self.previous_balance) / self.previous_balance
        else:
            growth_rate = 0
        return growth_rate, current_balance

    def monitor_balance(self, earn_balance=None, loss_balance=None, price_watch=[]):
        self.check_interval = 10  # seconds
        self.growth_threshold = 0.01  # 1%
        self.single_growth_threshold = 0.10  # 10%
        self.growth_count = 0
        self.previous_balance = float(self.fetch_balance('USDT', show=False)['total_equity_usd'])
        count = 0
        op = {'ETH': {'px': 0, 'sz': 0, 'pn': 0}, 'BTC': {'px': 0, 'sz': 0, 'pn': 0}}
        while True:
            time.sleep(self.check_interval)
            growth_rate, current_balance = self.fetch_and_growth()
            # print(f"Current balance growth rate: {growth_rate:.2%}")
            # 检查是否连续10次增长超过1%
            if growth_rate > self.growth_threshold:
                self.growth_count += 1
            else:
                self.growth_count = 0
            # 检查单次增长是否超过10%
            if ((
                        growth_rate > self.single_growth_threshold or self.growth_count >= 10) and current_balance > self.init_balance) \
                    or (earn_balance and current_balance > earn_balance) or (
                    loss_balance and current_balance <= loss_balance):
                print("Growth threshold exceeded. Executing stop loss.")
                self.soft_stop()
                break  # 停止监控
            else:
                if count % 10 == 0:
                    coins = ['eth', 'btc']
                    for coin in coins:
                        try:
                            position_info = self.fetch_position(f'{coin.upper()}-USDT-SWAP', show=False)
                            # print(position_info, '\n\n')
                            if position_info:
                                avg_px = float(position_info['开仓平均价'])
                                avg_sz = float(position_info['持仓数量'])
                                if coin == 'eth':
                                    op['ETH']['px'] = round(avg_px, 1)
                                    op['ETH']['sz'] = round(avg_px * avg_sz / 10, 1)
                                else:
                                    op['BTC']['px'] = round(avg_px, 1)
                                    op['BTC']['sz'] = round(avg_px * avg_sz / 100, 1)
                        except Exception as e:
                            print(e)

                output = f'Balance：{round(self.previous_balance, 1)}， ' + f'-> {round(current_balance, 1)}'
                if earn_balance:
                    output += f', {round(earn_balance - current_balance, 1)} -> {earn_balance} '
                if loss_balance:
                    output += f', {round(current_balance - loss_balance, 1)} -> {loss_balance} '
                for okx_exchange in price_watch:
                    coin_name = okx_exchange.symbol
                    # print(okx_exchange, coin_name)
                    px = op[coin_name[:3]]["px"]
                    sz = op[coin_name[:3]]["sz"]
                    px_now = okx_exchange.get_price_now()
                    op[coin_name[:3]]["pn"] = px_now
                    output += f' {coin_name[:3]}:' + f' {round(px_now, 1)} ' + f'- {px} ({round((px_now - px) / px * 100, 2)}%)' + f'({sz}) '

                print('\r{} {}'.format(output, round(op['ETH']['pn'] / op['BTC']['pn'], 6)), end='')
            self.previous_balance = current_balance
            count += 1

    def trigger_stop_loss(self, symbols=['eth']):
        # 执行止损操作
        position_finish_info_epoch = {}
        best_coin_rate = 0
        best_coin = 'btc'
        for coin in symbols:
            try:
                position_info = self.fetch_position(f'{coin.upper()}-USDT-SWAP', show=False)
                if position_info:
                    avg_px = float(position_info['开仓平均价'])
                    liq_px = float(position_info['预估强平价'])
                    mark_px = float(position_info['最新标记价格'])
                    pos_qty = float(position_info['持仓数量'])
                    pos_side = position_info['持仓方向']
                    profile_now = float(position_info['未实现收益'])
                    unit_price = rate_price2order[coin]  # 获取当前币种的单位价格比重
                    base_order_money = unit_price * mark_px
                    open_position = pos_qty * base_order_money
                    profile_rate = profile_now / abs(open_position)
                    position_info['每张价值'] = base_order_money
                    position_info['本次开仓价值'] = open_position
                    position_info['本次开仓收益率'] = profile_rate
                    position_finish_info_epoch[coin] = position_info
                    if pos_qty < 0 and profile_rate <= 0:
                        if abs(profile_rate) > best_coin_rate:
                            best_coin_rate = abs(profile_rate)
                            best_coin = coin
                    if pos_qty > 0 and profile_rate >= 0:
                        if profile_rate > best_coin_rate:
                            best_coin_rate = abs(profile_rate)
                            best_coin = coin
                    if pos_qty > 0:
                        order_price = mark_px - 2.88 if mark_px > 10000 else mark_px - 0.68
                        order_response, _ = self.okex_spot.sell(order_price, abs(pos_qty), 'MARKET', 'cross')
                    else:
                        order_price = mark_px - 2.88 if mark_px > 10000 else mark_px - 0.68
                        order_response, _ = self.okex_spot.buy(order_price, abs(pos_qty), 'MARKET', 'cross')
                    print(order_response)
            except Exception as e:
                print(coin, e)
                continue

        with open(f'trade_log_okex/tradePostionRecord-{BeijingTime()}.txt', 'w', encoding='utf8') as f:
            string = json.dumps(position_finish_info_epoch, indent=4)
            f.write(string)
        return best_coin

    def soft_stop(self, coins=list(rate_price2order.keys())):
        for coin in coins:
            position_info = self.fetch_position(f'{coin.upper()}-USDT-SWAP')
            print(position_info, '\n\n')
            if position_info:
                try:
                    avg_px = float(position_info['开仓平均价'])
                    mark_px = float(position_info['最新标记价格'])
                    pos_qty = float(position_info['持仓数量'])
                    liq_px = float(position_info['预估强平价'])
                    pos_side = position_info['持仓方向']
                except Exception as e:
                    print(e)
                if pos_qty > 0:
                    order_price = align_decimal_places(mark_px, mark_px * 1.00025)
                    order_response, _ = self.okex_spot.sell(order_price, abs(pos_qty), 'limit', 'cross')
                else:
                    order_price = align_decimal_places(mark_px, mark_px * 0.99975)
                    order_response, _ = self.okex_spot.buy(order_price, abs(pos_qty), 'limit', 'cross')
                print(order_response)

    def soft_stop_fast(self, coins=list(rate_price2order.keys())):
        batch_size = 10
        epoch = len(coins) // batch_size + 1
        for i in range(epoch):
            if len(coins) // batch_size == len(coins) / batch_size and epoch == len(coins) // batch_size:
                pass
            else:
                if epoch == len(coins) // batch_size:
                    position_infos = self.okex_spot.get_position(','.join(coins[i * 10:]))[0]['data']
                else:
                    position_infos = self.okex_spot.get_position(','.join(coins[i * 10: i * 10 + 10]))[0]['data']
            for data in position_infos:
                try:
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
                    if position_info:
                        avg_px = float(position_info['开仓平均价'])
                        mark_px = float(position_info['最新标记价格'])
                        pos_qty = float(position_info['持仓数量'])
                        pos_side = position_info['持仓方向']
                        coin = position_info['产品ID']
                except Exception as e:
                    print(e, '木有这个仓')
                    continue
                if pos_qty > 0:
                    order_price = align_decimal_places(mark_px, mark_px * 1.0001)
                    self.okex_spot.symbol = coin
                    order_response, _ = self.okex_spot.sell(order_price, abs(pos_qty), 'limit' if coin.lower().find(
                        'xaut') == -1 or coin.lower().find('trx') == -1 else 'MARKET', 'cross')
                else:
                    order_price = align_decimal_places(mark_px, mark_px * 0.9999)
                    self.okex_spot.symbol = coin
                    order_response, _ = self.okex_spot.buy(order_price, abs(pos_qty), 'limit' if coin.lower().find(
                        'xaut') == -1 or coin.lower().find('trx') == -1 else 'MARKET', 'cross')
                print(order_response)

    def soft_start(self, coins=list(rate_price2order.keys()), type='short', sz=2000):
        for coin in coins:
            self.okex_spot.symbol = (f'{coin.upper()}-USDT-SWAP')
            mark_px = self.okex_spot.get_price_now()
            if coin == 'eth':
                pos_qty = round(sz / mark_px * 10, 1)
                if type == 'long':
                    order_price = align_decimal_places(mark_px, mark_px * 0.99975)
                    order_response, _ = self.okex_spot.buy(order_price, abs(pos_qty), 'limit', 'cross')
                else:
                    order_price = align_decimal_places(mark_px, mark_px * 1.00025)
                    order_response, _ = self.okex_spot.sell(order_price, abs(pos_qty), 'limit', 'cross')
            elif coin == 'btc':
                pos_qty = round(sz / mark_px * 100, 1)

                if type == 'long':
                    order_price = mark_px + 1.88 if mark_px > 10000 else mark_px + 0.28
                    order_response, _ = self.okex_spot.sell(order_price, abs(pos_qty), 'limit', 'cross')
                else:
                    order_price = mark_px - 1.88 if mark_px > 10000 else mark_px - 0.28
                    order_response, _ = self.okex_spot.buy(order_price, abs(pos_qty), 'limit', 'cross')
            print(order_response)


    def set_coin_position_to_target(self, usdt_amounts=[10], coins=['eth'], soft=False):
        start_time = time.time()
        batch_size = 10
        epoch = len(coins) // batch_size + 1
        all_pos_info = {}
        for i in range(epoch):
            if len(coins) // batch_size == len(coins) / batch_size and epoch == len(coins) // batch_size:
                pass
            else:
                if epoch == len(coins) // batch_size:
                    position_infos = self.okex_spot.get_position(','.join(coins[i * 10:]))[0]['data']
                else:
                    position_infos = self.okex_spot.get_position(','.join(coins[i * 10: i * 10 + 10]))[0]['data']
            for x in position_infos:
                if float(x['pos']) != 0:
                    all_pos_info[x['instId']] = x
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


def define_self_operate():
    good_top10_coins = ['btc', 'bnb', 'trx', 'ton', 'eth', 'shib']
    for coin in good_top10_coins:
        if coin == 'btc':
            pass
        else:
            engine.place_incremental_orders(100, coin, 'sell')
    bad_top10_coins = ['btc', 'gala', 'sui', 'hbar', 'om', 'ada']
    for i in bad_top10_coins:
        if coin == 'btc':
            pass
        else:
            engine.place_incremental_orders(100, coin, 'buy')


def minize_money_to_buy():
    for coin in rate_price2order.keys():
        x = init_OkxClient(coin)
        for amount in [0.01, 0.05, 0.1, 0.5, 1]:
            now_prince = x.get_price_now()
            success, _ = x.buy(now_prince * 0.98, amount)
            time.sleep(0.1)
            if success:
                print(f'【 {coin} 】这个币，最小的买入单位是：{amount}, 需要花费 {amount * now_prince * rate_price2order[coin]} ')
                break


if __name__ == '__main__':
    # Example usage
    engine = OkexExecutionEngine()
    engine.okex_spot.symbol = 'ETH-USDT-SWAP'
    # Example to fetch balance
    # balance = engine.fetch_balance('BTC')
    # print(f"Balance for BTC: {balance}")

    # Example to place an order
    # print(f"Order Response: {order_response}")

    # from ExecutionEngine import *
    # engine = OkexExecutionEngine()
    # engine.fetch_balance('ETH')
    # now_money = float(engine.fetch_balance('USDT')['total_equity_usd'])
    exit()
    just_kill_position = False
    reset_start_money = 748
    win_times = 0
    good_group = ['btc', 'doge']
    stop_rate = 1.025
    add_position_rate = 0.975
    is_win = True
    leverage_times = 1.5
    print('来咯来咯！开始赚钱咯！')
    while True:
        stop_rate = 1.025
        add_position_rate = 0.988
        try:
            if just_kill_position:
                start_money = reset_start_money
            elif is_win:
                start_money = float(
                    engine.fetch_balance('USDT')['total_equity_usd'])  ##  * (1 - win_times * 1.88/100)
                # worst_performance_coins, best_performance_coins = get_good_bad_coin_group(5)
            else:
                start_money = float(engine.fetch_balance('USDT')['total_equity_usd'])
                # worst_performance_coins, best_performance_coins = get_good_bad_coin_group(5)
            start_time = time.time()
            init_operate_position = start_money * leverage_times
            target_money = start_money
            if (not just_kill_position) and is_win:
                usdt_amounts = []
                coins_to_deal = []
                for coin in rate_price2order.keys():
                    time.sleep(0.1)
                    if coin in good_group:
                        buy_amount = cal_amount(coin, init_operate_position, good_group)
                        usdt_amounts.append(buy_amount)
                        coins_to_deal.append(coin)
                    else:
                        sell_amount = init_operate_position / (len(rate_price2order) - len(good_group))
                        usdt_amounts.append(-sell_amount)
                        coins_to_deal.append(coin)
                        # if coin in worst_performance_coins:
                        #     place_incremental_orders((init_operate_position / (len(rate_price2order) - len(good_group))), coin, 'sell')
                        # elif coin in best_performance_coins:
                        #     place_incremental_orders(round(init_operate_position / (len(rate_price2order) - len(good_group))), coin, 'sell')
                        # elif coin not in best_performance_coins and coin not in worst_performance_coins:
                        #     place_incremental_orders(round( init_operate_position / (len(rate_price2order) - len(good_group))), coin, 'sell')
                engine.set_coin_position_to_target(usdt_amounts, coins_to_deal)
                is_win = False
            count = 0
            while True:
                try:
                    time.sleep(3)
                    now_money = float(engine.fetch_balance('USDT')['total_equity_usd'])
                    if count > 0 and count % 300 == 0 and not just_kill_position:
                        if now_money < target_money * add_position_rate and now_money > start_money * 0.6:
                            for coin in rate_price2order.keys():
                                time.sleep(0.1)
                                if coin in good_group:
                                    buy_amount = cal_amount(coin, 300, good_group)
                                    engine.place_incremental_orders(buy_amount, coin, 'buy')
                                else:
                                    # if coin in worst_performance_coins:
                                    #     place_incremental_orders(round(300 / (len(rate_price2order) - len(good_group))), coin, 'sell')
                                    # elif coin in best_performance_coins:
                                    #     place_incremental_orders(round(300 / (len(rate_price2order) - len(good_group))), coin, 'sell')
                                    # elif coin not in best_performance_coins and coin not in worst_performance_coins:
                                    #     place_incremental_orders(round(300 / (len(rate_price2order) - len(good_group))), coin, 'sell')
                                    engine.place_incremental_orders(
                                        round(300 / (len(rate_price2order) - len(good_group))), coin, 'sell')
                            target_money = target_money * add_position_rate
                            stop_rate += 0.0025
                            add_position_rate -= 0.005
                    count += 5
                    if now_money > start_money * stop_rate:
                        is_win = True
                        win_times += 1
                        just_kill_position = False
                        break
                    else:
                        low_target = target_money * add_position_rate
                        low1 = now_money if now_money < start_money else start_money
                        high1 = now_money if now_money >= start_money else start_money
                        high_target = start_money * stop_rate
                        step_unit = (high_target - low_target) / 100
                        if now_money < start_money:
                            icon = '='
                        else:
                            icon = '>'
                        print(
                            f"\r[{low_target} |{'=' * round((low1 - low_target) // step_unit)} {round(low1, 1)} | {icon * round((high1 - low1) // step_unit)}  {round(high1, 1)} | {'>' * round((high_target - high1) // step_unit)} {round(start_money * stop_rate, 1)} Time Usgae: {round(time.time() - start_time)}--------",
                            end='')
                except Exception as e:
                    print('aha? 垃圾api啊\n')
        except Exception as e:
            print(e)
            time.sleep(1800)
        for i in range(1800):
            time.sleep(1)
            print(f'\r 刚搞完一单，休息会，{i}/1800', end='')