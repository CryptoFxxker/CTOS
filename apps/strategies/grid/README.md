# Grid_with_more_gap.py - 动态网格策略

## 📋 概述

`Grid_with_more_gap.py` 是一个基于订单管理的动态网格交易策略，专门设计用于加密货币交易。该策略通过智能订单管理机制，在指定币种上维持动态的买卖网格，实现自动化交易。
## 🛠️ 新手快速上手指南

1. **首次运行自动生成配置文件**
   - 运行 `python Grid_with_more_gap.py`，程序会在 `configs/` 文件夹下自动为每个支持的交易所和账户生成默认配置文件（如 `grid_config_bp_0.json`），然后有一些默认配置需要你确认。
   - 默认情况下，大部分这些配置文件的 `MODE` 字段为 `DEACTIVATED`，表示未激活，有几个已经激活的，你可以确认。。

2. **编辑配置文件，启用策略**
   - 用文本编辑器打开你想启用的配置文件（如 `configs/grid_config_bp_0.json`）。
   - 将 `"MODE": "DEACTIVATED"` 修改为 `"MODE": "ACTIVE"`，并根据需要调整参数（如 `base_amount`, `buy_grid_step`, `sell_grid_step` 等）。
   - 每个配置文件对应一个交易所和账户，支持同时启用多个账户。

3. **参数说明**
   - `exchange`：交易所名称（如 `bp`, `okx`, `bnb`）
   - `account`：账户编号（如 0, 1, 2...）
   - `base_amount`：每次下单的基础金额（单位：USDT）
   - `buy_grid_step`：买单网格倍数（如 0.966 表示比基准价低3.4%）
   - `sell_grid_step`：卖单网格倍数（如 1.018 表示比基准价高1.8%）
   - `buy_move_step`：买单成交后基准价调整倍数
   - `sell_move_step`：卖单成交后基准价调整倍数
   - `MODE`：是否启用该配置（`ACTIVE`/`DEACTIVATED`）

4. **启动策略**
   - 配置好后，直接运行：
     ```
     python Grid_with_more_gap.py
     ```
   - 程序会自动加载所有 `MODE` 为 `ACTIVE` 的配置文件，并为每个账户独立运行网格策略。

5. **首次运行确认**
   - 如果是第一次运行，程序会提示你确认每个配置文件是否启用。按提示输入 `y` 或 `n` 即可。

6. **修改配置生效方式**
   - 修改配置文件后，重启程序即可生效，无需其他操作。

7. **日志与持仓数据**
   - 程序会自动在本地保存操作日志和持仓缓存，无需手动管理。

---

> **温馨提示**：  
> - 不会写代码也能用！只需会编辑配置文件（用记事本/VSCode等打开 `.json` 文件），按需调整参数即可。
> - 每次只需运行 `python Grid_with_more_gap.py`，无需添加命令行参数。
> - 配置文件越多，策略会自动为每个账户独立运行，无需多开进程。

如有疑问，欢迎查看下方“策略特点”和“配置参数”说明，或联系开发者获取帮助。

## 🎯 策略特点

### 核心功能
- **智能订单管理**：基于 `get_open_orders` 的订单状态监控
- **动态网格调整**：成交后自动调整网格位置和价格
- **改单机制**：优先使用改单而非撤单重下，提高执行效率
- **本地缓存**：6小时内自动加载持仓数据，减少API调用
- **多账户支持**：支持同时管理多个交易所账户

### 交易逻辑
- **买单价格**：基准价格 × buy_grid_step (默认0.966，3.4% 折扣)
- **卖单价格**：基准价格 × sell_grid_step (默认1.018，1.8% 溢价)
- **成交调整**：
  - 买单成交 → 基准价格调整至 buy_move_step 倍数 (默认0.99x)
  - 卖单成交 → 基准价格调整至 sell_move_step 倍数 (默认1.01x)
- **动态参数**：所有网格参数可通过配置文件自定义调整

## 🚀 快速开始

### 基本用法

