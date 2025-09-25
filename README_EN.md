🌐 Languages: [English](README_EN.md) | [中文](README.md) | [日本語](scripts/README_JP.md) | [한국어](scripts/README_KR.md)
![](logo.png)
## CTOS: Crypto Trading Operating System (Linux-inspired)

**Scope:** Quantitative trading on centralized exchanges (CEX) (initially supporting OKX, Backpack, Binance).
**Design note:** CTOS borrows Linux's concepts (architecture arch, driver, syscall, scheduler, processes), but it's not a complete copy. Instead, we selectively adopt ideas suitable for building robust, composable, and portable trading systems.

### Why CTOS?

* **Portability:** Abstract away exchange differences through **unified trading system calls (syscalls)**.
* **Composability:** Strategies = "processes"; Exchange adapters = "drivers"; Each exchange = "architecture".
* **Reliability:** Layered design of kernel/runtime/drivers improves testability and safety.
* **Observability:** Structured logs, metrics, and reproducible backtesting capabilities.
* **High Robustness:** Aligns order price and quantity precision across all exchanges, supports amount-based ordering with automatic conversion, worry-free throughout.

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

## Project Directory Structure

```
ctos/
├─ README.md                    # Project documentation
├─ pyproject.toml              # Python project configuration
├─ requirements.txt            # Python dependencies
├─ environment.yml             # Conda environment configuration
├─ configs/                    # Configuration management directory
│  ├─ account.yaml             # Account configuration file (API keys)
│  ├─ account_reader.py        # Account configuration reader
│  ├─ config_reader.py         # General configuration reader
│  └─ example_usage.py         # Configuration usage examples
├─ ctos/                       # Core code directory
│  ├─ core/                    # Core system modules
│  │  ├─ kernel/               # System kernel
│  │  │  ├─ syscalls.py        # Unified trading system call interface
│  │  │  ├─ scheduler.py       # Strategy scheduler
│  │  │  └─ event_bus.py       # Event bus
│  │  ├─ runtime/              # Runtime system
│  │  │  ├─ ExecutionEngine.py # Execution engine (core)
│  │  │  ├─ SystemMonitor.py   # System monitor
│  │  │  ├─ AccountManager.py  # Account manager
│  │  │  ├─ RiskWatcher.py     # Risk monitor
│  │  │  ├─ SignalGenerator.py # Signal generator
│  │  │  ├─ DataHandler.py     # Data handler
│  │  │  └─ IndicatorCalculator.py # Indicator calculator
│  │  └─ io/                   # Input/output modules
│  │     ├─ logging/           # Logging system
│  │     ├─ datafeed/          # Data source integration
│  │     └─ storage/           # Data storage
│  └─ drivers/                 # Exchange drivers
│     ├─ okx/                  # OKX exchange driver
│     │  ├─ driver.py          # OKX main driver
│     │  └─ util.py            # OKX utility functions
│     ├─ backpack/             # Backpack exchange driver
│     │  ├─ driver.py          # Backpack main driver
│     │  └─ util.py            # Backpack utility functions
│     └─ binance/              # Binance exchange driver
├─ apps/                       # Application layer
│  ├─ strategies/              # Trading strategies
│  │  ├─ grid/                 # Grid strategies
│  │  │  └─ Grid-All-Coin.py   # All-coin grid strategy
│  │  ├─ hedge/                # Hedging strategies
│  │  ├─ rank/                 # Ranking strategies
│  │  └─ examples/             # Example strategies
│  ├─ indicatorVisualization/  # Indicator visualization
│  └─ website/                 # Web interface
├─ tools/                      # Tool set
├─ scripts/                    # Script files
└─ tests/                      # Test files
```

### 🔥 Core Files Description

#### System Core
- **`ctos/core/runtime/ExecutionEngine.py`** - Execution engine, system core, responsible for strategy execution and system calls
- **`ctos/core/runtime/SystemMonitor.py`** - System monitor, responsible for position monitoring, anomaly detection and auto-correction
- **`ctos/core/kernel/syscalls.py`** - Unified trading system call interface, abstracts exchange differences

#### Exchange Drivers
- **`ctos/drivers/okx/driver.py`** - OKX exchange driver, supports dynamic account mapping
- **`ctos/drivers/backpack/driver.py`** - Backpack exchange driver, supports dynamic account mapping
- **`ctos/drivers/binance/driver.py`** - Binance exchange driver

#### Configuration Management
- **`configs/account.yaml`** - Account configuration file, stores API keys for each exchange
- **`configs/account_reader.py`** - Account configuration reader, supports dynamic account management

#### Trading Strategies
- **`apps/strategies/grid/Grid-All-Coin.py`** - All-coin grid strategy, integrated with ExecutionEngine
- **`apps/strategies/examples/`** - Example strategy collection

