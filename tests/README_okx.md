OKX Driver 测试输出快照
=======================

测试时间: 请在运行后补充实际时间戳（例如 2025-09-16T05:36:32）
测试环境: OKX Exchange API（合约：ETH-USDT-SWAP）

测试结果概览
------------

- 总测试数: 15
- 通过数: 12
- 失败数: 3（cancel_all 两项、fees 一项）
- 预计用时: ~2-4 秒

详细测试结果
------------

- 市场数据
  - get_price_now: ✅ 通过 — 示例价格 4377.81
  - get_orderbook: ✅ 通过 — 返回结构正常（示例 bids/asks 为空数组）
  - get_klines: ✅ 通过 — 返回标准化数据（示例包含 trade_date/open/high/low/close/vol1/vol）

- 交易与订单
  - place_order: ✅ 通过 — 示例返回 ordId '2852827355428593664'
  - amend_order: ✅ 通过 — 修改订单成功
  - get_order_status: ✅ 通过 — 返回状态 live、类型 limit、sz 0.01 等字段
  - get_open_orders: ✅ 通过 — 示例返回 ['2852827355428593664']
  - revoke_order: ✅ 通过 — 订单撤销成功
  - cancel_all（无 symbol）: ❌ 失败 — 'NoneType' object is not iterable
  - cancel_all（指定 symbol）: ❌ 失败 — 'NoneType' object is not iterable

- 账户与仓位
  - fetch_balance: ✅ 通过 — 示例 USDT 余额 3097.7631607182693
  - get_position: ✅ 通过 — 返回包含 avgPx/markPx/lever/upl 等字段

- 交易所信息
  - symbols: ✅ 通过 — 示例 ['BTC-USDT', 'ETH-USDT', 'SOL-USDT']
  - exchange_limits: ✅ 通过 — 示例 {'price_scale': 1e-08, 'size_scale': 1e-08}
  - fees: ❌ 失败 — too many values to unpack (expected 2)

功能特性验证
------------

- 市场数据: 价格、订单簿、K 线 ✅
- 订单管理: 下单、改价、查询、撤单 ✅；批量取消 ❌（待修复）
- 账户信息: 余额、仓位 ✅
- 交易所信息: 交易对、交易限制 ✅；费率接口 ❌（待修复）

性能指标（样例）
--------------

- API 响应: < 1 秒（大部分请求）
- 数据处理: 正常
- 稳定性: 通过

运行方式
--------

1) 配置 API 密钥（本地开发示例）

   - 在 `ctos/drivers/okx/Config.py` 中设置 `ACCESS_KEY`、`SECRET_KEY`、`PASSPHRASE`

2) 运行测试

```bash
python -m tests.test_okx_driver
```

3) 查看输出

- 终端打印当前运行结果
- 可参考本文件了解期望的输出结构与字段

已知问题与后续计划
------------------

- cancel_all 接口在无参数/带 symbol 两种调用下均出现迭代错误（NoneType）。计划：
  - 检查驱动内部返回值是否始终为可迭代结构；
  - 对 None 做显式保护与合并空列表处理。
- fees 接口返回解包错误。计划：
  - 统一接口返回值签名（期望二元组或显式对象），补齐测试断言与错误分支。

总结
----

OKX 驱动核心功能可用，市场数据、下单流程、账户/仓位查询均通过。后续需修复批量取消与费率接口，完善异常与空值处理，以保证边界场景的稳定性。