```bash
# 使用配置文件启动（推荐）
python Grid_with_more_gap.py

# 查看帮助
python Grid_with_more_gap.py --help
```

### 配置文件方式
策略现在完全基于配置文件运行，无需命令行参数：

1. **自动创建配置**：首次运行会自动创建默认配置文件
2. **多账户支持**：支持同时配置多个交易所和账户
3. **参数持久化**：所有参数保存在配置文件中

### 支持的交易所
- `bp` - Backpack交易所
- `okx` - 欧易交易所
- `bnb` - 币安交易所

## ⚙️ 配置参数

### 配置文件格式

配置文件位于 `configs/` 文件夹下，命名规则：`configs/grid_config_{exchange}_{account}.json`

示例配置文件：
- `configs/grid_config_bp_0.json` - Backpack账户0
- `configs/grid_config_bp_3.json` - Backpack账户3
- `configs/grid_config_okx_0.json` - OKX账户0

### 配置文件内容

```json
{
  "exchange": "bp",           // 交易所名称 (bp/okx/bnb)
  "account": 0,               // 账户ID (0-6)
  "base_amount": 8.88,        // 基础交易金额 (USDT)
  "force_refresh": false,     // 是否强制刷新缓存
  "buy_grid_step": 0.966,     // 买单网格步长 (基准价格倍数)
  "sell_grid_step": 1.018,   // 卖单网格步长 (基准价格倍数)
  "buy_move_step": 0.99,      // 买单成交后基准价格调整倍数
  "sell_move_step": 1.01,     // 卖单成交后基准价格调整倍数
  "MODE": "ACTIVATED",        // 运行模式 (ACTIVATED/DEACTIVATED)
  "description": "配置说明"    // 配置描述
}
```

### 内置配置

```python
# 默认配置
sleep_time = 1.88   # 循环间隔 (秒)
cache_hours = 6     # 缓存有效期 (小时)
```

## 📊 策略工作流程

### 1. 初始化阶段
```
加载配置文件 → 初始化交易所 → 加载持仓缓存 → 获取关注币种 → 对齐持仓数据
```

### 2. 主循环逻辑
```
获取全局订单 → 检查订单状态 → 执行订单管理 → 更新持仓数据
```

### 3. 订单管理策略

| 订单状态 | 执行动作 | 说明 |
|----------|----------|------|
| 两个订单都不存在 | 下新买单 + 下新卖单 | 初始网格建立 |
| 买单成交，卖单存在 | 下新买单 + 改单现有卖单 | 网格下移 |
| 卖单成交，买单存在 | 改单现有买单 + 下新卖单 | 网格上移 |
| 两个订单都存在 | 等待下一轮 | 网格正常运行 |

## 📁 文件结构

### 输入文件
- `configs/grid_config_{exchange}_{account}.json` - 配置文件（自动创建，最好是仔细检查哈~ ）
- `symbols/{exchange}_Account{account}_focus_symbols.json` - 关注币种列表（自动生成）

### 输出文件
- `GridPositions/{exchange}_Account{account}_{strategy}_GridPositions.json` - 持仓数据缓存

### 文件示例

#### configs/grid_config_bp_0.json
```json
{
  "exchange": "bp",
  "account": 0,
  "base_amount": 8.88,
  "force_refresh": false,
  "buy_grid_step": 0.966,
  "sell_grid_step": 1.018,
  "buy_move_step": 0.99,
  "sell_move_step": 1.01,
  "MODE": "ACTIVATED",
  "description": "Backpack账户0 - 主要交易账户"
}
```

#### symbols/bp_Account0_focus_symbols.json
```json
[
  "BTC-USDT-SWAP",
  "ETH-USDT-SWAP", 
  "BNB-USDT-SWAP",
  "SOL-USDT-SWAP"
]
```

#### GridPositions/bp_Account0_GRID_WITH_MORE_GAP_GridPositions.json
```json
{
  "timestamp": "2025-01-20T10:30:00",
  "exchange": "bp",
  "GridPositions": {
    "BTC-USDT-SWAP": {
      "baseline_price": 45000.0,
      "avg_cost": 44800.0,
      "size": 0.001,
      "side": "long",
      "pnlUnrealized": 15.5,
      "buy_order_id": "12345",
      "sell_order_id": "12346"
    }
  }
}
```