#### Monitoring & Logging
- **`ctos/core/io/logging/`** - Logging directory, contains:
  - `{exchange}_Account{id}_{strategy}_system_monitor.log` - System monitoring logs
  - `{exchange}_Account{id}_{strategy}_operation_log.log` - Operation logs
  - `{exchange}_account{id}_position_backup.json` - Position backup
  - `{exchange}_account{id}_anomaly_report.json` - Anomaly reports

---

## Trading System Calls (Unified Interface)

> Each exchange driver must implement these interfaces; strategies call syscalls through ExecutionEngine.

### 🚀 Core Function Overview

#### Market Data
- **`get_price_now(symbol)`** - Get latest traded price
- **`get_orderbook(symbol, level)`** - Get order book (bids/asks)
- **`get_klines(symbol, timeframe, limit, start_time, end_time)`** - Get K-line data
- **`fees(symbol, limit, offset)`** - Get funding rates

#### Trading
- **`place_order(symbol, side, order_type, size, price=None, **kwargs)`** - Place order
- **`revoke_order(order_id, symbol)`** - Cancel order
- **`amend_order(order_id, symbol, ...)`** - Modify order (query→cancel→place)
- **`get_open_orders(symbol=None, instType='SWAP')`** - Get open orders
- **`get_order_status(order_id, keep_origin=False)`** - Query order status
- **`cancel_all(symbol)`** - Cancel all orders for specified trading pair

#### Account/Position
- **`fetch_balance(currency)`** - Get balance (supports multiple currencies)
- **`get_position(symbol=None, keep_origin=False)`** - Get position information
- **`close_all_positions(symbol=None)`** - Close all positions

### 🔧 Execution Engine Functions

#### ExecutionEngine Core Methods
- **`place_incremental_orders(amount, coin, side, soft=True)`** - Incremental order placement
- **`set_coin_position(coin, usdt_amount, soft=True)`** - Set coin position
- **`_order_tracking_logic(coins, soft_orders_to_focus)`** - Order tracking logic

#### System Monitoring Functions
- **`monitor_positions()`** - Position monitoring (supports auto-correction)
- **`get_position_summary()`** - Get position summary
- **`get_anomaly_summary()`** - Get anomaly summary
- **`start_position_monitoring()`** - Start continuous monitoring

### 📊 Supported Exchanges

| Exchange | Driver File | Account Support | Special Features |
|----------|-------------|-----------------|------------------|
| **OKX** | `drivers/okx/driver.py` | Dynamic account mapping | Complete futures trading support |
| **Backpack** | `drivers/backpack/driver.py` | Dynamic account mapping | Native perpetual contract support |
| **Binance** | `drivers/binance/driver.py` | Basic support | World's largest exchange |

### 🎯 Dynamic Account Management

All exchange drivers support dynamic account selection through `account_id` parameter:

```python
# Use main account (account_id=0)
engine = ExecutionEngine(account=0, exchange_type='okx')

# Use sub account (account_id=1)
engine = ExecutionEngine(account=1, exchange_type='backpack')

# Use third account (account_id=2)
engine = ExecutionEngine(account=2, exchange_type='okx')
```

Account mapping is based on `configs/account.yaml` configuration file:
- `account_id=0` → First account (usually main)
- `account_id=1` → Second account (usually sub1)
- `account_id=2` → Third account (usually sub2)

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        CTOS System Architecture             │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │ Application     │  │ Configuration   │  │ Tools Layer     │ │
│  │ Layer (Apps)    │  │ Layer (Config)  │  │ (Tools)         │ │
│  │                 │  │                 │  │                 │ │
│  │ • Grid Strategy │  │ • Account Config│  │ • Backtest Tools│ │
│  │ • Hedge Strategy│  │ • System Config │  │ • Simulator     │ │
│  │ • Rank Strategy │  │ • Key Management│  │ • Visualization │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                Core Runtime (Core Runtime)              │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │ │
│  │  │ Execution   │  │ System      │  │ Account     │    │ │
│  │  │ Engine      │  │ Monitor     │  │ Manager     │    │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘    │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │ │
│  │  │ Risk        │  │ Signal      │  │ Data        │    │ │
│  │  │ Watcher     │  │ Generator   │  │ Handler     │    │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘    │ │
│  └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    System Kernel (Kernel)               │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │ │
│  │  │ System      │  │ Strategy    │  │ Event       │    │ │
│  │  │ Calls       │  │ Scheduler   │  │ Bus         │    │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘    │ │
│  └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                  Exchange Drivers (Drivers)             │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │ │
│  │  │   OKX       │  │  Backpack   │  │  Binance    │    │ │
│  │  │   Driver    │  │   Driver    │  │   Driver    │    │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘    │ │
│  └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                    Data Storage (Storage)               │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │ │
│  │  │ Logging     │  │ Data Feed   │  │ Storage     │    │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘    │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 🔄 Data Flow
1. **Strategy** → **Execution Engine** → **System Calls** → **Exchange Driver** → **Exchange API**
2. **Exchange API** → **Exchange Driver** → **System Calls** → **Execution Engine** → **System Monitor**
3. **System Monitor** → **Anomaly Detection** → **Auto Correction** → **Execution Engine** → **Exchange Driver**

