import datetime
import hashlib
import math
import os
import sys
import time
from urllib.parse import urljoin
import pandas as pd
import json
import requests

import hmac
import base64
import random
from util import *


from Config import ACCESS_KEY, SECRET_KEY, PASSPHRASE, HOST_IP, HOST_USER, HOST_PASSWD, HOST_IP_1


class OkexSpot:
    """OKEX Spot REST API client."""

    def __init__(self, symbol, access_key, secret_key, passphrase, host=None):
        self.symbol = symbol
        self._host = host or "https://www.okx.com"
        self._access_key = access_key
        self._secret_key = secret_key
        self._passphrase = passphrase
        self.account_type = 'MAIN'

    def request(self, method, uri, params=None, body=None, headers=None, auth=False):
        """Initiate network request
        ******* From :https://zhuanlan.zhihu.com/p/369770611 *******
       @param method: request method, GET / POST / DELETE / PUT
       @param uri: request uri
       @param params: dict, request query params
       @param body: dict, request body
       @param headers: request http header
       @param auth: boolean, add permission verification or not
       """
        if params:
            query = "&".join(
                ["{}={}".format(k, params[k]) for k in sorted(params.keys())]
            )
            uri += "?" + query
        url = urljoin(self._host, uri)

        if auth:
            timestamp = (
                    str(time.time()).split(".")[0]
                    + "."
                    + str(time.time()).split(".")[1][:3]
            )
            if body:
                body = json.dumps(body)
            else:
                body = ""
            message = str(timestamp) + str.upper(method) + uri + str(body)
            mac = hmac.new(
                bytes(self._secret_key, encoding="utf8"),
                bytes(message, encoding="utf-8"),
                digestmod="sha256",
            )
            d = mac.digest()
            sign = base64.b64encode(d)

            if not headers:
                headers = {}
            headers["Content-Type"] = "application/json"
            headers["OK-ACCESS-KEY"] = self._access_key
            headers["OK-ACCESS-SIGN"] = sign
            headers["OK-ACCESS-TIMESTAMP"] = str(timestamp)
            headers["OK-ACCESS-PASSPHRASE"] = self._passphrase
        result = requests.request(
            method, url, data=body, headers=headers, timeout=10
        ).json()
        if result.get("code") and result.get("code") != "0":
            return None, result
        return result, None

    def get_exchange_info(self, instType='SPOT'):
        """Obtain trading rules and trading pair information."""
        uri = "/api/v5/public/instruments"
        if self.symbol.find('SWAP') != -1:
            instType = 'SWAP'
        if self.symbol == 'ETH-BTC':
            instType = 'MARGIN'
        params = {"instType": instType, "instId": self.symbol}
        success, error = self.request(method="GET", uri=uri, params=params)
        return success, error

    def set_symbol(self, symbol):
        if len(symbol) == 0:
            return
        else:
            self.symbol = symbol

    def get_orderbook(self, sz=5):
        """
       Get orderbook data.
       *  asks Array 卖方深度
       *  bids Array 买方深度
       *  ts String  深度产生的时间
       *  asks和bids值数组举例说明：
             ["411.8","10", "1","4"]
                 411.8为深度价格，
                 10为此价格的合约张数，
                 1为此价格的强平单数量，
                 4为此价格的订单数量
       """
        uri = "/api/v5/market/books"
        params = {"instId": self.symbol, "sz": sz}
        success, error = self.request(method="GET", uri=uri, params=params)
        return success, error

    def get_trade(self, symbol):
        """
       Get trade data.
       """
        if symbol.find('-') == -1:
            symbol = f'{symbol.upper()}-USDT-SWAP'
        uri = "/api/v5/market/trades"
        params = {"instId": symbol, "limit": 1}
        success, error = self.request(method="GET", uri=uri, params=params)
        return success, error

    def vol_24h(self):
        """
       Get 24h_vol data.
       """
        uri = "/api/v5/market/platform-24-volume"
        params = {}
        success, error = self.request(method="GET", uri=uri, params=params)
        return success, error

    def get_price_now(self, symbol=None):
        """
         * 获取当前的价格
        """
        trade, error = self.get_trade(symbol if symbol else self.symbol)
        if error:
            print("Get trade error:", error)
            return
        else:
            return float(trade['data'][0]['px'])

    def get_kline(self, interval, limit=400, symbol='ETH-USDT'):
        """
       Get kline data.
       :param interval: kline period.
       """
        if symbol.find('-') == -1:
            symbol = f'{symbol.upper()}-USDT-SWAP'
        if str(interval).endswith("h") or str(interval).endswith("d"):
            interval = str(interval).upper()
        uri = "/api/v5/market/candles"
        params = {"instId": symbol, "bar": interval, "limit": limit}
        success, error = self.request(method="GET", uri=uri, params=params)
        data_ = [x[:5] + x[6:8] for x in success['data']]
        return pd.DataFrame(data=data_, columns=['trade_date', 'open', 'high', 'low', 'close', 'vol1', 'vol']), error

    def get_kline_origin(self, interval, limit=400, symbol='ETH-USDT'):
        """
       Get kline data.
       :param interval: kline period.
       """
        if symbol.find('-') == -1:
            symbol = f'{symbol.upper()}-USDT-SWAP'
        if str(interval).endswith("h") or str(interval).endswith("d"):
            interval = str(interval).upper()
        uri = "/api/v5/market/candles"
        params = {"instId": symbol, "bar": interval, "limit": limit}
        success, error = self.request(method="GET", uri=uri, params=params)
        return success['data'], error

    def get_zijin_asset(self, currency='USDT'):
        """
       Get account asset data.
       :param currency: e.g. "USDT", "BTC"
       """
        params = {"ccy": currency}
        result = self.request(
            "GET", "/api/v5/asset/balances", params=params, auth=True
        )
        # print(result)
        if result[0]['code'] == '0':  # 假设'0'是成功的响应代码
            data = result[0]['data'][0]
            return float(data['availBal'])
        else:
            print(result[0]['msg'])
            return None

    def get_jiaoyi_asset(self, currency='USDT'):
        """
       Get account asset data.
       :param currency: e.g. "USDT", "BTC"
       """
        """
        获取并记录给定货币的余额。
        """
        try:
            response = self.get_asset(currency)[0]
            if response['code'] == '0':  # 假设'0'是成功的响应代码
                data = response['data'][0]
                for i in range(len(currency.split(','))):
                    available_balance = data['details'][i]['availBal']
                    equity = data['details'][i]['eq']
                    frozenBal = data['details'][i]['frozenBal']
                    notionalLever = data['details'][i]['notionalLever']
                    total_equity = data['totalEq']
                    usd_equity = data['details'][i]['eqUsd']
                    return float(available_balance)
            else:
                # 如果API返回的代码不是'0'，记录错误消息
                return None
        except Exception as e:
            # 捕捉并记录任何其他异常
            return None

    def fetch_balance(self, currency='USDT'):
        """
        获取并记录给定货币的余额。
        """
        try:
            response = self.get_asset(currency)[0]
            if response['code'] == '0':  # 假设'0'是成功的响应代码
                data = response['data'][0]
                for i in range(len(currency.split(','))):
                    available_balance = data['details'][i]['availBal']
                    equity = data['details'][i]['eq']
                    frozenBal = data['details'][i]['frozenBal']
                    notionalLever = data['details'][i]['notionalLever']
                    total_equity = data['totalEq']
                    usd_equity = data['details'][i]['eqUsd']
                    return float(usd_equity)
            else:
                # 如果API返回的代码不是'0'，记录错误消息
                return None
        except Exception as e:
            # 捕捉并记录任何其他异常
            return None

    def get_asset(self, currency='USDT'):
        """
       Get account asset data.
       :param currency: e.g. "USDT", "BTC"
       """
        params = {"ccy": currency}
        result = self.request(
            "GET", "/api/v5/account/balance", params=params, auth=True
        )
        return result

    def get_posistion(self, symbol=None):
        if not symbol:
            params = {"instId": self.symbol}
        else:
            if symbol.find(',') != -1:
                symbolList = [x if x.find('-') != -1 else f'{x.upper()}-USDT-SWAP' for x in symbol.split(',')]
            else:
                if symbol.find('USDT') == -1:
                    symbolList = [f'{symbol.upper()}-USDT-SWAP']
                else:
                    symbolList = [symbol.upper()]
            params = {"instId": ','.join(symbolList)}
        result = self.request(
            "GET", "/api/v5/account/positions", params=params, auth=True
        )
        return result

    def get_order_status(self, order_no):
        """Get order status.
       @param order_no: order id.
       """
        uri = "/api/v5/trade/order"
        params = {"instId": self.symbol, "ordId": order_no}
        success, error = self.request(method="GET", uri=uri, params=params, auth=True)
        return success, error

    def buy(self, price, quantity, order_type='limit', tdMode='cross'):
        """
       Open buy order.
       :param price:order price
       :param quantity:order quantity
       :param order_type:order type, "LIMIT" or "MARKET"
       :return:order id and None, otherwise None and error information
       """
        uri = "/api/v5/trade/order"
        if self.symbol.find('USDT') != -1:
            data = {"instId": self.symbol, "tdMode": tdMode, "side": "buy", "ccy": 'USDT'}
        else:
            data = {"instId": self.symbol, "tdMode": tdMode, "side": "buy"}
        if self.symbol.find('SWAP') != -1:
            quantity = quantity
        if self.symbol == 'ETH-BTC':
            data['ccy'] = 'ETH'
        if order_type.upper() == "POST_ONLY":
            data["ordType"] = "post_only"
            data["px"] = price
            data["sz"] = quantity
        elif order_type.upper() == "MARKET":
            data["ordType"] = "market"
            data["sz"] = quantity
        else:
            data["ordType"] = "limit"
            data["px"] = price
            data["sz"] = quantity
        success, error = self.request(method="POST", uri=uri, body=data, auth=True)
        if error:
            return None, error
        return success["data"][0]["ordId"], error

    def place_order(self, price, quantity, order_type='limit', tdMode='cross', side=None, symbol=None):
        """
       Open buy order.
       :param price:order price
       :param quantity:order quantity
       :param order_type:order type, "LIMIT" or "MARKET"
       :return:order id and None, otherwise None and error information
       """
        symbol = symbol if symbol else self.symbol
        uri = "/api/v5/trade/order"
        if symbol.find('USDT') != -1:
            data = {"instId": symbol, "tdMode": tdMode, "side": side if side else 'buy', "ccy": 'USDT'}
        else:
            data = {"instId": symbol, "tdMode": tdMode, "side": side if side else 'buy', }
        if symbol.find('SWAP') != -1:
            quantity = quantity
        if symbol == 'ETH-BTC':
            data['ccy'] = 'ETH'
        if order_type.upper() == "POST_ONLY":
            data["ordType"] = "post_only"
            data["px"] = price
            data["sz"] = quantity
        elif order_type.upper() == "MARKET":
            data["ordType"] = "market"
            data["sz"] = quantity
        else:
            data["ordType"] = "limit"
            data["px"] = price
            data["sz"] = quantity
        success, error = self.request(method="POST", uri=uri, body=data, auth=True)
        if error:
            return None, error
        return success["data"][0]["ordId"], error


    def sell(self, price, quantity, order_type='limit', tdMode='cross'):
        """
       Close sell order.
       :param price:order price
       :param quantity:order quantity
       :param order_type:order type, "LIMIT" or "MARKET"
       :return:order id and None, otherwise None and error information
       """
        uri = "/api/v5/trade/order"
        if self.symbol.find('USDT') != -1:
            data = {"instId": self.symbol, "tdMode": tdMode, "side": "sell", "ccy": 'USDT'}
        else:
            data = {"instId": self.symbol, "tdMode": tdMode, "side": "sell"}
        if self.symbol.find('SWAP') != -1:
            quantity = quantity
        if self.symbol == 'ETH-BTC':
            data['ccy'] = 'ETH'
        if order_type == "POST_ONLY":
            data["ordType"] = "post_only"
            data["px"] = price
            data["sz"] = quantity
        elif order_type == "MARKET":
            data["ordType"] = "market"
            data["sz"] = quantity
        else:
            data["ordType"] = "limit"
            data["px"] = price
            data["sz"] = quantity
        success, error = self.request(method="POST", uri=uri, body=data, auth=True)
        if error:
            return None, error
        return success["data"][0]["ordId"], error

    def revoke_order(self, order_no):
        """Cancel an order.
       @param order_no: order id
       """
        uri = "/api/v5/trade/cancel-order"
        data = {"instId": self.symbol, "ordId": order_no}
        _, error = self.request(method="POST", uri=uri, body=data, auth=True)
        if error:
            return order_no, error
        else:
            return order_no, None

    def transfer_money(self, usdt_amount, direction='z2j'):
        """
        资金划转函数：在资金账户和交易账户之间划转USDT。

        :param usdt_amount: float，划转金额
        :param direction: str，方向，可选：
                - "fund_to_trade"：资金账户 -> 交易账户
                - "trade_to_fund"：交易账户 -> 资金账户
        :return: 请求结果或错误信息
        """
        if self.account_type != 'MAIN':
            return None, '无操作权限！！'

        from_to_map = {
            "z2j": ("6", "18"),
            "j2z": ("18", "6")
        }

        if direction not in from_to_map:
            return None, "不支持的方向参数，必须为 'z2j' 或 'j2z'"

        from_id, to_id = from_to_map[direction]

        uri = "/api/v5/asset/transfer"
        data = {
            "ccy": "USDT",
            "amt": str(usdt_amount),
            "from": from_id,
            "to": to_id,
        }

        resp, error = self.request(method="POST", uri=uri, body=data, auth=True)

        if error:
            return None, f"划转失败: {error}"
        else:
            return resp, None

    def revoke_orders(self, order_nos):
        """
       Cancel mutilple orders by order ids.
       @param order_nos :order list
       """
        success, error = [], []
        for order_id in order_nos:
            _, e = self.revoke_order(order_id)
            if e:
                error.append((order_id, e))
            else:
                success.append(order_id)
        return success, error

    def get_open_orders(self, instType='SPOT', symbol='ETH-USDT-SWAP'):

        """Get all unfilled orders.
       * NOTE: up to 100 orders
       """
        symbol = self.symbol if not symbol else symbol
        if symbol == 'ETH-BTC':
            instType = 'MARGIN'
        uri = "/api/v5/trade/orders-pending"
        params = {"instType": instType, "instId": symbol}
        success, error = self.request(method="GET", uri=uri, params=params, auth=True)
        if error:
            return None, error
        else:
            order_ids = []
            if success.get("data"):
                for order_info in success["data"]:
                    order_ids.append(order_info["ordId"])
            return order_ids, None

    def amend_order(self, price=None, quantity=None, orderId=None):
        """
       Open buy order.
       :param price:order price
       :param quantity:order quantity
       :param order_type:order type, "LIMIT" or "MARKET"
       :return:order id and None, otherwise None and error information
       """
        uri = "/api/v5/trade/amend-order"
        data = {"instId": self.symbol, "ordId": orderId}
        if not price and not quantity:
            print('WTF想修改啥？')
            return
        if price:
            data["newPx"] = float(price)
        elif quantity:
            data["newSz"] = quantity
        success, error = self.request(method="POST", uri=uri, body=data, auth=True)
        if error:
            return None, error
        return success["data"][0]["ordId"], error

    def get_market(self, instId='', all=False, amountLimit=5000000, condition=None):
        """Get all unfilled orders.
       * NOTE: up to 100 orders
       """
        success = {'data': []}
        if all:
            uri = "/api/v5/market/tickers"
            for tp in ['SPOT', 'SWAP']:
                params = {"instType": tp}
                su, error = self.request(method="GET", uri=uri, params=params, auth=True)
                success['data'] += su['data']
        else:
            uri = "/api/v5/market/ticker"
            if instId == '':
                instId = self.symbol
            params = {"instId": instId}
            success, error = self.request(method="GET", uri=uri, params=params, auth=True)
        if error:
            return None, error
        else:
            ccy_datas = []
            if success.get("data"):
                for x in success["data"]:
                    if condition and x['instId'].find(condition) == -1:
                        continue
                    if (float(x['last']) * float(x['volCcy24h']) <= amountLimit):
                        continue
                    if (float(x['last']) - float(x['sodUtc8'])) / float(x['sodUtc8']) * 100 < 0:
                        continue
                    ccy_datas.append(x)
            return ccy_datas, None


