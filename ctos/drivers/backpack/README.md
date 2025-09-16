# Backpack 驱动说明（ctos/drivers/backpack）

本目录提供 Backpack 交易所的驱动封装，统一对上层策略暴露一组与 OKX 驱动相近的调用接口，便于无感切换与快速集成。

功能概览（BackpackDriver）
- 行情相关：
  - `symbols()` → (list, error)：从公开市场接口获取并按模式（perp/spot）过滤交易对
  - `get_price_now(symbol)`：获取最新成交价
  - `get_orderbook(symbol, level)`：获取订单簿（bids/asks）
  - `get_klines(symbol, timeframe, limit, start_time, end_time)`：按目标 DF 结构返回 K 线（自动按周期边界推导时间范围）
  - `fees(symbol, limit, offset)`：获取资金费率（返回原始数据及 latest 快照）
- 交易相关：
  - `place_order(symbol, side, order_type, size, price=None, **kwargs)`：下单，兼容 `post_only`、`time_in_force` 等参数
  - `revoke_order(order_id, symbol)`：撤单（Backpack 撤单需带 symbol）
  - `amend_order(order_id, symbol, ...)`：通过“查单→撤单→下单”实现改单，支持改价/改量/TIF/post_only 等
  - `get_open_orders(symbol=None, market_type='PERP')`：获取未完成订单；可配合 `get_order_status(symbol, order_id, ...)` 查询单一订单
  - `cancel_all(symbol)`：撤销指定交易对的全部未完成订单
- 账户/仓位：
  - `fetch_balance(currency)`：返回全部或指定币种余额（大小写不敏感）
  - `get_position(symbol=None)`：返回全部或指定交易对的仓位信息

快速测试
- 进入项目根目录，运行：
  - `python -m tests.test_bp_driver`
- 支持环境变量：
  - `BP_PUBLIC_KEY`、`BP_SECRET_KEY`（必需）
  - `BP_TEST_MODE`（perp|spot，默认 perp）、`BP_TEST_SYMBOL`、`BP_TEST_TIMEFRAME`、`BP_TEST_LIMIT`
- 测试输出将打印到控制台并写入 `tests/README_bp.py`

参考链接
- Backpack Python SDK（第三方实现）：
  - https://github.com/sndmndss/bpx-py/tree/main
  - https://github.com/solomeowl/backpack_exchange_sdk/blob/main/backpack_exchange_sdk/authenticated.py
- 非官方 API 指南与示例：
  - https://github.com/cryptocj520/backpack_api_guide
- 官方文档：
  - https://docs.backpack.exchange/#tag/Trades

说明
- 由于不同账户或市场返回结构可能存在差异，驱动在解析时做了尽量的兼容处理；若遇到字段缺失或响应结构变化，请根据返回的 `raw` 字段或原始响应进行适配。