没这个pyfiglet包
<ctos.drivers.okx.driver.OkxDriver object at 0x7faee4ed38b0>


[OKX_TEST] before call: get_price_now
ETH-USDT-SWAP eth


[OKX_TEST] after call: get_price_now -> 4480.6


[OKX_TEST] before call: get_orderbook


[OKX_TEST] after call: get_orderbook -> ETH-USDT-SWAP


[OKX_TEST] before call: get_klines


[OKX_TEST] after call: get_klines -> (       trade_date     open     high  ...    close        vol1               vol
0   1758085200000  4474.86   4487.9  ...   4480.6   35879.836   160803368.99939
1   1758081600000     4495   4502.8  ...  4474.86  133741.562   599260283.77045
2   1758078000000  4528.54  4528.98  ...     4495   110262.29   497364959.77206
3   1758074400000   4511.2     4550  ...  4528.55  160533.933   727323880.85123
4   1758070800000  4510.83   4517.5  ...  4511.19   49339.013    222416620.7888
5   1758067200000     4499  4514.23  ...  4510.82   54087.991   243648155.13861
6   1758063600000  4517.14     4521  ...     4499   59232.438   266851343.34425
7   1758060000000     4505  4523.33  ...  4517.14    61757.93   278614163.99551
8   1758056400000     4496  4507.99  ...     4505   48803.038   219561984.03363
9   1758052800000  4488.87  4496.64  ...  4496.01   34752.404   156046215.89025
10  1758049200000  4471.68  4493.13  ...  4488.87   42756.116   191573559.74722
11  1758045600000  4483.75  4493.98  ...  4471.68   76629.632   343217844.19881
12  1758042000000  4460.48  4507.85  ...  4483.75  210559.853   945036504.28658
13  1758038400000     4465  4468.99  ...  4460.48  112862.783   503072318.27244
14  1758034800000  4443.37     4468  ...     4465  151373.794   672942137.96668
15  1758031200000  4470.84  4470.84  ...  4443.37  338096.513  1500377538.80441
16  1758027600000  4498.54   4510.5  ...  4470.83  451628.841  2014989681.65394
17  1758024000000   4499.6     4505  ...  4498.54   48418.352   217855682.97216
18  1758020400000  4496.01  4505.33  ...  4499.59   60124.273   270467791.31238
19  1758016800000   4509.2  4512.49  ...  4496.01   56203.731   253077270.57042

[20 rows x 7 columns], None)


[OKX_TEST] before call: place_order
ETH-USDT-SWAP eth


[OKX_TEST] after call: place_order -> ('2871733629465567232', None)


[OKX_TEST] before call: amend_order
ETH-USDT-SWAP eth


[OKX_TEST] after call: amend_order -> ('2871733629465567232', None)


[OKX_TEST] before call: get_order_status


[OKX_TEST] after call: get_order_status -> ({'orderId': '2871733629465567232', 'symbol': 'ETH-USDT-SWAP', 'side': 'buy', 'orderType': 'limit', 'price': 3584.12, 'quantity': 0.01, 'filledQuantity': 0.0, 'status': 'live', 'timeInForce': None, 'postOnly': None, 'reduceOnly': 'false', 'clientId': '', 'createdAt': 1758086731436, 'updatedAt': 1758086732904, 'raw': {'accFillSz': '0', 'algoClOrdId': '', 'algoId': '', 'attachAlgoClOrdId': '', 'attachAlgoOrds': [], 'avgPx': '', 'cTime': '1758086731436', 'cancelSource': '', 'cancelSourceReason': '', 'category': 'normal', 'ccy': '', 'clOrdId': '', 'fee': '0', 'feeCcy': 'USDT', 'fillPx': '', 'fillSz': '0', 'fillTime': '', 'instId': 'ETH-USDT-SWAP', 'instType': 'SWAP', 'isTpLimit': 'false', 'lever': '20', 'linkedAlgoOrd': {'algoId': ''}, 'ordId': '2871733629465567232', 'ordType': 'limit', 'pnl': '0', 'posSide': 'net', 'px': '3584.12', 'pxType': '', 'pxUsd': '', 'pxVol': '', 'quickMgnType': '', 'rebate': '0', 'rebateCcy': 'USDT', 'reduceOnly': 'false', 'side': 'buy', 'slOrdPx': '', 'slTriggerPx': '', 'slTriggerPxType': '', 'source': '', 'state': 'live', 'stpId': '', 'stpMode': 'cancel_maker', 'sz': '0.01', 'tag': '', 'tdMode': 'cross', 'tgtCcy': '', 'tpOrdPx': '', 'tpTriggerPx': '', 'tpTriggerPxType': '', 'tradeId': '', 'tradeQuoteCcy': '', 'uTime': '1758086732904'}}, None)


[OKX_TEST] before call: get_open_orders only Orderids