def get_rates(account=0):
    _rates = {}
    try:
        _rates = json.load(open('_rates.txt', 'r'))
    except Exception as e:
        _rates = {
            # 'ETH-USD-SWAP': {'gap': 30, 'sell': 3, 'price_bit': 2, 'amount_base':3, 'change_base':3000, 'change_gap': 120, 'change_amount':1},
            'ETH-USDT-SWAP': {'gap': 12.88, 'sell': 6.66, 'price_bit': 2, 'amount_base': 0.1, 'change_base': 2700,
                              'change_gap': 88.88, 'change_amount': 0.01},
            'BTC-USDT-SWAP': {'gap': 288.88, 'sell': 6.66, 'price_bit': 1, 'amount_base': 0.01, 'change_base': 96000,
                              'change_gap': 8888.88, 'change_amount': 0.01},
            # 'SHIB-USDT-SWAP': {'gap': 0.0000002, 'sell': 10, 'price_bit': 8, 'amount_base':1, 'change_base':0.000026, 'change_gap': 0.000001, 'change_amount':1},
            # 'DOGE-USDT-SWAP': {'gap': 0.0025, 'sell': 2.5, 'price_bit': 5, 'amount_base':1, 'change_base':0.14, 'change_gap': 0.01, 'change_amount':1},
            # 'ETH-BTC': {'gap': 0.00008, 'sell': 10, 'price_bit': 5, 'amount_base':0.002, 'change_base':0.05150, 'change_gap': 0.0006, 'change_amount':0.001},
        }
        print("Load Rates Failed")
        with open('_rates.txt', 'w') as out:
            out.write(json.dumps(_rates, indent=4))
    # print(list(_rates.keys()))
    exchanges = [get_okexExchage(x[:x.find('-')].lower(), account, show=False) for x in list(_rates.keys())]
    update_rates(_rates)
    return exchanges, _rates


