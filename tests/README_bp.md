没这个pyfiglet包
<ctos.drivers.backpack.driver.BackpackDriver object at 0x7f5d56f5f850>


[BP_TEST] before call: get_price_now


[BP_TEST] after call: get_price_now -> 4482.67


[BP_TEST] before call: get_orderbook


[BP_TEST] after call: get_orderbook -> ETH_USDC_PERP


[BP_TEST] before call: get_klines


```markdown
### `get_klines` API Call Result

```

(
trade\_date       open     high      low     close      vol1             vol
0  1758016800000  4511.88  4514.60  4495.00  4499.51  1126.8094  5.078269e+06
1  1758020400000  4499.50  4507.62  4495.00  4501.62  1233.2404  5.552114e+06
2  1758024000000  4501.63  4506.74  4496.39  4500.31  1752.5052  7.889530e+06
3  1758027600000  4500.55  4512.50  4431.63  4473.67  5135.4976  2.295534e+07
4  1758031200000  4473.71  4473.82  4425.56  4447.89  4299.9148  1.910236e+07
5  1758034800000  4447.84  4471.58  4431.28  4468.87  2741.4156  1.220026e+07
6  1758038400000  4468.87  4472.50  4448.55  4465.35  2544.5075  1.135353e+07
7  1758042000000  4465.34  4511.84  4464.12  4488.25  3260.5049  1.465010e+07
8  1758045600000  4488.25  4497.58  4467.43  4475.57  1362.4197  6.108819e+06
9  1758049200000  4475.71  4496.22  4472.84  4492.09  1024.1439  4.593317e+06
10 1758052800000  4492.51  4499.90  4485.79  4499.19  1415.6698  6.361939e+06
11 1758056400000  4499.19  4511.45  4491.92  4508.36  1194.4949  5.377075e+06
12 1758060000000  4508.58  4525.70  4502.56  4521.33  1531.1175  6.911756e+06
13 1758063600000  4521.33  4524.09  4496.29  4502.47  1265.6800  5.709889e+06
14 1758067200000  4502.50  4517.84  4494.01  4514.29  1881.1182  8.484910e+06
15 1758070800000  4514.70  4520.44  4504.19  4514.18  2075.7147  9.365404e+06
16 1758074400000  4514.19  4553.50  4508.39  4531.79  2306.6011  1.045199e+07
17 1758078000000  4531.79  4531.79  4496.60  4498.38  1811.4137  8.178744e+06
18 1758081600000  4498.39  4505.24  4464.24  4477.46  1741.5557  7.811921e+06
19 1758085200000  4477.46  4490.59  4477.46  4483.58  799.9689  3.587435e+06
None
)

```
```


[BP_TEST] before call: place_order


[BP_TEST] after call: place_order -> ('8891371467', None)


[BP_TEST] before call: amend_order


[BP_TEST] after call: amend_order -> ('8891380021', None)


[BP_TEST] before call: get_order_status


[BP_TEST] after call: get_order_status -> ({'orderId': '8891380021', 'symbol': 'ETH_USDC_PERP', 'side': 'bid', 'orderType': 'limit', 'price': 3944.75, 'quantity': 0.01, 'filledQuantity': 0.0, 'status': 'New', 'timeInForce': 'GTC', 'postOnly': None, 'reduceOnly': None, 'clientId': None, 'createdAt': 1758086762900, 'updatedAt': None, 'raw': {'clientId': None, 'createdAt': 1758086762900, 'executedQuantity': '0', 'executedQuoteQuantity': '0', 'id': '8891380021', 'orderType': 'Limit', 'postOnly': False, 'price': '3944.75', 'quantity': '0.01', 'reduceOnly': None, 'relatedOrderId': None, 'selfTradePrevention': 'RejectTaker', 'side': 'Bid', 'status': 'New', 'stopLossLimitPrice': None, 'stopLossTriggerBy': None, 'stopLossTriggerPrice': None, 'strategyId': None, 'symbol': 'ETH_USDC_PERP', 'takeProfitLimitPrice': None, 'takeProfitTriggerBy': None, 'takeProfitTriggerPrice': None, 'timeInForce': 'GTC', 'triggerBy': None, 'triggerPrice': None, 'triggerQuantity': None, 'triggeredAt': None}}, None)


[BP_TEST] before call: get_open_orders only Orderids
ETH_USDC_PERP


