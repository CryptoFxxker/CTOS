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

## Quick Start

1. **Generate the project**

   ```bash
   python3 scaffold_ctos.py --name ctos --exchanges okx backpack binance
   ```

2. **Install deps (example)**

   ```bash
   cd ctos
   python -m venv .venv && source .venv/bin/activate
   pip install -U pip
   # add your libs later (httpx/websockets/pandas/pyyaml/uvloop/...)
   ```

3. **Configure**

   * Copy `configs/secrets.example.yaml` → `configs/secrets.yaml`, fill API keys **(never commit)**.
   * Edit `configs/ctos.yaml` to pick default exchange, mode (`paper` / `live`), log level, etc.

4. **Run a demo strategy (paper/sim)**

   ```bash
   python -m apps.strategies.examples.mean_reversion
   ```

5. **Backtest / Replay**

   * Put historical data into `tools/backtest/` or wire a loader.
   * Run `scripts/backtest.sh` (or your own command).

---

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

# Scaffold Script

Save as `scaffold_ctos.py` (run from the parent directory where you want the project created):

```python
#!/usr/bin/env python3
"""
CTOS Project Scaffold
Creates a Linux-inspired crypto trading OS layout with exchange-specific "arch" drivers.
Usage:
  python scaffold_ctos.py --name ctos --exchanges okx backpack binance
"""

import argparse
import os
from pathlib import Path
import textwrap
import yaml  # optional; if not installed, replace with simple string write

README_CN_EN = """# CTOS: Crypto Trading Operating System (Linux-inspired)

> Bilingual README is placed here as a stub.
> Replace this file with your current README content from the chat.
> (Or keep this and append.)

See configs/ctos.yaml and configs/secrets.example.yaml to get started.
"""

GITIGNORE = """# Python
__pycache__/
*.py[cod]
*.pyo
*.egg-info/
.venv/
.env
.ipynb_checkpoints/

# OS
.DS_Store

# Data & Logs
data/
logs/
tmp/
"""

CTOS_YAML = {
    "mode": "paper",  # paper | live
    "default_exchange": "okx",
    "log_level": "INFO",
    "data": {"store": "parquet", "path": "data/"},
    "risk": {
        "max_notional_usd": 10000,
        "max_leverage": 3,
        "price_band_bps": 200,  # 2%
        "kill_switch": True,
    },
    "exchanges": {
        "okx": {"account": "default_okx"},
        "binance": {"account": "default_binance"},
        "backpack": {"account": "default_backpack"},
    },
    "accounts": {
        "default_okx": {"keyref": "okx_main"},
        "default_binance": {"keyref": "binance_main"},
        "default_backpack": {"keyref": "backpack_main"},
    },
}

SECRETS_EXAMPLE = {
    "keys": {
        "okx_main": {
            "api_key": "YOUR_OKX_KEY",
            "api_secret": "YOUR_OKX_SECRET",
            "passphrase": "YOUR_OKX_PASSPHRASE"
        },
        "binance_main": {
            "api_key": "YOUR_BINANCE_KEY",
            "api_secret": "YOUR_BINANCE_SECRET"
        },
        "backpack_main": {
            "api_key": "YOUR_BACKPACK_KEY",
            "api_secret": "YOUR_BACKPACK_SECRET"
        }
    }
}

SYSCALLS_PY = '''"""
Canonical trading syscall spec for CTOS drivers.
Each driver must implement these methods with consistent shapes.
"""

from typing import Any, Dict, Iterable, Optional

class TradingSyscalls:
    def symbols(self) -> Iterable[str]: ...
    def exchange_limits(self) -> Dict[str, Any]: ...
    def fees(self) -> Dict[str, Any]: ...

    # Market data
    def subscribe_ticks(self, symbols): ...
    def subscribe_klines(self, symbol: str, timeframe: str): ...
    def get_orderbook(self, symbol: str, level: int = 50): ...

    # Trading
    def place_order(self, symbol: str, side: str, ord_type: str,
                    size: float, price: Optional[float] = None,
                    client_id: Optional[str] = None, **kwargs) -> Dict[str, Any]: ...
    def amend_order(self, order_id: str, **kwargs) -> Dict[str, Any]: ...
    def cancel_order(self, order_id: str) -> Dict[str, Any]: ...
    def cancel_all(self, symbol: Optional[str] = None) -> Dict[str, Any]: ...

    # Account
    def balances(self) -> Dict[str, float]: ...
    def positions(self) -> Dict[str, Any]: ...
    def transfer(self, **kwargs) -> Dict[str, Any]: ...
'''

DRIVER_INIT = '''"""
Exchange driver package.
Implement arch.yaml + rest.py + ws.py + signer.py according to CTOS syscalls.
"""
'''

DRIVER_ARCH_YAML = {
    "arch": "REPLACE_ME",              # e.g., okx / binance / backpack
    "kind": "cex",
    "features": {
        "modes": ["spot", "swap"],
        "order_types": ["limit", "market", "post_only"],
        "time_in_force": ["GTC", "IOC", "FOK"],
        "ws_streams": ["tick", "kline", "orderbook", "orders", "balances"],
    },
    "limits": {
        "price_scale": 1e-8,
        "size_scale": 1e-8
    }
}

REST_PY = '''"""
REST adapter for this exchange.
Responsibilities:
- Normalize requests & responses to CTOS syscall contracts
- Handle authentication/signature
- Respect rate limits & idempotency
"""
class RestClient:
    def __init__(self, config, secrets):
        self.config = config
        self.secrets = secrets

    # TODO: implement REST calls (symbols, place_order, cancel_order, balances, etc.)
'''

WS_PY = '''"""
Websocket adapter for this exchange.
Responsibilities:
- Connect, subscribe, and normalize streams (ticks/klines/orderbook/orders/balances)
- Auto-reconnect & backoff
"""
class WsClient:
    def __init__(self, config, secrets):
        self.config = config
        self.secrets = secrets

    # TODO: implement WS subscriptions and message normalization
'''

SIGNER_PY = '''"""
Request signer/authorizer for this exchange.
- HMAC/Ed25519 etc. depending on the exchange
"""
class Signer:
    def __init__(self, secrets):
        self.secrets = secrets

    # TODO: implement sign(payload) -> headers/params
'''

MEAN_REV_PY = '''"""
Minimal example strategy (pseudo-code):
- Subscribes to klines
- Places tiny paper orders when a simple condition triggers
"""
def main():
    print("Example strategy would run here and call TradingSyscalls.")

if __name__ == "__main__":
    main()
'''

SCHEDULER_PY = '''"""
Simple placeholder scheduler (supervisor/orchestrator).
"""
class Scheduler:
    def start(self):
        print("Scheduler starting...")

    def stop(self):
        print("Scheduler stopping...")
'''

EVENT_BUS_PY = '''"""
Trivial event bus placeholder (pub/sub).
Replace with a real bus or use asyncio signals.
"""
class EventBus:
    def publish(self, topic, message):
        pass

    def subscribe(self, topic, handler):
        pass
'''

RISK_PY = '''"""
Pre-trade risk checks and kill-switch.
"""
class Risk:
    def check(self, order):
        # TODO: implement price bands, max notional, leverage caps
        return True
'''

PORTFOLIO_PY = '''"""
Positions & PnL accounting.
"""
class Portfolio:
    pass
'''

EXEC_ENGINE_PY = '''"""
Execution engine dispatches strategy intents to driver syscalls.
"""
class ExecutionEngine:
    def __init__(self, driver):
        self.driver = driver

    # def place(order): call driver.place_order(...)
'''

def write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def write_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    except Exception:
        # fallback to plain string if pyyaml missing
        import json
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def scaffold(base: Path, exchanges: list[str]):
    # Root files
    write_text(base / "README.md", README_CN_EN)
    write_text(base / ".gitignore", GITIGNORE)
    write_yaml(base / "configs" / "ctos.yaml", CTOS_YAML)
    write_yaml(base / "configs" / "secrets.example.yaml", SECRETS_EXAMPLE)

    # Core package
    write_text(base / "ctos" / "__init__.py", "'''CTOS package'''")
    write_text(base / "ctos" / "core" / "kernel" / "syscalls.py", SYSCALLS_PY)
    write_text(base / "ctos" / "core" / "kernel" / "scheduler.py", SCHEDULER_PY)
    write_text(base / "ctos" / "core" / "kernel" / "event_bus.py", EVENT_BUS_PY)
    write_text(base / "ctos" / "core" / "runtime" / "execution_engine.py", EXEC_ENGINE_PY)
    write_text(base / "ctos" / "core" / "runtime" / "risk.py", RISK_PY)
    write_text(base / "ctos" / "core" / "runtime" / "portfolio.py", PORTFOLIO_PY)

    # IO subdirs
    (base / "ctos" / "core" / "io" / "datafeed").mkdir(parents=True, exist_ok=True)
    (base / "ctos" / "core" / "io" / "storage").mkdir(parents=True, exist_ok=True)
    (base / "ctos" / "core" / "io" / "logging").mkdir(parents=True, exist_ok=True)

    # Drivers
    for ex in exchanges:
        ex = ex.lower()
        write_text(base / "ctos" / "drivers" / ex / "__init__.py", DRIVER_INIT)
        arch_yaml = DRIVER_ARCH_YAML.copy()
        arch_yaml["arch"] = ex
        write_yaml(base / "ctos" / "drivers" / ex / "arch.yaml", arch_yaml)
        write_text(base / "ctos" / "drivers" / ex / "rest.py", REST_PY)
        write_text(base / "ctos" / "drivers" / ex / "ws.py", WS_PY)
        write_text(base / "ctos" / "drivers" / ex / "signer.py", SIGNER_PY)

    # Apps / tools / scripts / tests
    write_text(base / "apps" / "strategies" / "examples" / "mean_reversion.py", MEAN_REV_PY)
    (base / "tools" / "backtest").mkdir(parents=True, exist_ok=True)
    (base / "tools" / "simulator").mkdir(parents=True, exist_ok=True)
    (base / "scripts").mkdir(parents=True, exist_ok=True)
    (base / "tests").mkdir(parents=True, exist_ok=True)

def print_next_steps(base: Path):
    steps = f"""
✅ CTOS scaffold created at: {base}

Next steps:
1) cd {base.name}
2) python -m venv .venv && source .venv/bin/activate
3) pip install pyyaml
4) Edit configs/ctos.yaml and copy configs/secrets.example.yaml → configs/secrets.yaml
5) Run example: python -m apps.strategies.examples.mean_reversion
"""
    print(textwrap.dedent(steps))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="ctos", help="Project folder name")
    parser.add_argument("--exchanges", nargs="+", default=["okx", "backpack", "binance"],
                        help="List of exchanges (treated as arch drivers)")
    args = parser.parse_args()

    base = Path(args.name).resolve()
    scaffold(base, args.exchanges)
    print_next_steps(base)

if __name__ == "__main__":
    main()
```

> If you don’t want to install `pyyaml`, the script already falls back to JSON text for YAML writes.

---