def update_rates(_rates):
    with open('_rates.txt', 'w') as out:
        out.write(json.dumps(_rates, indent=4))


def _grid_Okex(exchanges, init_rate_rates={'eth': {'buy': 1, 'sell': 3, 'price_bit': 2, 'amount_bit': 6},
                                           'doge': {'buy': 1, 'sell': 3, 'price_bit': 6, 'amount_bit': 4}}):
    codes = ['eth', 'doge']
    start = time.time()
    gaps = load_gaps()
    operate_prices = {symbol: load_trade_log_once(symbol)[symbol]['price'] for symbol in codes}
    count = 0
    buy_times = {symbol: get_order_times(symbol)['buy'] for symbol in codes}
    sell_times = {symbol: get_order_times(symbol)['sell'] for symbol in codes}
    buy_rates = load_rates('buy')
    sell_rates = load_rates('sell')
    # print(gaps)
    # print(buy_rates)
    # print(sell_rates)
    os.system('clear; tail -n 20 exist_okex.txt')
    start_display = time.time()
    code_display = 0
    while True:
        count += 1
        for symbol in codes:
            exchange = exchanges[symbol]
            init_rr = init_rate_rates[symbol]
            time.sleep(1)
            gap = gaps[symbol]
            operate_price = operate_prices[symbol]
            buy_rate = buy_rates[symbol]
            sell_rate = sell_rates[symbol]
            try:
                price_now = exchange.get_price_now()
                if count > 18000:
                    os.system('clear; tail -n 20 exist_okex.txt')
                    count = 0
                if count % 3600 == 0:
                    if sell_rate / buy_rate > (init_rr['sell'] / init_rr['buy'] * 1.67):
                        operate_prices[symbol] += (price_now - operate_prices[symbol]) * 0.005
                    elif sell_rate / buy_rate < (init_rr['sell'] / init_rr['buy'] * 0.67):
                        operate_prices[symbol] += (price_now - operate_prices[symbol]) * 0.005
                chars = ['*', '#', '&', '$', '~', '@']
                index_char = random.randint(0, 5)
                if time.time() - start_display > 6:
                    start_display = time.time()
                    code_display += 1
                    code_display = code_display % len(codes)
                if symbol == codes[code_display]:
                    print(
                        "\r【%s, BUY:%s, SELL:%s】 [TIME USAGE]/%s, [GAP]/%s, [B_R:%s, S_R:%s]  [B_P:%s, S_P:%s]  [DonePrice]/%s  [PRICE] %s %s %s" %
                        (symbol.upper(), buy_times[symbol], sell_times[symbol], round(time.time() - start),
                         round(gap, init_rr['price_bit']), round(buy_rate, 1),
                         round(sell_rate, 1),
                         round(operate_price - gap * round(buy_rate, 1), init_rr['price_bit'] - 2),
                         round(operate_price + gap * round(sell_rate, 1), init_rr['price_bit'] - 2),
                         operate_price,
                         chars[index_char] * 3, price_now, chars[index_char] * 3), end='')

                if price_now < operate_price - gap * round(buy_rate, 1):
                    sell_rates[symbol] /= 1.1
                    if sell_rates[symbol] < init_rr['sell']:
                        sell_rates[symbol] = init_rr['sell']
                    buy_rates[symbol] *= 1.05
                    save_rates_once(sell_rates, 'sell')
                    save_rates_once(buy_rates, 'buy')
                    buy_price = round(operate_price - gap, init_rr['price_bit'])
                    buy_amount = round(15 * (buy_rate / init_rr['buy'] * 1.5) / round((buy_price + price_now) / 2,
                                                                                      init_rr['price_bit']),
                                       init_rr['amount_bit'])
                    buy_money = round(buy_price * buy_amount, )
                    while buy_price * buy_amount < 10:
                        print("好像出了点问题，总价居然跑五美元下去了")
                        buy_amount *= 1.03
                        buy_money = round(buy_price * buy_amount, 2)
                    buy_amount = round(buy_amount, init_rr['amount_bit'])
                    x, _ = exchange.buy(price=None, quantity=buy_money, order_type="MARKET")
                    if not x:
                        print("买入出毛病了，快看")
                        break
                    save_trade_log_once(symbol,
                                        {symbol: {'price': buy_price, 'amount': buy_amount, 'buy_money': buy_money}})
                    operate_prices[symbol] = buy_price
                    time.sleep(0.5)
                    buy_times[symbol] += 1
                    os.system(
                        "echo '[BUY %s %s] Price  Now:%s, Amount:%s, Operate_price:%s, Money:%s, OrderID:%s' >> exist_okex.txt; clear; tail -n 20 exist_okex.txt" % (
                            symbol,
                            BeijingTime('%Y-%m-%dT%H:%M:%S'),
                            round(price_now, init_rr['price_bit']),
                            buy_amount, price_now, buy_money, x))

                if price_now > operate_price + gap * round(sell_rate, 1):
                    buy_rates[symbol] /= 1.05
                    if buy_rates[symbol] < init_rr['buy']:
                        buy_rates[symbol] = init_rr['buy']
                    sell_rates[symbol] *= 1.1
                    save_rates_once(sell_rates, 'sell')
                    save_rates_once(buy_rates, 'buy')
                    sell_price = round(operate_price + gap, init_rr['price_bit'])
                    sell_amount = round(15 * (sell_rate / init_rr['sell'] * 1.5) / round((sell_price + price_now) / 2,
                                                                                         init_rr['price_bit']),
                                        init_rr['amount_bit'])
                    while sell_price * sell_amount < 10:
                        print("好像出了点问题，总价居然跑五美元下去了")
                        sell_amount *= 1.02
                        sell_amount = round(sell_amount, init_rr['amount_bit'])
                    x, _ = exchange.sell(price=None, quantity=sell_amount, order_type="MARKET")
                    if not x:
                        print("%s卖出出毛病了，快看" % symbol)
                        break
                    save_trade_log_once(symbol.lower(), {symbol.lower(): {'price': sell_price, 'amount': sell_amount,
                                                                          'sell_money': round(sell_price * sell_amount,
                                                                                              2)}})
                    operate_prices[symbol] = sell_price
                    time.sleep(0.5)
                    sell_times[symbol] += 1
                    os.system(
                        "echo '[SELL %s %s] Price  Now:%s, Amount:%s, Operate_price:%s, Money:%s, OrderID:%s' >> exist_okex.txt; clear; tail -n 20 exist_okex.txt" % (
                            symbol,
                            BeijingTime('%Y-%m-%dT%H:%M:%S'),
                            round(price_now, init_rr['price_bit']),
                            sell_amount, price_now, round(sell_price * sell_amount, 2), x))
            except Exception as e:
                print('循环过程中的错误', e)
                break


