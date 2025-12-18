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


def _add_bpx_path():
    """添加bpx包路径到sys.path，支持多种运行方式"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    bpx_path = os.path.join(current_dir, 'bpx')
    
    # 添加当前目录的bpx路径
    if bpx_path not in sys.path:
        sys.path.insert(0, bpx_path)
    
    # 添加项目根目录的bpx路径（如果存在）
    project_root = os.path.abspath(os.path.join(current_dir, '../../..'))
    root_bpx_path = os.path.join(project_root, 'bpx')
    if os.path.exists(root_bpx_path) and root_bpx_path not in sys.path:
        sys.path.insert(0, root_bpx_path)
    if os.path.exists(project_root) and project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root
# 执行路径添加
PROJECT_ROOT = _add_bpx_path()
print('PROJECT_ROOT: ', PROJECT_ROOT, 'CURRENT_DIR: ', os.path.dirname(os.path.abspath(__file__)))

try:
    # 优先：绝对导入（当项目以包方式安装/运行时）
    from ctos.drivers.okx.util import *
    from ctos.drivers.okx.Config import ACCESS_KEY, SECRET_KEY, PASSPHRASE, HOST_IP, HOST_USER, HOST_PASSWD, HOST_IP_1
except Exception as e:
    print('Error okex.py from ctos parent path import *', e)
    try:
        from .util import *
    except Exception as e:
        print('Error okex.py from util import *', e)
    try:
       from .Config import ACCESS_KEY, SECRET_KEY, PASSPHRASE, HOST_IP, HOST_USER, HOST_PASSWD, HOST_IP_1
    except Exception as e:
        print('Error okex.py from util import *', e)



class OkexSpot:
    """OKEX Spot REST API client."""

    def __init__(self, symbol, access_key, secret_key, passphrase, host=None, proxies=None):
        self.symbol = symbol
        self._host = host or "https://www.okx.com"
        self._access_key = access_key
        self._secret_key = secret_key
        self._passphrase = passphrase
        self.account_type = 'MAIN'
        self.proxies = proxies

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
            method, url, data=body, headers=headers, timeout=10, proxies=self.proxies
        ).json()
        if result.get("code") and result.get("code") != "0":
            return None, result
        return result, None

    def get_exchange_info(self, instType='SPOT', symbol=None):
        """Obtain trading rules and trading pair information."""
        uri = "/api/v5/public/instruments"
        if symbol and symbol.find('SWAP') != -1:
            instType = 'SWAP'
        params = {"instType": instType}
        if symbol:
            params["instId"] = symbol
        success, error = self.request(method="GET", uri=uri, params=params)
        return success, error

    def set_symbol(self, symbol):
        if len(symbol) == 0:
            return
        else:
            self.symbol = symbol

    def get_orderbook(self, symbol=None, sz=5):
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
        if symbol:
            if symbol.find('-') == -1:
                symbol = f'{symbol.upper()}-USDT-SWAP'
        else:
            symbol = self.symbol
        uri = "/api/v5/market/books"
        params = {"instId": symbol, "sz": sz}
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
            print('Error fetch_balance: ', e)
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

    def get_fee(self, symbol='ETH-USDT-SWAP', instType='SPOT'):
        """
       Get account asset data.
       :param currency: e.g. "USDT", "BTC"
       """
        params = {"instType": instType, "instId": symbol}
        result, err = self.request(
            "GET", "/api/v5/account/trade-fee", params=params, auth=True
        )
        return result['data'], err

    def get_funding_rate(self, symbol='ETH-USDT-SWAP', instType='SPOT'):
        """
        获取当前资金费率
        HTTP: GET /api/v5/public/funding-rate
        :param symbol: 交易对，例如 'ETH-USDT-SWAP'；为空则使用当前实例的 symbol
        :return: (result, error)
        """
        inst_id = symbol if symbol else self.symbol
        uri = "/api/v5/public/funding-rate"
        params = {"instId": inst_id}
        success, error = self.request(method="GET", uri=uri, params=params)
        return success, error

    def get_position(self, symbol=None, instType='SWAP'):
        if not symbol:
            params = {"instType": instType}
        else:
            if symbol:
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

    def get_order_status(self, order_id, symbol=None):
        """Get order status.
       @param order_id: order id.
       """
        symbol = self.symbol if not symbol else symbol
        uri = "/api/v5/trade/order"
        params = {"instId": symbol, "ordId": order_id}
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

    def place_order(self, price, quantity, order_type='limit', tdMode='cross', side=None, symbol=None, ccy=None):
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
            data = {"instId": symbol, "tdMode": tdMode, "side": side if side else 'buy'}
        if symbol.find('SWAP') != -1:
            quantity = quantity
        if ccy:
            data['ccy'] = ccy
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

    def revoke_order(self, order_id, symbol=None):
        """Cancel an order.
       @param order_id: order id
       """
        uri = "/api/v5/trade/cancel-order"
        data = {"instId": self.symbol if not symbol else symbol, "ordId": order_id}
        _, error = self.request(method="POST", uri=uri, body=data, auth=True)
        if error:
            return order_id, error
        else:
            return True, None

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

    def revoke_orders(self, order_ids=[], symbol=None):
        """
       Cancel mutilple orders by order ids.
       @param order_ids :order list
       """

        success, error = [], []
        if not order_ids and symbol:
            order_ids = self.get_open_orders(symbol=symbol, onlyOrderId=True)[0]
        for order_id in order_ids:
            _, e = self.revoke_order(order_id=order_id, symbol=symbol)
            if e:
                error.append((order_id, e))
            else:
                success.append(order_id)
        return success, error

    def get_open_orders(self, instType='SWAP', symbol='ETH-USDT-SWAP', onlyOrderId=True):

        """Get all unfilled orders.
       * NOTE: up to 100 orders
       """
        uri = "/api/v5/trade/orders-pending"
        if symbol:
            params = {"instType": instType, "instId": symbol}
        else:
            params = {"instType": instType}
        success, error = self.request(method="GET", uri=uri, params=params, auth=True)
        if error:
            return None, error
        else:
            order_ids = []
            if success.get("data"):
                for order_info in success["data"]:
                    if onlyOrderId:
                        order_ids.append(order_info["ordId"])
                    else:
                        order_ids.append(order_info)
            return order_ids, None

    def amend_order(self, price=None, quantity=None, orderId=None, symbol=None):
        """
       Open buy order.
       :param price:order price
       :param quantity:order quantity
       :param order_type:order type, "LIMIT" or "MARKET"
       :return:order id and None, otherwise None and error information
       """
        uri = "/api/v5/trade/amend-order"
        data = {"instId": self.symbol if not symbol else symbol, "ordId": orderId}
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

    def get_market(self, instId='', all=False, condition='SWAP'):
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
                    ccy_datas.append(x)
            return ccy_datas, None

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

if __name__ == '__main__':
    eth = get_okexExchage('eth')
    print(eth.get_fee(symbol='ETH-USDT'))

    # print(_rates)
    # while True:
    #   grid_heyue(exchanges, _rates)
