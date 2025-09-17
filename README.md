🌐 Languages: [English](README_EN.md) | [中文](README.md)

## CTOS：加密交易操作系统（借鉴 Linux 设计理念）

**范围：** 面向中心化交易所（CEX）的量化交易（初期支持 OKX、Backpack、Binance）。
**设计说明：** CTOS 借鉴了 Linux 的理念（架构 arch、驱动 driver、系统调用 syscall、调度器 scheduler、进程 processes），但并非完全复制，而是有选择地吸收适合于构建健壮、可组合、可移植的交易系统的思想。

### 为什么是 CTOS？

* **可移植性：** 通过 **统一的交易系统调用（syscall）** 屏蔽不同交易所的差异。
* **可组合性：** 策略 = “进程”；交易所适配器 = “驱动”；每个交易所 = “架构”。
* **可靠性：** 内核 / 运行时 / 驱动 的分层设计提高了可测试性与安全性。
* **可观测性：** 结构化日志、指标和可复现的回测能力。

---

## 概念映射（Linux → CTOS）

| Linux 概念       | CTOS 对应                                                          | 说明                                                                                     |
| -------------- | ---------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `arch/`        | **交易所架构** (`drivers/okx`, `drivers/binance`, `drivers/backpack`) | 每个交易所一个文件夹，隔离 REST / WS / 签名 / 规格实现。                                                   |
| 设备驱动           | **交易所驱动**                                                        | REST/WS 客户端、签名器、符号映射、功能开关。                                                             |
| 系统调用           | **交易系统调用**                                                       | `place_order`、`cancel_order`、`amend_order`、`balances`、`positions`、`subscribe_ticks` 等。 |
| 调度器            | **策略调度器**                                                        | 协调策略“进程”，处理限速、重试、执行顺序。                                                                 |
| 进程             | **策略**                                                           | 无状态/有状态的策略，调用 syscall，由运行时监督管理。                                                        |
| 文件系统           | **存储层**                                                          | Parquet/SQLite 保存市场数据、成交、标记价格、快照、配置等。                                                  |
| `/proc`        | **指标与运行态信息**                                                     | 健康状态、PnL、风险、延迟、交易所限额、已打开的 websocket。                                                   |
| `init`/systemd | **监督进程**                                                         | 启动模块、重启、隔离崩溃、滚动更新。                                                                     |

---

## 项目目录结构

```
ctos/
├─ README.md
├─ .gitignore
├─ configs/
│  ├─ ctos.yaml                 # 全局配置与开关
│  └─ secrets.example.yaml      # API Key 模板（请勿提交真实密钥）
├─ ctos/
│  ├─ __init__.py
│  ├─ core/
│  │  ├─ kernel/
│  │  │  ├─ syscalls.py         # 系统调用规范
│  │  │  ├─ scheduler.py        # 策略进程调度
│  │  │  └─ event_bus.py        # 事件总线（订单、成交、行情推送）
│  │  ├─ runtime/
│  │  │  ├─ strategy_manager.py # 策略管理：加载/运行/停止
│  │  │  ├─ execution_engine.py # 执行引擎：派发 syscall，重试，幂等
│  │  │  ├─ risk.py             # 风控：下单前检查、节流、Kill-switch
│  │  │  └─ portfolio.py        # 账户与持仓、风险暴露、PnL
│  │  └─ io/
│  │     ├─ datafeed/           # 行情接入与归一化
│  │     ├─ storage/            # Parquet/SQLite 适配
│  │     └─ logging/            # 结构化日志
│  └─ drivers/
│     ├─ okx/
│     │  ├─ __init__.py
│     │  ├─ arch.yaml           # 功能、限制、符号规格
│     │  ├─ rest.py             # REST 适配
│     │  ├─ ws.py               # WebSocket 适配
│     │  └─ signer.py           # 签名与认证
│     ├─ binance/               # 同 okx
│     └─ backpack/              # 同 okx
├─ apps/
│  ├─ strategies/
│  │  └─ examples/
│  │     └─ mean_reversion.py   # 示例策略，调用 syscalls
│  └─ research/
│     └─ notebooks/             # 研究用 Jupyter 笔记
├─ tools/
│  ├─ backtest/                 # 离线回测与重放
│  └─ simulator/                # 延迟、滑点、费用模型
├─ scripts/
│  ├─ run_dev.sh                # 开发环境运行脚本（可选）
│  └─ backtest.sh
└─ tests/                       # 单元与集成测试
```

