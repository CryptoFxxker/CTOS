## CTOS: Crypto Trading Operating System (Linux‑inspired)

**Scope:** Quant trading on CEXs (initially OKX, Backpack, Binance).
**Design note:** CTOS borrows Linux’s concepts (arch, driver, syscall, scheduler, processes), but it’s not a full copy. We adapt what’s useful for building robust, composable, and portable trading systems.

### Why CTOS?

* **Portability:** Abstract away exchange quirks behind **standard trading syscalls**.
* **Composability:** Strategies = “processes”; Exchange adapters = “drivers”; Each CEX = “arch”.
* **Reliability:** Separation of concerns (kernel/runtime/drivers) improves testability & safety.
* **Observability:** Structured logs, metrics, and reproducible backtests.

---

## Concept Mapping (Linux → CTOS)

| Linux Concept  | CTOS Analogy                                                                      | Notes                                                                                          |
| -------------- | --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `arch/`        | **Exchange architectures** (`drivers/okx`, `drivers/binance`, `drivers/backpack`) | One folder per exchange; keeps REST/WS/signing/specs isolated.                                 |
| Device Drivers | **Exchange drivers**                                                              | REST/WS client, signer, symbol map, feature flags.                                             |
| Syscalls       | **Trading syscalls**                                                              | `place_order`, `cancel_order`, `amend_order`, `balances`, `positions`, `subscribe_ticks`, etc. |
| Scheduler      | **Orchestrator**                                                                  | Coordinates strategy “processes”, rate limits, retries, ordering.                              |
| Processes      | **Strategies**                                                                    | Stateless/stateful strategies that call syscalls; supervised by runtime.                       |
| Filesystem     | **Storage layer**                                                                 | Parquet/SQLite for market data, trades, marks, snapshots, configs.                             |
| `/proc`        | **Metrics/Introspection**                                                         | Health, PnL, risk, latency, exchange limits, open websockets.                                  |
| `init`/systemd | **Supervisor**                                                                    | Starts modules, restarts, isolates crashes, rolling updates.                                   |

---

## Directory Layout

```
ctos/
├─ README.md
├─ .gitignore
├─ configs/
│  ├─ ctos.yaml                 # global config & toggles
│  └─ secrets.example.yaml      # api keys template (never commit real keys)
├─ ctos/
│  ├─ __init__.py
│  ├─ core/
│  │  ├─ kernel/
│  │  │  ├─ syscalls.py         # canonical syscall spec
│  │  │  ├─ scheduler.py        # strategy process orchestration
│  │  │  └─ event_bus.py        # pub/sub of events (orders, fills, ticks)
│  │  ├─ runtime/
│  │  │  ├─ strategy_manager.py # load/run/stop user strategies
│  │  │  ├─ execution_engine.py # syscall dispatch, retries, idempotency
│  │  │  ├─ risk.py             # pre-trade checks, throttles, kill-switch
│  │  │  └─ portfolio.py        # positions, exposure, PnL
│  │  └─ io/
│  │     ├─ datafeed/           # REST/WS streams normalization
│  │     ├─ storage/            # parquet/sqlite adapters
│  │     └─ logging/            # structured logging config
│  └─ drivers/
│     ├─ okx/
│     │  ├─ __init__.py
│     │  ├─ arch.yaml           # features, limits, symbol shape
│     │  ├─ rest.py             # REST adapter
│     │  ├─ ws.py               # websocket streams
│     │  └─ signer.py           # auth & request signing
│     ├─ binance/               # same pattern as okx/
│     └─ backpack/              # same pattern as okx/
├─ apps/
│  ├─ strategies/
│  │  └─ examples/
│  │     └─ mean_reversion.py   # demo strategy calling syscalls
│  └─ research/
│     └─ notebooks/             # optional
├─ tools/
│  ├─ backtest/                 # offline simulator & replay
│  └─ simulator/                # latency, slippage, fee models
├─ scripts/
│  ├─ run_dev.sh                # convenience runners (optional)
│  └─ backtest.sh
└─ tests/                       # unit & integration tests
```

---

## Trading Syscalls (Canonical Interface)