def equal_rate_grid(exchanges, init_rate_rates={'eth': {'buy': 1, 'sell': 3, 'price_bit': 2, 'amount_bit': 6},
                                                'doge': {'buy': 1, 'sell': 3, 'price_bit': 6, 'amount_bit': 4}}):
    codes = ['eth', 'doge']
    start = time.time()
    operate_prices = {symbol: load_trade_log_once(symbol)[symbol]['price'] for symbol in codes}
    count = 0
    buy_times = {symbol: get_order_times(symbol)['buy'] for symbol in codes}
    sell_times = {symbol: get_order_times(symbol)['sell'] for symbol in codes}
    print(buy_times, sell_times)
    time.sleep(3)
    os.system('clear; tail -n 30 exist_okex.txt')
    start_display = time.time()
    code_display = 0
    open_orders = {s: {'buy': None, 'sell': None} for s in codes}
    buy_records = {s: '' for s in codes}
    sell_records = {s: '' for s in codes}
    gap = 2
    open_prices = {x: float(exchanges[x].get_market()[0][0].get('sodUtc8')) for x in codes}
    while True:
        count += 1
        for symbol in codes:
            exchange = exchanges[symbol]
            init_rr = init_rate_rates[symbol]
            time.sleep(gap)
            operate_price = operate_prices[symbol]
            open_order = open_orders[symbol]
            open_price = open_prices[symbol]
            if len(codes) > 1:
                # try:
                if count > 1200:
                    os.system('clear; tail -n 30 exist_okex.txt')
                    open_prices = {x: float(exchanges[x].get_market()[0][0]['sodUtc8']) for x in codes}
                    count = 0
                price_now = exchange.get_price_now()
                ticker_rate = round(100 * ((price_now - open_price) / open_price), 3)
                chars = ['*', '#', '&', '$', '~', '@']
                index_char = random.randint(0, 5)
                if time.time() - start_display > gap * 1.6:
                    start_display = time.time()
                    code_display += 1
                    code_display = code_display % len(codes)
                if symbol == codes[code_display]:
                    print(
                        "\r【%s, BUY:%s, SELL:%s】 [TIME USAGE]/%s, [GAP]/1,  [B_P:%s, S_P:%s]  [DonePrice]/%s  [PRICE] %s %s(%s) %s" %
                        (symbol.upper(), buy_times[symbol], sell_times[symbol], round(time.time() - start),
                         round(operate_price * 0.99, init_rr['price_bit'] - 2),
                         round(operate_price * 1.02, init_rr['price_bit'] - 2),
                         round(operate_price, init_rr['price_bit']),
                         chars[index_char] * 3, price_now, round(ticker_rate, 2), chars[index_char] * 3), end='')

                if (not open_order.get('buy')) and (not open_order.get('sell')):
                    size_rate = 1
                    if ticker_rate < 0:
                        size_rate += abs(ticker_rate / 20)

                    buy_price = round(operate_price * 0.99, init_rr['price_bit'])

                    buy_amount = round(
                        25 * size_rate * (1 + 0.5 * (buy_times[symbol] + 8) / (sell_times[symbol] + 8)) / buy_price,
                        init_rr['amount_bit'])
                    buy_money = round(buy_price * buy_amount, )
                    xb, _ = exchange.buy(price=buy_price, quantity=buy_amount, order_type="limit")
                    buy_records[
                        symbol] = "echo '[BUY %s %s] Price  Now:%s, Amount:%s, Operate_price:%s, Money:%s, OrderID:%s' >> exist_okex.txt; clear; tail -n 30 exist_okex.txt" % (
                        symbol,
                        BeijingTime('%Y-%m-%dT%H:%M:%S'),
                        round(price_now, init_rr['price_bit']),
                        buy_amount, buy_price, buy_money, xb)

                    size_rate = 1
                    if ticker_rate > 0:
                        size_rate += abs(ticker_rate / 20)

                    sell_price = round(operate_price * 1.02, init_rr['price_bit'])
                    sell_amount = round(
                        25 * size_rate * (1 + 0.5 * (sell_times[symbol] + 8) / (buy_times[symbol] + 8)) / sell_price,
                        init_rr['amount_bit'])
                    sell_money = round(sell_price * sell_amount, )
                    xs, _ = exchange.sell(price=sell_price, quantity=sell_amount, order_type="limit")
                    sell_records[
                        symbol] = "echo '[SELL %s %s] Price  Now:%s, Amount:%s, Operate_price:%s, Money:%s, OrderID:%s' >> exist_okex.txt; clear; tail -n 30 exist_okex.txt" % (
                        symbol,
                        BeijingTime('%Y-%m-%dT%H:%M:%S'),
                        round(price_now, init_rr['price_bit']),
                        sell_amount, sell_price, sell_money, xs)
                    gap = 0.5
                    if not xs or not xb:
                        print("买入出毛病了，快看")
                        return
                    open_orders[symbol]['buy'] = xb
                    open_orders[symbol]['sell'] = xs

                else:
                    buy_id = open_order['buy']
                    sell_id = open_order['sell']
                    try:
                        open_order_id, _ = exchange.get_open_orders()
                        while len(open_order_id) == 0:
                            open_order_id, _ = exchange.get_open_orders()
                    except TypeError as e:
                        print(e, symbol)
                        continue
                    if (buy_id not in open_order_id) and (sell_id in open_order_id):

                        save_trade_log_once(symbol.lower(),
                                            {symbol.lower(): {'price': operate_price * 0.99,
                                                              'amount': 20 / operate_price,
                                                              'sell_money': 20}})
                        operate_prices[symbol] = operate_price * 0.99
                        exchange.revoke_order(sell_id)
                        os.system(buy_records[symbol])
                        buy_times[symbol] += 1
                        open_orders[symbol] = {'buy': None, 'sell': None}

                    elif (sell_id not in open_order_id) and (buy_id in open_order_id):
                        save_trade_log_once(symbol.lower(),
                                            {symbol.lower(): {'price': operate_price * 1.01,
                                                              'amount': 20 / operate_price,
                                                              'sell_money': 20}})
                        operate_prices[symbol] = operate_price * 1.01
                        exchange.revoke_order(buy_id)
                        os.system(sell_records[symbol])
                        sell_times[symbol] += 1
                        open_orders[symbol] = {'buy': None, 'sell': None}

                    elif (sell_id not in open_order_id) and (buy_id not in open_order_id):
                        operate_prices[symbol] = price_now
                        buy_times[symbol] += 1
                        sell_times[symbol] += 1
                        open_orders[symbol] = {'buy': None, 'sell': None}
                    else:
                        gap = 2
                        continue