---

## 🌟 System Features

### 🔥 Core Functions
- **Unified Trading Interface** - One API supports OKX, Backpack, Binance exchanges
- **Dynamic Account Management** - Support multi-account switching, auto-mapping based on configuration
- **Smart Position Monitoring** - Precise monitoring based on quantityUSD, supports auto-correction
- **Multi-dimensional Anomaly Detection** - Comprehensive monitoring of price, position, profit, risk
- **Auto-correction Mechanism** - Automatically place orders to correct anomalies when detected
- **Complete Logging System** - Structured logs, operation records, anomaly reports

### 🛡️ Security Features
- **Risk Control** - Built-in risk management module, supports multiple risk indicator monitoring
- **Account Isolation** - Independent multi-account management, avoids cross-contamination
- **Operation Audit** - Complete operation records and anomaly tracking
- **Auto Circuit Breaker** - Automatically stop trading in case of anomalies

### 🚀 Performance Features
- **High Precision Calculation** - Unified handling of precision differences across exchanges
- **Smart Order Placement** - Automatic handling of price and quantity precision conversion
- **Incremental Trading** - Support incremental order placement, avoiding duplicate operations
- **Real-time Monitoring** - Support continuous monitoring and scheduled tasks

---

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
   Clone the repository:

   ```bash
   git clone https://github.com/CryptoFxxker/CTOS.git
   cd ctos
   ```

2. **Set Up the Environment**

   ```bash
   conda create -n ctos python=3.10 -y
   conda activate ctos
   pip install -U pip
   pip install -r requirements.txt
   ```

3. **Configure API Keys**

   ```bash
   cp configs/secrets.example.yaml configs/account.yaml
   ```

   Fill in **OKX / Backpack / Binance** API Keys

   ### 3.1 Test Cases (Optional)

   To verify environment and API Key configuration, run the built-in test script:

     ```bash
   python configs/example_usage.py
   ```

   This script will automatically test order placement on OKX and Backpack exchanges for mainstream coins and output results. Recommended to run first during initial deployment to ensure everything is working properly.
   > ⚠️ Do not commit this file to git

4. **Run Built-in Strategies**

   ```bash
   # Run all-coin grid strategy
   python apps/strategies/grid/Grid-All-Coin.py
   
   # Or run other strategies
   python apps/strategies/examples/your_strategy.py
   ```

   Strategies will automatically use ExecutionEngine and SystemMonitor for execution and monitoring.

6. **Backtest/Replay@TODO** 
   Place historical data in `tools/backtest/`, then:

     ```bash
     ./scripts/backtest.sh
     ```

   Results will be written to `var/logs/` and stored in `var/data/`.

👉 The flow is clear: **get code → install environment → fill API keys → configure → live deployment**


## Roadmap

* **v0.1**
  System call specification; exchange drivers (OKX/Backpack/Binance) skeleton; runtime scheduling; simulated trading

* **v0.2**
  Unified WebSocket data stream; consistency between backtesting and simulation; richer risk control modules

* **v0.3**
  Multi-exchange portfolio net asset management; real-time failover; hot restart; stronger indicators and UI

* **🎉 Milestone 1 (2025.09.17)**
  ✅ Completed unified API design and abstraction for 2 exchanges.
  🚀 Achieved a significant milestone today: **AI-driven, system-call-based grid strategy code** has been generated, fine-tuned, and officially deployed!
  🥂🎊 Cheers to this launch — onward to the next stage!

* **🎉 Milestone 2 (2025.09.)**
  ✅ Completed precise position monitoring system based on quantityUSD
  ✅ Implemented multi-dimensional anomaly detection (price, position, profit, risk)
  ✅ Completed auto-correction mechanism, supports automatic position anomaly repair
  ✅ Implemented complete logging system and data persistence
  ✅ Supports OKX, Backpack, Binance three major exchanges
  🚀 System is ready for production environment deployment!
  🥂🎊 Cheers to this launch — onward to the next stage!

---

## Security & Compliance

* **Principle of Least Privilege:** API keys should only have necessary trading permissions; withdrawal must always remain disabled.
* **Key Security:** Use `configs/secrets.yaml` (excluded from version control), or system key management, environment variables.
* **Risk Controls First:** Pre-trade checks, circuit breakers, kill-switch, rate limiting and logging.
* **Reproducible Backtests:** All strategy inputs/outputs and market snapshots must be replayable.

---

## License & Disclaimer

* **Disclaimer:** Cryptocurrency trading carries extremely high risk. CTOS is provided as a research/tooling framework; please assess risks and take responsibility yourself.
* **License:** Choose your preferred license (MIT / Apache-2.0 / GPL-3.0) and specify it clearly in the `LICENSE` file.

