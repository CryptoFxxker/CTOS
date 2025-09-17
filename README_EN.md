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

## BackpackDriver Feature Overview

---

### Market Data

* `symbols()` → (list, error): Retrieves and filters trading pairs from the public market interface based on type (perp/spot).
* `get_price_now(symbol)`: Gets the latest traded price.
* `get_orderbook(symbol, level)`: Gets the order book (bids/asks).
* `get_klines(symbol, timeframe, limit, start_time, end_time)`: Returns k-line data according to the target data frame structure (automatically derives time ranges based on period boundaries).
* `fees(symbol, limit, offset)`: Retrieves funding rates (returns raw data and a latest snapshot).

---

### Trading

* `place_order(symbol, side, order_type, size, price=None, **kwargs)`: Places an order, compatible with parameters like `post_only` and `time_in_force`.
* `revoke_order(order_id, symbol)`: Cancels an order (requires `symbol` for Backpack API).
* `amend_order(order_id, symbol, ...)`: Amends an order by looking it up, canceling it, and then placing a new one. Supports changes to price, size, TIF, `post_only`, etc.
* `get_open_orders(symbol=None, market_type='PERP')`: Gets open orders. Can be used with `get_order_status(symbol, order_id, ...)` to query a single order.
* `cancel_all(symbol)`: Cancels all open orders for a specified trading pair.

---

### Account/Position

* `fetch_balance(currency)`: Returns the balance for all or a specified currency (case-insensitive).
* `get_position(symbol=None)`: Returns position information for all or a specified trading pair.

### 🎯 CTOS Design Goals (For Beginners)

1. **Plug & Play** — one-click start, no complex setup.
   👉 Even if you’re new, you can run your first trading strategy within minutes.

2. **No Code Hassle** — prebuilt strategies included.
   👉 Choose “mean reversion”, “grid”, or “hedge” with a single command, no coding required.

3. **Multi-Exchange, One Interface**
   👉 Trade on OKX, Binance, Backpack… without learning their different APIs.

4. **Safe by Default**
   👉 Built-in risk checks & kill-switch protect you from big losses due to mistakes.

5. **Paper Trading First**
   👉 Practice with **simulated money** before going live, so you can learn without risk.

6. **Clear Insights**
   👉 Auto-generated reports and charts show your profit/loss, risk, and performance clearly.

7. **Step-by-Step Upgrade Path**
   👉 Start with ready-made strategies → tweak simple configs → later write your own if you want.

---
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


* **v0.1**
  Syscall specification; driver skeleton (OKX / Backpack / Binance); runtime scheduling; simulated trading

* **v0.2**
  Unified WebSocket stream; consistency between backtesting and simulation; richer risk-control modules

* **v0.3**
  Multi-exchange portfolio net asset management; real-time failover; hot restart; stronger indicators and UI

* **🎉 Milestone (Today)**
  ✅ Completed unified API design and abstraction for 2 exchanges.
  🚀 Achieved a significant milestone today: **AI-driven, system-call-based grid strategy code** has been generated, fine-tuned, and officially deployed!
  📂 Location: `apps/strategies/grid/Grid.py`
  🥂🎊 Cheers to this launch — onward to the next stage!

---

## Security & Compliance

* **Principle of Least Privilege:** API keys should only have the necessary trading permissions; withdrawal must always remain disabled.
* **Key Security:** Store secrets in `configs/secrets.yaml` (excluded from version control), or use environment variables / system key managers.
* **Risk Controls First:** Pre-trade checks, circuit breakers, kill-switch mechanisms, rate-limit enforcement, and full logging.
* **Reproducible Backtests:** All strategy inputs/outputs and market snapshots must be replayable.

---

## License & Disclaimer

* **Disclaimer:** Cryptocurrency trading carries extremely high risk. CTOS is provided as a research/tooling framework; use it at your own discretion and risk.
* **License:** Choose an open-source license (MIT / Apache-2.0 / GPL-3.0) and specify it clearly in the `LICENSE` file.