def get_today_utc8_change():
    keys = ['instId', 'last', 'lastSz', 'open24h', 'high24h', 'low24h', 'volCcy24h', 'vol24h', 'sodUtc0', 'sodUtc8']
    coin_data = {}
    coin_change = {}
    coin_pre = {}
    for x in exchange1.get_market(all=True)[0]:
        coin_data[x['instId']] = x
        coin_change[x['instId']] = round((float(x['last']) - float(x['sodUtc8'])) / float(x['sodUtc8']) * 100, 4)
    coin_change = sorted(coin_change.items(), key=lambda x: x[1], reverse=True)
    for i in coin_change:
        print(i[0], i[1])


def run_test():
    keys = ['instId', 'last', 'lastSz', 'open24h', 'high24h', 'low24h', 'volCcy24h', 'vol24h', 'sodUtc0', 'sodUtc8']
    coin_pres = []
    coin_szs = []
    coin_pre = {}
    coin_sz = {}
    for x in exchange1.get_market(all=True)[0]:
        coin_pre[x['instId']] = float(x['last'])
        coin_sz[x['instId']] = float(x['lastSz'])
    coin_pres.append(coin_pre)
    coin_szs.append(coin_sz)
    time.sleep(random.randint(10, 15))
    money = 100
    win_times = 0
    fail_times = 0
    while True:
        coin_change = {}
        shift = 3
        if len(coin_pres) < shift:
            coin_pre = coin_pres[-1]
            coin_sz = coin_szs[-1]
        else:
            coin_pre = coin_pres[-shift]
            coin_pres = coin_pres[-shift:]
            coin_sz = coin_szs[-shift]
            coin_szs = coin_szs[-shift:]

        coin_pre_tmp = {}
        coin_sz_tmp = {}
        for x in exchange1.get_market(all=True)[0]:
            try:
                if x['instId'] not in coin_pre.keys():
                    pass
                else:
                    coin_change[x['instId']] = round((float(x['last']) -
                                                      coin_pre[x['instId']])
                                                     / coin_pre[x['instId']] * 100 * (
                                                             float(x['lastSz']) / coin_sz[x['instId']]), 4)
            except Exception as e:
                print(coin_pre)
                print(coin_sz)
            coin_pre_tmp[x['instId']] = float(x['last'])
            coin_sz_tmp[x['instId']] = float(x['lastSz'])
        coin_change = sorted(coin_change.items(), key=lambda x: x[1], reverse=True)
        all_change = [v for k, v in coin_change]
        coin_pres.append(coin_pre_tmp)
        coin_szs.append(coin_sz_tmp)
        # if sum(all_change) / len(all_change) < -0.5:
        #     time.sleep(60)
        #     print('\r 当前整体局势不佳：%s'%( round( sum(all_change) / len(all_change), 2 )), end='...')
        #     continue
        coin_pre = coin_pre_tmp
        amount = money / coin_pre[coin_change[0][0]]
        print("TIME/[%s]\tBUY/[%s]\tAMOUT/[%s]\tPRICE/[%s]" % (
            BeijingTime(), coin_change[0][0], round(amount, 4), coin_pre[coin_change[0][0]]))
        detect_times = 60
        for i in range(detect_times):
            time.sleep(5)
            data = exchange1.get_market(instId=coin_change[0][0])[0][0]
            print("\rPRICE_NOW:%s" % (data['last']), end='')
            if (i < detect_times - 1 and float(data['last']) / coin_pre[coin_change[0][0]] > 1.012) or (
                    i == detect_times - 1 and float(data['last']) > coin_pre[coin_change[0][0]]):
                money = amount * float(data['last']) * 0.9984
                print("\r ", end='')
                win_times += 1
                print("***WINED[%s]***! TIME/[%s]\tSELL/[%s]\tMONEY/[%s]\tPRICE/[%s]" % (
                    win_times, BeijingTime(), coin_change[0][0], round(money, 4), data['last']))
                break
            if (i < detect_times - 1 and float(data['last']) / coin_pre[coin_change[0][0]] < 0.99) or (
                    i == detect_times - 1 and float(data['last']) <= coin_pre[coin_change[0][0]]):
                money = amount * float(data['last']) * 0.9984
                print("\r ", end='')
                fail_times += 1
                print("```FAILED[%s]```! TIME/[%s]\tSELL/[%s]\tMONEY/[%s]\tPRICE/[%s]" % (
                    fail_times, BeijingTime(), coin_change[0][0], round(money, 4), data['last']))
                break


def output_record(orderNo, exchange, filename='exist_okex.txt', data={}):
    try:
        response = exchange.get_order_status(orderNo)
        # print('get status from respose content')
        # print(response)
        data = response[0]['data'][0]
    except Exception as e:
        pass

    os.system('clear; tail -n 15 exist_okex.txt')
    print("=" * 50 + '|' * 20 + '=' * 50)
    record = "\r[%s] [%s %s, SUCCESS! [%s\t%s\t%s]]..." % (BeijingTime(), data['side'].upper(),
                                                           exchange.symbol.upper(), data['px'],
                                                           data['sz'])
    print(record, '\n')
    f = open(filename, 'a')
    print(record, file=f)

    f.close()


