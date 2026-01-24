# MACD 策略 (MACD Strategy)

通过加载**外部策略配置文件**，对不同交易所、不同币种、不同周期计算 MACD，以经典**金叉**（DIF 上穿 DEA）买入、**死叉**（DIF 下穿 DEA）卖出。K 线来自 `get_klines`。

## 特性

- **外部配置与热更新**：参数来自 `macd_strategy_config.json`，修改保存后自动重新加载。
- **多交易所、多币种、多周期**：每条规则可配 `exchange`、`account_id`、`symbol`、`timeframe`，以及 MACD 参数 `fast`、`slow`、`signal`。
- **金叉 / 死叉**：
  - **金叉**：上一根 K 线 DIF < DEA，当前根 DIF > DEA → 买入。
  - **死叉**：上一根 K 线 DIF > DEA，当前根 DIF < DEA → 卖出。
- **状态持久化**：`macd_strategy_state.json` 记录 DIF 相对 DEA 的上下关系，避免同一根 K 线内重复发单。

## MACD 计算

- **DIF** = EMA(close, fast) − EMA(close, slow)，默认 fast=12，slow=26。
- **DEA** = EMA(DIF, signal)，默认 signal=9。
- 金叉：DIF 由下上穿 DEA；死叉：DIF 由上下穿 DEA。

## 配置说明 (`macd_strategy_config.json`)

| 字段 | 说明 | 默认 |
|------|------|------|
| `check_interval` | 轮询间隔（秒） | 60 |
| `kline_limit` | `get_klines` 请求根数 | 200 |
| `dry_run` | `true` 仅打印信号不下单 | true |
| `rules` | 规则列表 | [] |

### 单条规则 `rules[]`

| 字段 | 说明 | 示例 |
|------|------|------|
| `id` | 规则标识 | `okx_btc_1h` |
| `exchange` | 交易所 | okx |
| `account_id` | 账户 ID | 0 |
| `symbol` | 币种（如 btc、eth） | btc |
| `timeframe` | K 线周期（1m/15m/1h/4h/1d 等） | 1h |
| `fast` | 快线周期 | 12 |
| `slow` | 慢线周期 | 26 |
| `signal` | 信号线周期 | 9 |
| `golden_cross_buy` | 金叉时是否买入 | true |
| `death_cross_sell` | 死叉时是否卖出 | true |
| `order_amount` | 每次触发下单金额（USDT） | 100.0 |
| `enabled` | 是否启用 | true |

## 运行

```bash
python apps/strategies/macd/MACDStrategy.py
```

修改并保存 `macd_strategy_config.json` 后，策略会在下一轮循环自动重新加载。

## 依赖

- `get_klines`：交易所驱动需实现 `get_klines(symbol, timeframe, limit)`（如 OKX 的 `ctos/drivers/okx/driver.py`）。
- `place_incremental_orders`：来自 `ExecutionEngine`。
- `pick_exchange`：按 `exchange`、`account_id` 创建并复用 `ExecutionEngine`。

## 文件

- `MACDStrategy.py`：主程序，含配置加载、热更新、K 线解析、MACD 计算、金叉/死叉判断与下单。
- `macd_strategy_config.json`：外部配置（可热更新）。
- `macd_strategy_state.json`：运行时状态，由程序自动读写。
