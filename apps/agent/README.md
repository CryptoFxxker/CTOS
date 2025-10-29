# AI 自动交易系统

基于 LLM 的智能加密货币交易系统，使用 DeepSeek-R1 模型生成交易策略。

[English](README_EN.md) | [中文](README.md)

## 功能特性

- 🤖 **AI 策略生成** - 使用 DeepSeek-R1 模型分析市场并生成交易策略
- 📊 **实时数据** - 从交易所获取最新的市场数据和行情
- ⚡ **自动执行** - 自动执行买卖订单，24/7 运行
- 🛡️ **风险控制** - 内置止损止盈、单日亏损限制、仓位管理
- 🔧 **灵活配置** - 支持环境变量和配置文件两种方式

## 架构设计

### 模块化结构

```
apps/agent/
├── main.py              # 主程序（调度所有模块）
├── ai_strategist.py     # AI 策略师（生成交易策略）
├── data_fetcher.py      # 数据获取（获取市场数据）
├── executor.py          # 执行器（执行买卖订单）
├── risk_manager.py      # 风险管理（控制交易风险）
├── config_manager.py    # 配置管理（管理配置文件）
├── ollama_client.py     # Ollama 客户端
└── test_*.py            # 测试文件
```

### 模块说明

#### AI 策略师 (`ai_strategist.py`)
- 使用 DeepSeek-R1 生成交易策略
- 基于市场数据生成买卖决策
- 包含信心度评估

#### 数据获取 (`data_fetcher.py`)
- 从交易所获取实时行情
- K线数据获取
- 趋势分析
- ⚠️ **TODO**: 需要对接实际交易所API

#### 执行器 (`executor.py`)
- 执行买卖订单
- 查询余额和持仓
- ⚠️ **TODO**: 需要对接实际的交易系统

#### 风险管理 (`risk_manager.py`)
- 控制单次交易金额
- 止损止盈逻辑
- 单日亏损限制

## 快速开始

### 1. 环境变量设置

```bash
# 设置 Ollama 服务器（无需 http:// 前缀，会自动添加）
export OLLAMA_BASE_URL="localhost:11434"
export OLLAMA_MODEL="deepseek-r1:32b"

# 设置交易所和账户
export EXCHANGE="okx"
export ACCOUNT_ID="0"
export SYMBOL="BTC/USDT"
```

### 2. 运行系统

```bash
# 启动交易系统
cd apps/agent
python main.py
```

### 3. 配置文件（可选）

创建 `ai_trading_config.json`:

```json
{
  "symbol": "BTC/USDT",
  "exchange": "okx",
  "account_id": 0,
  "risk": {
    "max_position_size": 1000,
    "max_daily_loss": 500,
    "stop_loss_percent": 0.05,
    "take_profit_percent": 0.10
  },
  "ai": {
    "model": "deepseek-r1:32b"
  },
  "trading": {
    "enabled": true,
    "min_confidence": 0.5
  }
}
```

## 工作流程

```
1. 获取市场数据 (DataFetcher)
   ↓
2. AI 分析并生成策略 (AIStrategist)
   ↓
3. 风险检查 (RiskManager)
   ↓
4. 执行交易 (Executor)
   ↓
5. 更新持仓
   ↓
6. 等待下一个周期
```

## 配置选项

### Ollama 客户端

系统使用 Ollama 客户端与 DeepSeek-R1 模型交互，支持代理配置：

```python
from ollama_client import OllamaClient

# 不使用代理（默认）
client = OllamaClient(use_proxy=False)

# 使用代理
client = OllamaClient(use_proxy=True)
```

详细使用方法请参考 `ollama_client.py` 和测试文件。

## 使用示例

### 基础使用

```python
from main import AITradingSystem

# 创建系统
system = AITradingSystem()

# 启动
system.start()
```

### 自定义配置

```python
from ai_strategist import AIStrategist
from data_fetcher import DataFetcher
from executor import Executor
from risk_manager import RiskManager

# 初始化各模块
ai = AIStrategist()
data = DataFetcher(exchange='okx')
executor = Executor(exchange='okx', account_id=0)
risk = RiskManager(max_position_size=2000)

# 手动执行一个周期
market_data = data.get_market_data('BTC/USDT')
strategy = ai.generate_strategy(market_data)
risk_check = risk.check_risk(strategy)

if risk_check['allowed']:
    result = executor.execute_order(
        symbol='BTC/USDT',
        action=strategy['action'],
        amount=risk_check['adjusted_amount']
    )
```

## 待完成功能

### 数据获取模块
- [ ] 对接交易所实时行情API
- [ ] 实现K线数据获取
- [ ] 技术指标计算
- [ ] 订单簿深度分析

### 执行器模块
- [ ] 对接已有交易系统
- [ ] 实现实际订单执行
- [ ] 订单状态查询
- [ ] 持仓管理

### 其他功能
- [ ] 策略回测
- [ ] 历史数据记录
- [ ] 性能监控
- [ ] 邮件/短信通知

## 测试

```bash
# 运行完整测试套件
python ollama_client.py

# 运行连接测试
python test_connection.py

# 运行聊天测试
python test_chat.py
```

## 风险提示

⚠️ **重要提醒**：

1. 本系统仅用于研究和学习目的
2. 实盘交易有风险，请谨慎使用
3. 建议先在模拟环境测试
4. 设置合理的止损止盈
5. 控制单次交易金额
6. 定期监控系统运行状态

## 技术栈

- Python 3.10+
- DeepSeek-R1 LLM
- Okx 交易所 API
- CTOS 交易框架

---

**注意**：系统从环境变量读取配置，请设置 `OLLAMA_BASE_URL` 环境变量指向你的 Ollama 服务器。
