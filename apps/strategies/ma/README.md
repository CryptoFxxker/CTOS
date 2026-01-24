# 均线策略 (MA Strategy)

通过加载**外部策略配置文件**，对不同交易所、不同币种、不同周期计算均线，根据**均线突破**（买）与**均线击穿**（卖）产生买卖信号并执行下单。均线数据来自驱动层的 `get_klines`。

## 特性

- **外部配置**：策略参数全部来自 `ma_strategy_config.json`，支持运行中**热更新**（修改保存后自动重新加载）。
- **多交易所、多币种、多周期**：每条规则可配置 `exchange`、`account_id`、`symbol`、`timeframe`、`ma_period`，独立运行。
- **突破 / 击穿**：
  - **突破**：上一根 K 线收盘在均线下方，当前根收盘站上均线 → 买入。
  - **击穿**：上一根 K 线收盘在均线上方，当前根收盘跌破均线 → 卖出。
- **状态持久化**：`ma_strategy_state.json` 记录各规则「价格在均线上/下」的状态，避免同一根 K 线内重复发单。

## 配置说明 (`ma_strategy_config.json`)

| 字段 | 说明 | 默认 |
|------|------|------|
| `check_interval` | 轮询间隔（秒） | 60 |
| `kline_limit` | 每次 `get_klines` 请求的 K 线根数 | 200 |
| `dry_run` | `true` 只打印信号不下单，`false` 真实下单 | true |
| `rules` | 规则列表 | [] |

### 单条规则 `rules[]`

| 字段 | 说明 | 示例 |
|------|------|------|
| `id` | 规则唯一标识，用于状态记录 | `okx_btc_1h_ma20` |
| `exchange` | 交易所，如 `okx` | okx |
| `account_id` | 账户 ID | 0 |
| `symbol` | 交易对基础币种（如 btc、eth） | btc |
| `timeframe` | K 线周期，与 `get_klines` 一致：1m/15m/1h/4h/1d 等 | 1h |
| `ma_period` | 均线周期（根数） | 20 |
| `breakthrough_buy` | 是否在突破时买入 | true |
| `breakdown_sell` | 是否在击穿时卖出 | true |
| `order_amount` | 每次触发的下单金额（USDT） | 100.0 |
| `enabled` | 是否启用 | true |

## 运行

```bash
cd /path/to/ctos
python apps/strategies/ma/MAStrategy.py
```

- 首次运行如无 `ma_strategy_config.json` 会生成默认配置。
- 修改 `ma_strategy_config.json` 并保存后，策略会在下一轮循环**自动重新加载**，无需重启。

## 依赖

- `get_klines`：需交易所驱动实现 `get_klines(symbol, timeframe, limit)`。当前 OKX 驱动通过 `ctos/drivers/okx/driver.py` 的 `get_klines` 调用底层 `okex.get_kline` 获取 K 线（DataFrame，含 `close` 列）。
- `place_incremental_orders`：来自 `ExecutionEngine`，按 USDT 金额下单。
- `pick_exchange`：按 `exchange`、`account_id` 创建 `ExecutionEngine`，同一 `(exchange, account_id)` 会复用同一 engine。

## 文件

- `MAStrategy.py`：策略主程序，含配置加载、热更新、`get_klines`、均线计算、突破/击穿判断与下单。
- `ma_strategy_config.json`：外部策略配置（可热更新）。
- `ma_strategy_state.json`：运行时状态，由程序自动读写。