---

## 交易系统调用（统一接口）

> 每个交易所的 driver 必须实现这些接口；策略只调用 syscall。

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
  - `close_all_positions(symbol=None)`：返回全部或指定交易对的仓位信息

---

### 🎯 CTOS 设计目标（小白友好版）

1. **开箱即用** — 一键启动，无需复杂环境。
   👉 新手也能在几分钟内跑起第一个交易策略。

2. **免写代码** — 内置常见策略。
   👉 “均值回归”、“网格”、“对冲”一条命令就能跑，不会编程也能玩。

3. **多交易所统一接口**
   👉 一个系统同时对接 OKX、Binance、Backpack，不必重复学各种 API。

4. **默认安全保护**
   👉 自带风控和紧急熔断，帮你避免新手常见的大额亏损。

5. **先模拟，后实盘**
   👉 先用“虚拟资金”训练和测试，放心学习，不怕亏钱。

6. **结果可视化**
   👉 自动生成收益、风险、表现的图表报告，让你一眼看懂。

7. **循序渐进学习**
   👉 先用现成策略 → 再改配置参数 → 最后想学编程时自己写。


---

## 运行时与安全性

* **风控关卡：** 下单前检查（价格区间、最大杠杆/名义、最大撤单率）。
* **Kill-switch：** 触发异常 → 策略立即停机、撤单、告警。
* **确定性：** 策略输入输出全记录，可复现回测。
* **可观测性：** 结构化日志 + 指标（延迟、成交、滑点、拒单等）。

---

## 快速开始（实践流程）

1. **获取代码**
   克隆仓库或下载模板：

   ```bash
   git clone https://github.com/your-org/ctos.git
   cd ctos
   ```

   或使用脚手架生成：

   ```bash
   python3 scaffold_ctos.py --name ctos --exchanges okx backpack binance
   cd ctos
   ```

2. **搭建环境**

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -U pip
   pip install -r requirements.txt
   ```

3. **配置 API Key**

   ```bash
   cp configs/secrets.example.yaml configs/secrets.yaml
   ```

   填入 **OKX / Backpack / Binance** 的 API Key

   > ⚠️ 请勿将该文件提交到 git

4. **配置全局参数**
   修改 `configs/ctos.yaml`，选择：

   * `default_exchange`（okx / backpack / binance）
   * `mode`: `paper`（模拟）或 `live`（实盘）
   * 日志、风控参数、数据存储方式

5. **运行内置策略**

   ```bash
   python -m apps.strategies.examples.mean_reversion
   ```

   或运行 `apps/strategies/` 下你自己的策略文件。

6. **回测/重放**
   将历史数据放入 `tools/backtest/`，然后：

   ```bash
   ./scripts/backtest.sh
   ```

   结果会写入 `var/logs/` 并存储在 `var/data/`。

7. **切换实盘（谨慎）**

   * 将 `configs/ctos.yaml` 中的 `mode` 改为 `live`
   * 确保已启用风控与 Kill-switch
   * 再次运行策略 → 会路由到真实交易所

👉 流程一目了然：**获取代码 → 安装环境 → 填 API Key → 配置 → 模拟策略 → 回测 → 实盘上线**

---

## Roadmap

* **v0.1**：syscall 规范，driver（OKX/Backpack/Binance）骨架，运行时调度，模拟交易
* **v0.2**：统一 WS 流，回测与模拟一致性，更丰富的风控模块
* **v0.3**：多交易所投资组合净额管理，实时容灾，热重启，更强的指标与 UI

---

## 安全与合规

* **最小权限**：API Key 仅开通必要权限，提现永远关闭。
* **密钥安全**：使用 `configs/secrets.yaml`（未纳入版本控制），或系统密钥管理、环境变量。
* **风控优先**：下单检查、熔断、Kill-switch、速率与日志留痕。
* **回测可复现**：所有策略输入/输出与行情快照可回放。

---

## 许可与免责声明

* **免责声明**：加密货币交易风险极高。CTOS 仅作为研究与工具框架，请自行评估风险并承担责任。
* **License**：可自行选择（MIT / Apache-2.0 / GPL-3.0），在 `LICENSE` 文件中明确。