[BP_TEST] after call: get_open_orders -> ([{'orderId': '8891380021', 'symbol': 'ETH_USDC_PERP', 'side': 'bid', 'orderType': 'limit', 'price': 3944.75, 'quantity': 0.01, 'filledQuantity': 0.0, 'status': 'New', 'timeInForce': 'GTC', 'postOnly': None, 'reduceOnly': None, 'clientId': None, 'createdAt': 1758086762900, 'updatedAt': None, 'raw': {'clientId': None, 'createdAt': 1758086762900, 'executedQuantity': '0', 'executedQuoteQuantity': '0', 'id': '8891380021', 'orderType': 'Limit', 'postOnly': False, 'price': '3944.75', 'quantity': '0.01', 'reduceOnly': None, 'relatedOrderId': None, 'selfTradePrevention': 'RejectTaker', 'side': 'Bid', 'status': 'New', 'stopLossLimitPrice': None, 'stopLossTriggerBy': None, 'stopLossTriggerPrice': None, 'strategyId': None, 'symbol': 'ETH_USDC_PERP', 'takeProfitLimitPrice': None, 'takeProfitTriggerBy': None, 'takeProfitTriggerPrice': None, 'timeInForce': 'GTC', 'triggerBy': None, 'triggerPrice': None, 'triggerQuantity': None, 'triggeredAt': None}}], None)


[BP_TEST] before call: get_open_orders all infos
ETH_USDC_PERP


[BP_TEST] after call: get_open_orders -> ([{'orderId': '8891380021', 'symbol': 'ETH_USDC_PERP', 'side': 'bid', 'orderType': 'limit', 'price': 3944.75, 'quantity': 0.01, 'filledQuantity': 0.0, 'status': 'New', 'timeInForce': 'GTC', 'postOnly': None, 'reduceOnly': None, 'clientId': None, 'createdAt': 1758086762900, 'updatedAt': None, 'raw': {'clientId': None, 'createdAt': 1758086762900, 'executedQuantity': '0', 'executedQuoteQuantity': '0', 'id': '8891380021', 'orderType': 'Limit', 'postOnly': False, 'price': '3944.75', 'quantity': '0.01', 'reduceOnly': None, 'relatedOrderId': None, 'selfTradePrevention': 'RejectTaker', 'side': 'Bid', 'status': 'New', 'stopLossLimitPrice': None, 'stopLossTriggerBy': None, 'stopLossTriggerPrice': None, 'strategyId': None, 'symbol': 'ETH_USDC_PERP', 'takeProfitLimitPrice': None, 'takeProfitTriggerBy': None, 'takeProfitTriggerPrice': None, 'timeInForce': 'GTC', 'triggerBy': None, 'triggerPrice': None, 'triggerQuantity': None, 'triggeredAt': None}}], None)


[BP_TEST] before call: revoke_order


[BP_TEST] after call: revoke_order -> (True, None)


[BP_TEST] before call: cancel_all (no symbol)


[BP_TEST] after call: cancel_all (no symbol) -> {'ok': True, 'raw': []}


[BP_TEST] before call: cancel_all (with symbol)


[BP_TEST] after call: cancel_all (with symbol) -> {'ok': True, 'raw': []}


[BP_TEST] before call: fetch_balance


[BP_TEST] after call: fetch_balance -> 12042.182468


[BP_TEST] before call: get_position


[BP_TEST] after call: get_position -> ({'symbol': 'ETH_USDC_PERP', 'positionId': '8626747549', 'side': 'long', 'quantity': 0.517, 'entryPrice': 4491.872870237995, 'markPrice': 4483.88088476, 'pnlUnrealized': -0.085124, 'pnlRealized': -3.913558, 'leverage': None, 'liquidationPrice': 0.0, 'ts': None}, None)


[BP_TEST] before call: symbols


[BP_TEST] after call: symbols -> ['SOL_USDC_PERP', 'BTC_USDC_PERP', 'ETH_USDC_PERP', 'XRP_USDC_PERP', 'SUI_USDC_PERP', 'DOGE_USDC_PERP', 'JUP_USDC_PERP', 'TRUMP_USDC_PERP', 'WIF_USDC_PERP', 'BERA_USDC_PERP']


[BP_TEST] before call: exchange_limits


[BP_TEST] after call: exchange_limits -> {}


[BP_TEST] before call: fees


[BP_TEST] after call: fees -> (None, ValueError('too many values to unpack (expected 2)'))