def grid_heyue(exchanges, _rates=None):
    os.system('tail -n 10 exist_okex.txt')
    print("=" * 50 + '|' * 20 + '=' * 50)
    Error_flag = False
    if not _rates:
        _, _rates = get_rates()
    count = 0
    symbols = [x.symbol for x in exchanges]
    buy_orders = {x: '' for x in symbols}
    sell_orders = {x: '' for x in symbols}
    start = time.time()
    init_prices = {symbol: load_trade_log_once(symbol)[symbol]['price'] for symbol in symbols}
    buy_prices = {symbol: round(init_prices[symbol] - _rates[symbol]['gap'], _rates[symbol]['price_bit']) for symbol in
                  symbols}
    sell_prices = {
        symbol: round(init_prices[symbol] + _rates[symbol]['gap'] * _rates[symbol]['sell'], _rates[symbol]['price_bit'])
        for symbol in symbols}
    for exchange in exchanges:
        symbol = exchange.symbol
        response = exchange.get_posistion()[0]
        # 如果API返回的代码不是'0'，记录错误消息
        if response['code'] == '0' and response['data']:  # 确保响应代码为'0'且有数据
            data = response['data'][0]
            try:
                if float(data['avgPx']):
                    _rates[symbol]['change_base'] = float(data['avgPx'])
                    print('开仓均价为： {} '.format(_rates[symbol]['change_base']))
                    update_rates(_rates)
            except Exception as e:
                print(f'{symbol} 无法得到仓位数据，只能使用默认数据了')
        else:
            print('开仓均价为默认： {} '.format(_rates[symbol]['change_base']))

        open_order_id, _ = exchange.get_open_orders('SWAP')
        if not open_order_id:
            for i in range(5):
                time.sleep(2)
                open_order_id, _ = exchange.get_open_orders('SWAP')
        buy_price = buy_prices[symbol]
        sell_price = sell_prices[symbol]
        buy_amount = 0
        sell_amount = 0
        for idx in open_order_id:
            s, _ = exchange.get_order_status(idx)
            s = s['data'][0]
            if float(s['px']) == buy_price:
                buy_orders[symbol] = idx
                buy_amount = s['sz']
                # exchange.revoke_order(idx)
            if float(s['px']) == sell_price:
                sell_orders[symbol] = idx
                sell_amount = s['sz']
        if len(buy_orders[symbol]) == 0:
            buy_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * int(
                abs(_rates[symbol]['change_base'] - buy_price) // _rates[symbol]['change_gap'])
            buy_orders[symbol], _ = exchange.buy(buy_price, buy_amount, tdMode='cross')
        if len(sell_orders[symbol]) == 0:
            sell_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * int(
                abs(_rates[symbol]['change_base'] - sell_price) // _rates[symbol]['change_gap'])
            sell_amount = round(sell_amount, 4)
            sell_orders[symbol], _ = exchange.sell(sell_price, sell_amount, tdMode='cross')
        print("%s INTO CIRCLE, \n\tBuy order:%s, price:%s, amount:%s" % (
        symbol, buy_orders[symbol], buy_price, buy_amount))
        print("\tSell order:%s, price:%s, amount:%s" % (sell_orders[symbol], sell_price, sell_amount))

    process_bar = [''] * len(symbols)
    # return
    while True:
        if count > 86400:
            count = 0
        if count % 10000 == 0:
            _, _rates = get_rates()
            response = exchange.get_posistion()[0]
            # 如果API返回的代码不是'0'，记录错误消息
            if response['code'] == '0' and response['data']:  # 确保响应代码为'0'且有数据
                data = response['data'][0]
                try:
                    if float(data['avgPx']):
                        _rates[symbol]['change_base'] = float(data['avgPx'])
                    update_rates(_rates)
                except Exception as e:
                    pass
        for exchange in exchanges:
            symbol = exchange.symbol
            # init_price = init_prices[symbosl]
            buy_order = buy_orders[symbol]
            sell_order = sell_orders[symbol]
            orders_exist, _ = exchange.get_open_orders('SWAP')
            while not orders_exist:
                time.sleep(2)
                orders_exist, _ = exchange.get_open_orders('SWAP')
            price_now = exchange.get_price_now()
            gap = _rates[symbol]['gap']
            # print(orders_exist, buy_order, sell_order)
            if buy_order in orders_exist and sell_order in orders_exist:
                pass
            else:
                if buy_order not in orders_exist and sell_order not in orders_exist:
                    print("异常异常！居然都没了！")
                    buy_price = round(init_prices[symbol] - gap, _rates[symbol]['price_bit'])
                    buy_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * int(
                        abs((_rates[symbol]['change_base'] - buy_price) // _rates[symbol]['change_gap']))
                    buy_orders[symbol], _ = exchange.buy(buy_price, buy_amount, order_type='limit', tdMode='cross')
                    sell_price = round(init_prices[symbol] + _rates[symbol]['gap'] * _rates[symbol]['sell'],
                                       _rates[symbol]['price_bit'])
                    sell_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * int(
                        abs(_rates[symbol]['change_base'] - sell_price) // _rates[symbol]['change_gap'])
                    sell_orders[symbol], _ = exchange.sell(sell_price, sell_amount, order_type='limit', tdMode='cross')
                    continue
                elif buy_order not in orders_exist:
                    try:
                        # if 1 > 0:
                        # 先对外宣告上一单完成了
                        # 建立同一方向的新单子
                        init_prices[symbol] -= gap
                        buy_price = round(init_prices[symbol] - gap, _rates[symbol]['price_bit'])
                        buy_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * int(
                            abs(_rates[symbol]['change_base'] - buy_price) // _rates[symbol]['change_gap'])
                        # print("local - 2")
                        buy_order, _ = exchange.buy(round(buy_price, _rates[symbol]['price_bit']), buy_amount,
                                                    order_type='limit', tdMode='cross')
                        print('新开买单：', (round(buy_price, _rates[symbol]['price_bit']), buy_amount))
                        if not buy_order:
                            buy_order, _ = exchange.buy(round(buy_price, _rates[symbol]['price_bit']), buy_amount,
                                                        order_type='limit', tdMode='cross')
                            print('没找到buy order')
                            print(buy_price, buy_amount)
                            time.sleep(20)
                            break
                        # print("local - 3 - %s"%buy_order)
                        buy_orders[symbol] = buy_order
                        # 相反方向的单子未成交，直接修改，只改价格不改量
                        exchange.amend_order(orderId=sell_order, price=round(
                            init_prices[symbol] + _rates[symbol]['gap'] * _rates[symbol]['sell'],
                            _rates[symbol]['price_bit']))
                        # 把已经进行的交易存储起来，后续可用
                        # print("local - 4")
                        data = {'price': init_prices[symbol], 'amount': buy_amount / buy_price, 'buy_money': buy_amount}
                        save_trade_log_once(symbol, {symbol: data})
                        # print("local - 5")
                        continue
                    except Exception as e:
                        print("买单异常")
                        print(e)
                        if str(e).find('Timeout') != -1:
                            continue
                        count += 1
                        if count > 20:
                            Error_flag = True
                            break

                elif sell_order not in orders_exist:
                    init_prices[symbol] += gap
                    sell_price = round(init_prices[symbol] + _rates[symbol]['gap'] * _rates[symbol]['sell'],
                                       _rates[symbol]['price_bit'])
                    sell_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * int(
                        abs(_rates[symbol]['change_base'] - sell_price) // _rates[symbol]['change_gap'])
                    sell_order, _ = exchange.sell(round(sell_price, _rates[symbol]['price_bit']), sell_amount,
                                                  order_type='limit', tdMode='cross')
                    print('新开卖单：', (round(sell_price, _rates[symbol]['price_bit']), sell_amount))
                    if not sell_order:
                        print(sell_price, sell_amount)
                        break
                    sell_orders[symbol] = sell_order

                    exchange.amend_order(orderId=buy_order,
                                         price=round(init_prices[symbol] - gap, _rates[symbol]['price_bit']))
                    data = {'price': init_prices[symbol], 'amount': sell_amount / sell_price, 'sell_money': sell_amount}
                    save_trade_log_once(symbol, {symbol: data})
                    continue
            lowP = round(init_prices[symbol] - gap, _rates[symbol]['price_bit'])
            highP = round(init_prices[symbol] + _rates[symbol]['gap'] * _rates[symbol]['sell'],
                          _rates[symbol]['price_bit'])
            process_bar[symbols.index(symbol)] = '[%s] [%s %s %s %s %s]' % (symbol, lowP,
                                                                            '>' * int((price_now - lowP) // gap),
                                                                            price_now,
                                                                            '=' * int((highP - price_now) // gap),
                                                                            highP)
            time.sleep(1)
            time_now = time.time()
            print('\r%s [TIME:%s]' % ('\t'.join(process_bar), round(time_now - start)), end='')
    return Error_flag


def grid_eth(exchanges, _rates=None):
    if not _rates:
        _rates = {
            'ETH-USDT-SWAP': {'gap': 12.88, 'sell': 3.88, 'price_bit': 2, 'amount_base': 3, 'change_base': 3300,
                              'change_gap': 300,
                              'change_amount': 1}, }

    def output_record(orderNo, exchange, filename='exist_okex.txt', data={}):
        try:
            response = exchange.get_order_status(orderNo)
            data = response[0]['data'][0]
        except Exception as e:
            pass

    print("=" * 30 + '|' * 20 + '=' * 30)
    Error_flag = False
    count = 0
    symbols = [x.symbol for x in exchanges]
    buy_orders = {x: '' for x in symbols}
    sell_orders = {x: '' for x in symbols}
    start = time.time()
    init_prices = {exchanges[0].symbol: exchanges[0].get_price_now()}
    buy_prices = {symbol: round(init_prices[symbol] - _rates[symbol]['gap'], _rates[symbol]['price_bit']) for symbol in
                  symbols}
    sell_prices = {
        symbol: round(init_prices[symbol] + _rates[symbol]['gap'] * _rates[symbol]['sell'], _rates[symbol]['price_bit'])
        for symbol in symbols}
    for exchange in exchanges:
        symbol = exchange.symbol
        open_order_id, _ = exchange.get_open_orders('SWAP')
        if not open_order_id:
            for i in range(5):
                time.sleep(2)
                open_order_id, _ = exchange.get_open_orders('SWAP')
        buy_price = buy_prices[symbol]
        sell_price = sell_prices[symbol]
        buy_amount = 0
        sell_amount = 0
        for idx in open_order_id:
            s, _ = exchange.get_order_status(idx)
            s = s['data'][0]
            if float(s['px']) == buy_price:
                buy_orders[symbol] = idx
                buy_amount = s['sz']
                # exchange.revoke_order(idx)
            if float(s['px']) == sell_price:
                sell_orders[symbol] = idx
                sell_amount = s['sz']
        if len(buy_orders[symbol]) == 0:
            buy_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * int(
                abs((_rates[symbol]['change_base'] - buy_price) // _rates[symbol]['change_gap']))
            buy_orders[symbol], _ = exchange.buy(round(buy_price) + 0.88, 0.1)
        if len(sell_orders[symbol]) == 0:
            sell_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * int(
                abs((_rates[symbol]['change_base'] - sell_price) // _rates[symbol]['change_gap']))
            sell_orders[symbol], _ = exchange.sell(round(sell_price) + 0.88, 0.1)
        print("%s INTO CIRCLE, \n\tBuy order:%s, price:%s, amount:%s" % (
            symbol, buy_orders[symbol], buy_price, buy_amount))
        print("\tSell order:%s, price:%s, amount:%s" % (sell_orders[symbol], sell_price, 0.1))
    process_bar = [''] * len(symbols)
    # return
    buy_times = 0
    sell_times = 0
    while True:
        if count > 86400:
            count = 0
        for exchange in exchanges:
            symbol = exchange.symbol
            # init_price = init_prices[symbol]
            buy_order = buy_orders[symbol]
            sell_order = sell_orders[symbol]
            orders_exist, _ = exchange.get_open_orders('SWAP')
            while not orders_exist:
                time.sleep(2)
                orders_exist, _ = exchange.get_open_orders('SWAP')
            price_now = exchange.get_price_now()
            gap = _rates[symbol]['gap']
            # print(orders_exist, buy_order, sell_order)
            if buy_order in orders_exist and sell_order in orders_exist:
                pass
            else:
                if buy_order not in orders_exist and sell_order not in orders_exist:
                    print("异常异常！居然都没了！")
                    output_record(buy_order, exchange, data={
                        'sz': buy_prices[symbol] * _rates[symbol]['amount_base'] + _rates[symbol][
                            'change_amount'] * abs(
                            (_rates[symbol]['change_base'] - price_now) // _rates[symbol]['change_gap']),
                        'px': buy_price, 'side': 'BUY'})
                    output_record(sell_order, exchange, data={
                        'sz': sell_prices[symbol] * _rates[symbol]['amount_base'] + _rates[symbol][
                            'change_amount'] * abs(
                            (_rates[symbol]['change_base'] - price_now) // _rates[symbol]['change_gap']),
                        'px': buy_price, 'side': 'SELL'})
                    buy_price = round(init_prices[symbol] - gap, _rates[symbol]['price_bit'])
                    buy_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * int(
                        abs((_rates[symbol]['change_base'] - buy_price) // _rates[symbol]['change_gap']))
                    buy_orders[symbol], _ = exchange.buy(round(buy_price) + 0.88, 0.1, order_type='limit',
                                                         tdMode='cross')
                    sell_price = round(init_prices[symbol] + _rates[symbol]['gap'] * _rates[symbol]['sell'],
                                       _rates[symbol]['price_bit'])
                    sell_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * int(
                        abs((_rates[symbol]['change_base'] - sell_price) // _rates[symbol]['change_gap']))
                    sell_orders[symbol], _ = exchange.sell(round(sell_price) + 0.88, 0.1, order_type='limit',
                                                           tdMode='cross')
                    continue
                elif buy_order not in orders_exist:
                    try:
                        # if 1 > 0:
                        # 先对外宣告上一单完成了
                        # print("local - 0")
                        output_record(buy_order, exchange, data={
                            'sz': buy_prices[symbol] * _rates[symbol]['amount_base'] + _rates[symbol][
                                'change_amount'] * abs(
                                (_rates[symbol]['change_base'] - price_now) // _rates[symbol]['change_gap']),
                            'px': buy_price, 'side': 'BUY'})
                        init_prices[symbol] -= gap
                        buy_price = round(init_prices[symbol] - gap, _rates[symbol]['price_bit'])
                        buy_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * abs(
                            (_rates[symbol]['change_base'] - price_now) // _rates[symbol]['change_gap'])
                        # print("local - 2")
                        buy_times += 1
                        sell_times = 0
                        buy_order, _ = exchange.buy(round(buy_price) + 0.88, 0.1 + 0.01 * buy_times // 1.5,
                                                    order_type='limit', tdMode='cross')
                        if not buy_order:
                            buy_order, _ = exchange.buy(round(buy_price) + 0.88, buy_amount,
                                                        order_type='limit', tdMode='cross')
                            print('没找到buy order')
                            print(buy_price, buy_amount)
                            time.sleep(20)
                            break
                        # print("local - 3 - %s"%buy_order)
                        buy_orders[symbol] = buy_order
                        # 相反方向的单子未成交，直接修改，只改价格不改量
                        exchange.amend_order(orderId=sell_order, price=round(
                            init_prices[symbol] + _rates[symbol]['gap'] * _rates[symbol]['sell'],
                            _rates[symbol]['price_bit']))
                        # 把已经进行的交易存储起来，后续可用
                        # print("local - 4")
                        data = {'price': init_prices[symbol], 'amount': buy_amount / buy_price, 'buy_money': buy_amount}
                        # print("local - 5")
                        continue
                    except Exception as e:
                        print("买单异常")
                        print(e)
                        if str(e).find('Timeout') != -1:
                            continue
                        count += 1
                        if count > 20:
                            Error_flag = True
                            break
                elif sell_order not in orders_exist:
                    # try:
                    output_record(sell_order, exchange, data={
                        'sz': sell_prices[symbol] * _rates[symbol]['amount_base'] + _rates[symbol][
                            'change_amount'] * abs(
                            (_rates[symbol]['change_base'] - price_now) // _rates[symbol]['change_gap']),
                        'px': buy_price, 'side': 'SELL'})
                    init_prices[symbol] += gap
                    sell_price = round(init_prices[symbol] + _rates[symbol]['gap'] * _rates[symbol]['sell'],
                                       _rates[symbol]['price_bit'])
                    sell_amount = _rates[symbol]['amount_base'] + _rates[symbol]['change_amount'] * abs(
                        (_rates[symbol]['change_base'] - price_now) // _rates[symbol]['change_gap'])
                    sell_times += 1
                    buy_times = 0
                    sell_order, _ = exchange.sell(round(sell_price) + 0.88, 0.1 + 0.01 * sell_times // 1.5,
                                                  order_type='limit', tdMode='cross')
                    if not sell_order:
                        # print(sell_price, 0.1)
                        break
                    sell_orders[symbol] = sell_order
                    exchange.amend_order(orderId=buy_order,
                                         price=round(init_prices[symbol] - gap, _rates[symbol]['price_bit']))
                    data = {'price': init_prices[symbol], 'amount': sell_amount / sell_price, 'sell_money': sell_amount}
                    continue
            lowP = round(init_prices[symbol] - gap, _rates[symbol]['price_bit'])
            highP = round(init_prices[symbol] + _rates[symbol]['gap'] * _rates[symbol]['sell'],
                          _rates[symbol]['price_bit'])
            process_bar[symbols.index(symbol)] = '[%s] [%s %s %s %s %s]' % (symbol, lowP,
                                                                            '>' * int((price_now - lowP) // gap),
                                                                            price_now,
                                                                            '=' * int((highP - price_now) // gap),
                                                                            highP)
            time.sleep(1)
            time_now = time.time()
            print('\r%s [TIME:%s]' % ('\t'.join(process_bar), round(time_now - start)), end='')
    return Error_flag


def get_okexExchage(name='eth', account=0, show=True):
    if account == 1 and os.path.exists('../sub_config'):
        with open('../sub_config', 'r') as f:
            data = f.readlines()
            ak = data[0].strip()
            sk = data[1].strip()
            ph = data[2].strip()
            if show:
                print(' Sub Okex 1', end=' ')
            exchange1 = OkexSpot(symbol="{}-USDT-SWAP".format(name.upper()),
                                 access_key=ak, secret_key=sk, passphrase=ph, host=None)
            exchange1.account_type = 'SUB'
    elif account == 2 and os.path.exists('../sub_config'):
        with open('../sub_config_2', 'r') as f:
            data = f.readlines()
            ak = data[0].strip()
            sk = data[1].strip()
            ph = data[2].strip()
            if show:
                print(' Sub Okex 2', end=' ')
            exchange1 = OkexSpot(symbol="{}-USDT-SWAP".format(name.upper()),
                                 access_key=ak, secret_key=sk, passphrase=ph, host=None)
            exchange1.account_type = 'SUB'
    else:
        ak = ACCESS_KEY
        sk = SECRET_KEY
        ph = PASSPHRASE
        if show:
            print(' Main Okex ', end=' ')
        exchange1 = OkexSpot(symbol="{}-USDT-SWAP".format(name.upper()),
                             access_key=ak, secret_key=sk, passphrase=ph, host=None)
        exchange1.account_type = 'MAIN'

    return exchange1


def beautify_order_output(orders):
    header = f"{'Order ID':<25} {'Type':<10} {'Price':<20} {'ID':<5} {'Rate':<10}"
    print(header)
    print('-' * len(header))
    for order_id, info in orders.items():
        print(f"{order_id:<25} {info['type']:<10} {round(info['price']):<20} {info['id']:<5} {info['rate']:<10.4f}")


def pin_capture_trading(e2, interval=0.5, range_start=2, range_end=10, amount=1):
    current_price = e2.get_price_now()
    if current_price is None:
        print("Failed to fetch current price.")
        return
    orders = {}
    sell_prices = [current_price * (100 + i * interval) / 100 for i in
                   range(int(range_start / interval), int(range_end / interval) + 1)]
    buy_prices = [current_price * (100 - i * interval) / 100 for i in
                  range(int(range_start / interval), int(range_end / interval) + 1)]
    print(sell_prices)
    print(buy_prices)
    # Place initial orders
    for idx, price in enumerate(sell_prices):
        sell_order_id, _ = e2.sell(price, amount, order_type='limit', tdMode='cross')
        if sell_order_id:
            orders[sell_order_id] = {'type': 'sell', 'id': idx, 'rate': (101 + idx * interval) / 100, 'price': price}
    for idx, price in enumerate(buy_prices):
        buy_order_id, _ = e2.buy(price, amount, order_type='limit', tdMode='cross')
        if buy_order_id:
            orders[buy_order_id] = {'type': 'buy', 'id': idx, 'rate': (99 - idx * interval) / 100, 'price': price}
    print(f"Initial orders placed with IDs and types:\n ")
    beautify_order_output(orders)
    # Monitoring and handling orders
    while True:
        time.sleep(60)  # Check every minute
        open_order_ids, _ = e2.get_open_orders('SWAP')
        triggered = [oid for oid in orders if oid not in open_order_ids]
        current_price = e2.get_price_now()
        if triggered:
            print(f"Orders triggered: {triggered}")
            # Perform the opposite transaction
            for order_id in triggered:
                order_type = orders[order_id]
                if order_type == 'sell':
                    e2.buy(current_price + 10, amount, order_type='limit', tdMode='cross')
                else:
                    e2.sell(current_price - 10, amount, order_type='limit', tdMode='cross')
                del orders[order_id]  # Remove the executed order from the dictionary
            print(f"Opposite orders executed at price: {current_price}")
            flag = True
            while flag:
                succ, _ = e2.revoke_orders(orders.keys())
                if succ:
                    flag = False
            break  # Exit loop if no orders are left
        for order_id in orders.keys():
            order_info = orders[order_id]
            new_price = current_price * order_info['rate']
            success, error = e2.amend_order(price=new_price, quantity=amount, orderId=order_id)
            if not success:
                flag = True
                while flag:
                    succ, _ = e2.revoke_orders(orders.keys())
                    if succ:
                        flag = False
            orders[order_id]['price'] = new_price  # 更新订单价格信息
        print(f"Orders updated at price: {current_price} \n")
        beautify_order_output(orders)


if __name__ == '__main__':
    exchanges, _rates = get_rates()
    print(_rates)
    while True:
        try:
            grid_heyue(exchanges, _rates)
        except Exception as e:
            print(e)
            time.sleep(10)

    # print(_rates)
    # while True:
    #   grid_heyue(exchanges, _rates)
