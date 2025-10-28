# 接针策略 (Pin Catching Strategy) 【无敌接针王】

> **Language / 语言**: [简体中文](README.md) | [English](README_EN.md)

![Strategy Diagram](image_cn.png)

## 概述

接针策略是一种基于订单消失检测的交易策略，通过在现价上下布置多个订单来"接针"（捕捉价格波动），当订单被成交时检查盈利情况并决定是否平仓。

## 策略特点

- **接针机制**: 在现价上下布置K个订单，等待价格波动触发
- **智能盈利检测**: 接针后自动计算盈利，达到阈值才平仓
- **多种订单模式**: 支持等差/等比价格分布，等量/等金额/递增数量模式
- **断点重跑**: 支持本地缓存，程序重启后可恢复状态
- **多账户支持**: 支持多交易所多账户同时运行
- **自动刷新**: 定期撤销重下订单，确保策略持续有效

## 文件结构

```
pin/
├── PinCatchingStrategy.py    # 主策略文件
├── configs/                 # 配置文件目录
│   ├── pin_config_bp_0.json
│   ├── pin_config_bp_3.json
│   └── ...
├── PinPositions/           # 持仓数据缓存
│   ├── bp_Account0_PINCATCHINGSTRATEGY_PinPositions.json
│   └── ...
└── symbols/                # 关注币种文件
    ├── bp_Account0_focus_symbols.json
    └── ...
```

## 配置文件说明

配置文件位于 `configs/pin_config_{exchange}_{account}.json`，包含以下参数：

### 基础参数
- `exchange`: 交易所名称 (bp/okx/bnb)
- `account`: 账户ID (0-6)
- `MODE`: 激活状态 (ACTIVATED/DEACTIVATED)

### 订单参数
- `k_orders`: 每个方向K个订单 (默认3)
- `price_gap_pct`: 距离现价的比例差距 (默认0.01 = 1%)
- `order_gap_pct`: 订单之间的gap (默认0.005 = 0.5%)
- `gap_type`: 价格分布类型 (arithmetic/geometric)

### 数量参数
- `size_mode`: 数量模式 (equal_amount/equal_quantity/increasing)
- `base_amount`: 基础金额 (USDT)
- `base_quantity`: 基础数量
- `increasing_factor`: 递增因子

### 策略参数
- `profit_threshold`: 盈利阈值 (默认0.01 = 1%)
- `check_interval`: 检查间隔秒数 (默认300 = 5分钟)
- `force_refresh`: 是否强制刷新缓存

## 策略逻辑

1. **初始化**: 加载配置文件，获取持仓，设置关注币种
2. **订单布置**: 在现价上下各布置K个订单
3. **监控循环**: 
   - 检查订单存活情况
   - 如果接到针（订单消失）→ 检查盈利 → 达到阈值则平仓
   - 如果没接到针 → 定期撤销重下订单
4. **状态保存**: 定期保存持仓和订单状态

## 使用方法

### 1. 首次运行
```bash
python apps/strategies/pin/PinCatchingStrategy.py
```

首次运行会：
- 自动创建配置文件
- 提示确认是否启用各配置
- 创建关注币种文件

### 2. 查看帮助
```bash
python apps/strategies/pin/PinCatchingStrategy.py --help
```

### 3. 配置文件示例

```json
{
  "exchange": "bp",
  "account": 0,
  "k_orders": 3,
  "price_gap_pct": 0.01,
  "order_gap_pct": 0.005,
  "gap_type": "arithmetic",
  "size_mode": "equal_amount",
  "base_amount": 10.0,
  "base_quantity": 0.0,
  "increasing_factor": 1.2,
  "profit_threshold": 0.01,
  "check_interval": 300,
  "force_refresh": false,
  "MODE": "ACTIVATED",
  "description": "接针策略配置"
}
```

## 策略优势

1. **风险控制**: 只在盈利时平仓，避免亏损
2. **自动化**: 全自动运行，无需人工干预
3. **灵活性**: 支持多种参数配置，适应不同市场
4. **稳定性**: 断点重跑设计，程序异常后可恢复
5. **监控**: 完整的操作日志和状态监控

## 注意事项

1. **资金管理**: 确保账户有足够资金支持多订单
2. **参数调优**: 根据市场波动调整价格gap和盈利阈值
3. **监控**: 定期检查策略运行状态和盈利情况
4. **风险**: 接针策略存在价格反向波动的风险

## 技术实现

- **订单管理**: 基于 `get_open_orders` 检测订单状态
- **持仓管理**: 基于 `get_position` 获取持仓信息
- **价格计算**: 支持等差和等比数列分布
- **缓存机制**: 本地JSON文件缓存持仓状态
- **异常处理**: 完善的错误处理和日志记录

## 版本信息

- 版本: 1.0
- 创建时间: 2025.10.24 19:30
- Edited by `Cursor`
- Author [CryptoHunter](https://github.com/CryptoFxxker/CTOS), [DisCord](https://discord.gg/KvqEFMft), [X](https://x.com/Crypto_Fxxker)
- Supported By [`CTOS`](https://github.com/CryptoFxxker/CTOS) 交易框架