> Drivers implement these consistently per exchange; strategies only talk to syscalls.

* **Market Data:** `subscribe_ticks`, `subscribe_klines(tf)`, `get_orderbook(level)`
* **Trading:** `place_order(...)`, `amend_order(...)`, `cancel_order(id)`, `cancel_all(symbol?)`
* **Account:** `balances()`, `positions()`, `margin_info()`, `transfer(...)`
* **Ref‑data:** `symbols()`, `exchange_limits()`, `fees()`

Design goals:

* **Idempotency** (client order IDs), **retries**, **backoff**, **rate-limit awareness**.
* **Normalization** of enums, sizes, price scales across exchanges.
* **Metadata‑rich errors** (driver + syscall + payload + remote code).

---

## Runtime & Safety

* **Risk gates:** pre‑trade checks (price bands, max leverage/notional, max cancel rate).
* **Kill‑switch:** breach → halt strategies, revoke orders, notify.
* **Determinism:** strategy in/out logged; replayable in backtests.
* **Observability:** structured logs + metrics (latency, fills, slippage, rejects).

---


## Quick Start (Practical Workflow)

1. **Get the Code**
   Clone or download the CTOS repository scaffold:

   ```bash
   git clone https://github.com/your-org/ctos.git
   cd ctos
   ```

   Or generate the skeleton locally:

   ```bash
   python3 scaffold_ctos.py --name ctos --exchanges okx backpack binance
   cd ctos
   ```

2. **Set Up the Environment**
   Create a clean Python environment and install dependencies:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -U pip
   pip install -r requirements.txt
   ```

3. **Configure API Keys**

   * Copy the example secrets file:

     ```bash
     cp configs/secrets.example.yaml configs/secrets.yaml
     ```
   * Fill in your **OKX / Backpack / Binance** API keys.

     > ⚠️ Never commit this file to git.

4. **Configure Global Settings**

   * Edit `configs/ctos.yaml` to choose:

     * `default_exchange` (`okx`, `backpack`, `binance`)
     * `mode`: `paper` (simulation) or `live`
     * logging, risk limits, and data storage.

5. **Run a Built-in Strategy**
   Start one of the demo strategies in **paper mode**:

   ```bash
   python -m apps.strategies.examples.mean_reversion
   ```

   Or run your own strategy file in `apps/strategies/`.

6. **Backtest or Replay**

   * Place historical data files under `tools/backtest/`.
   * Launch the backtest runner:

     ```bash
     ./scripts/backtest.sh
     ```
   * Results will be logged into `var/logs/` and stored in `var/data/`.

7. **Move to Live Trading (Carefully)**

   * Switch `mode: live` in `configs/ctos.yaml`.
   * Make sure **risk checks and kill-switch** are enabled.
   * Run your strategy again — it will now route orders to the real exchange.

---

👉 This way the flow is: **get code → install env → set API keys → configure runtime → run paper strategy → backtest → live deploy**.

Would you like me to also add a **table of example commands** for running the strategies in your current `Strategy.py` (like `btc`, `grid`, `hedge` etc.) so that it’s included in the README?


## Roadmap

* **v0.1**: Syscall spec, drivers (OKX/Backpack/Binance) skeletons, runtime orchestration, paper‑trading.
* **v0.2**: Unified WS streaming, simulator/backtest parity, richer risk module.
* **v0.3**: Multi‑exchange portfolio netting, live failover, warm restart, richer metrics UI.

---

## 安全与合规（中文）

* **API最小权限原则**：仅交易所需权限；提现永久关闭。
* **密钥安全**：使用 `configs/secrets.yaml`（未纳入版本控制），可以结合系统密钥管理或环境变量。
* **风控优先**：下单前风险检查、熔断与Kill‑switch、速率与风控日志留存。
* **回测可复现**：策略输入/输出与市场数据快照可回放。

---

## 许可与免责声明

* **免责声明**：加密货币交易风险极高。CTOS仅为研究/工具框架，请自行评估并承担风险。
* **License**：自选（MIT / Apache‑2.0 / GPL‑3.0），在 `LICENSE` 中明确。

---
