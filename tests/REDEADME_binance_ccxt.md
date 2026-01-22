PROJECT_ROOT:  D:\blockchain\polymarket\CTOS CURRENT_DIR:  D:\blockchain\polymarket\CTOS\ctos\drivers\binance
从配置文件读取Binance账户: main (ID: 0)
load_yaml ctos.yaml make some errors: None, BUT, u can still run normally, don't worry about it
✓ Binance Driver初始化成功 (账户ID: 0, 模式: usdm)
================================================================================
Binance CCXT Driver 接口功能测试
================================================================================
Driver: <ctos.drivers.binance.driver_ccxt.BinanceDriver object at 0x000001507927FC40>
测试交易对: ETH/USDT
================================================================================

[TEST 1] get_price_now
--------------------------------------------------------------------------------
✓ 成功: 3212.0

[TEST 2] get_orderbook
--------------------------------------------------------------------------------
✓ 成功: symbol=ETH/USDT:USDT, bids数量=5, asks数量=5
  示例: bid=[3212.4, 1.716], ask=[3212.41, 117.48]

[TEST 3] get_klines
--------------------------------------------------------------------------------
✓ 成功: DataFrame, shape=(20, 7)
  前5行:
      trade_date     open     high      low    close        vol1           vol
0  1768762800000  3360.67  3364.43  3342.70  3345.36   80676.545  2.698921e+08
1  1768766400000  3345.36  3351.22  3335.49  3339.77   53708.033  1.793725e+08
2  1768770000000  3339.77  3344.98  3335.01  3340.37   25735.709  8.596679e+07
3  1768773600000  3340.37  3356.14  3338.58  3349.34   36162.686  1.211211e+08
4  1768777200000  3349.33  3349.34  3277.42  3282.77  433050.075  1.421604e+09

[TEST 4] place_order (限价买单)
--------------------------------------------------------------------------------
✓ 成功: order_id=8389766078910271161, price=2890.79

[TEST 5] amend_order
--------------------------------------------------------------------------------
⚠ 警告: new_order_id=None，保留原order_id=8389766078910271161用于后续测试, new_price=2569.59

[TEST 6] get_order_status
--------------------------------------------------------------------------------
✓ 成功: orderId=8389766078910271161, status=open, side=buy, price=2890.79, quantity=0.01

[TEST 7] get_open_orders (仅订单ID)
--------------------------------------------------------------------------------
✓ 成功: 订单数量=1, 订单ID列表=['8389766078910271161']

[TEST 8] get_open_orders (完整信息)
--------------------------------------------------------------------------------
✓ 成功: 订单数量=1
  第一个订单: orderId=8389766078910271161, status=open, side=buy

[TEST 9] revoke_order
--------------------------------------------------------------------------------
✓ 成功: True

[TEST 10] cancel_all (无symbol参数)
--------------------------------------------------------------------------------
✓ 成功: []

[TEST 11] cancel_all (带symbol参数)
--------------------------------------------------------------------------------
✓ 成功: [{'info': {'code': '200', 'msg': 'The operation of cancel all open order is done.'}, 'fees': [], 'id': None, 'clientOrderId': None, 'timestamp': None, 'datetime': None, 'symbol': None, 'type': None, 'side': None, 'lastTradeTimestamp': None, 'lastUpdateTimestamp': None, 'price': None, 'amount': None, 'cost': None, 'average': None, 'filled': None, 'remaining': None, 'timeInForce': None, 'postOnly': None, 'trades': [], 'reduceOnly': None, 'stopPrice': None, 'triggerPrice': None, 'takeProfitPrice': None, 'stopLossPrice': None, 'status': None, 'fee': None}]

[TEST 12] fetch_balance
--------------------------------------------------------------------------------
✓ 成功: USDT余额=0.8361315

[TEST 13] get_position (keep_origin=False)
--------------------------------------------------------------------------------
✓ 成功: 持仓数量=0

[TEST 14] get_position (keep_origin=True)
--------------------------------------------------------------------------------
✓ 成功: 返回原始数据
  数据条数: 0

[TEST 15] symbols
--------------------------------------------------------------------------------
✓ 成功: 交易对数量=610
  前10个交易对: ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'BCH/USDT:USDT', 'XRP/USDT:USDT', 'LTC/USDT:USDT', 'TRX/USDT:USDT', 'ETC/USDT:USDT', 'LINK/USDT:USDT', 'XLM/USDT:USDT', 'ADA/USDT:USDT']

[TEST 16] exchange_limits (所有)
--------------------------------------------------------------------------------
✓ 成功: 交易对数量=692
  第一个交易对: symbol=BTC/USDT:USDT, price_precision=0.1, size_precision=0.001

[TEST 17] exchange_limits (指定symbol)
--------------------------------------------------------------------------------
✓ 成功: symbol=ETH/USDT:USDT, price_precision=0.01, size_precision=0.001, min_order_size=0.001

[TEST 18] fees
--------------------------------------------------------------------------------
✓ 成功: symbol=ETH/USDT:USDT, fundingRate_hourly=-6.8875e-07, fundingRate_period=-5.51e-06, period_hours=8.0

[TEST 19] fees (keep_origin=True)
--------------------------------------------------------------------------------
✓ 成功: 返回原始数据
  数据类型: dict, keys=['info', 'symbol', 'markPrice', 'indexPrice', 'interestRate']

================================================================================
测试完成
================================================================================