## 🔧 高级配置

### 自定义关注币种

1. **自动模式**：策略会自动从当前持仓中提取币种
2. **手动模式**：编辑 `symbols/{exchange}_Account{account}_focus_symbols.json` 文件

```bash
# 编辑关注币种
vim symbols/bp_Account0_focus_symbols.json
```

### 调整交易参数

```python
# 修改基础交易金额
base_amount = 10.0  # 改为10 USDT

# 修改网格间距（通过配置文件）
"buy_grid_step": 0.97,   # 买单3%折扣
"sell_grid_step": 1.02,  # 卖单2%溢价

# 修改成交后调整幅度
"buy_move_step": 0.98,   # 买单成交后基准价格调整
"sell_move_step": 1.02,  # 卖单成交后基准价格调整
```

## 📈 监控与日志

### 实时监控信息
```
[仓位监控] BTC-USDT-SWAP | Account 0 | Uptime 01:23:45
现价=45000.0 | 起步价=44800.0 | 数量=0.001 | 方向=long | 涨跌幅=+0.45%
```

### 操作日志
- 策略启动/退出记录
- 订单操作记录
- 异常情况记录
- 持仓数据保存记录

## ⚠️ 风险提示

### 使用前须知
1. **资金管理**：确保账户有足够资金支持网格交易
2. **市场风险**：网格策略在单边行情中可能面临较大风险
3. **API限制**：注意交易所API调用频率限制
4. **网络稳定**：确保网络连接稳定，避免订单丢失

### 建议设置
- 单币种最大仓位不超过总资金的20%
- 设置合理的止损机制
- 定期检查策略运行状态
- 保持足够的USDT余额用于下单

## 🛠️ 故障排除

### 常见问题

#### 1. 订单下单失败
```
原因：资金不足、价格精度错误、API限制
解决：检查余额、调整价格精度、降低下单频率
```

#### 2. 持仓数据加载失败
```
原因：缓存文件损坏、网络问题
解决：设置 force_refresh: true 强制刷新
```

#### 3. 币种不支持
```
原因：交易所不支持该交易对
解决：检查币种名称、确认交易对存在
```

### 调试模式

```bash
# 启用详细日志
python Grid_with_more_gap.py --refresh bp 2>&1 | tee grid_log.txt
```

## 📚 技术细节

### 核心函数说明

#### `manage_grid_orders()`
- **功能**：管理单个币种的网格订单
- **参数**：引擎、币种、持仓数据、开放订单、价格精度、数量精度、基础金额
- **返回**：是否更新了订单

#### `get_all_GridPositions()`
- **功能**：获取所有持仓数据，支持本地缓存
- **参数**：引擎、交易所名称、是否使用缓存
- **返回**：持仓数据字典

#### `save_GridPositions()` / `load_GridPositions()`
- **功能**：保存/加载持仓数据到本地文件
- **特性**：自动时间戳检查、交易所匹配验证

## 🔄 版本历史

- **v3.0** - 订单管理版本
  - 基于 `get_open_orders` 的智能订单管理
  - 改单机制优化
  - 本地缓存系统
  - 多账户支持

## 📞 支持与反馈

如有问题或建议，请通过以下方式联系：
- 查看日志文件排查问题
- 检查配置文件设置
- 确认网络连接状态
- 验证API权限设置

---

**免责声明**：本策略仅供学习和研究使用，实际交易存在风险，请谨慎使用并做好风险管理。

## 版本信息
- 版本: 1.0
- 创建时间: 2025.10.24 19:30
- Edited by `Cursor`
- Author [CryptoHunter](https://github.com/CryptoFxxker/CTOS), [DisCord](https://discord.gg/KvqEFMft), [X](https://x.com/Crypto_Fxxker)
- Supported By [`CTOS`](https://github.com/CryptoFxxker/CTOS) 交易框架