[OKX_TEST] after call: get_open_orders -> (['2871733629465567232'], None)


[OKX_TEST] before call: get_open_orders all infos


[OKX_TEST] after call: get_open_orders -> ([{'orderId': '2871733629465567232', 'symbol': 'ETH-USDT-SWAP', 'side': 'buy', 'orderType': 'limit', 'price': 3584.12, 'quantity': 0.01, 'filledQuantity': 0.0, 'status': 'live', 'timeInForce': None, 'postOnly': None, 'reduceOnly': 'false', 'clientId': '', 'createdAt': 1758086731436, 'updatedAt': 1758086732904, 'raw': {'accFillSz': '0', 'algoClOrdId': '', 'algoId': '', 'attachAlgoClOrdId': '', 'attachAlgoOrds': [], 'avgPx': '', 'cTime': '1758086731436', 'cancelSource': '', 'cancelSourceReason': '', 'category': 'normal', 'ccy': '', 'clOrdId': '', 'fee': '0', 'feeCcy': 'USDT', 'fillPx': '', 'fillSz': '0', 'fillTime': '', 'instId': 'ETH-USDT-SWAP', 'instType': 'SWAP', 'isTpLimit': 'false', 'lever': '20', 'linkedAlgoOrd': {'algoId': ''}, 'ordId': '2871733629465567232', 'ordType': 'limit', 'pnl': '0', 'posSide': 'net', 'px': '3584.12', 'pxType': '', 'pxUsd': '', 'pxVol': '', 'quickMgnType': '', 'rebate': '0', 'rebateCcy': 'USDT', 'reduceOnly': 'false', 'side': 'buy', 'slOrdPx': '', 'slTriggerPx': '', 'slTriggerPxType': '', 'source': '', 'state': 'live', 'stpId': '', 'stpMode': 'cancel_maker', 'sz': '0.01', 'tag': '', 'tdMode': 'cross', 'tgtCcy': '', 'tpOrdPx': '', 'tpTriggerPx': '', 'tpTriggerPxType': '', 'tradeId': '', 'tradeQuoteCcy': '', 'uTime': '1758086732904'}}], None)


[OKX_TEST] before call: revoke_order


[OKX_TEST] after call: revoke_order -> (True, None)


[OKX_TEST] before call: cancel_all (no symbol)


[OKX_TEST] after call: cancel_all (no symbol) raised: 'NoneType' object is not iterable


[OKX_TEST] before call: cancel_all (with symbol)


[OKX_TEST] after call: cancel_all (with symbol) raised: 'NoneType' object is not iterable


[OKX_TEST] before call: fetch_balance


[OKX_TEST] after call: fetch_balance -> 3651.262698055444


[OKX_TEST] before call: get_position


[OKX_TEST] after call: get_position -> {'symbol': 'HYPE-USDT-SWAP', 'positionId': '2607751765412978688', 'side': 'short', 'quantity': 49.0, 'entryPrice': 53.452471836734695, 'markPrice': 54.269, 'pnlUnrealized': -4.000987999999987, 'pnlRealized': 1.1578178889628183, 'leverage': 20.0, 'liquidationPrice': 745.7783960544394, 'ts': 1758081600489}


[OKX_TEST] before call: symbols


[OKX_TEST] after call: symbols -> ['MOG-USDT-SWAP', 'CETUS-USDT-SWAP', 'WIF-USDT-SWAP', 'PI-USDT-SWAP', 'SUSHI-USDT-SWAP', 'XLM-USDT-SWAP', 'GPS-USDT-SWAP', 'CRO-USDT-SWAP', 'UNI-USDT-SWAP', 'STRK-USDT-SWAP']


[OKX_TEST] before call: exchange_limits


[OKX_TEST] after call: exchange_limits -> {'price_scale': 1e-08, 'size_scale': 1e-08}


[OKX_TEST] before call: fees


[OKX_TEST] after call: fees -> ({'symbol': 'ETH-USDT-SWAP', 'instType': 'SWAP', 'fundingRate_hourly': -5.3457456351125e-06, 'fundingRate_period': -4.27659650809e-05, 'period_hours': 8.0, 'fundingTime': 1758096000000, 'raw': {'code': '0', 'data': [{'formulaType': 'withRate', 'fundingRate': '-0.0000427659650809', 'fundingTime': '1758096000000', 'impactValue': '20000.0000000000000000', 'instId': 'ETH-USDT-SWAP', 'instType': 'SWAP', 'interestRate': '0.0001000000000000', 'maxFundingRate': '0.0075', 'method': 'current_period', 'minFundingRate': '-0.0075', 'nextFundingRate': '', 'nextFundingTime': '1758124800000', 'premium': '-0.0005376571978021', 'settFundingRate': '-0.0000686128088225', 'settState': 'settled', 'ts': '1758086700087'}], 'msg': ''}}, None)
