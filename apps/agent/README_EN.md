# AI Automated Trading System

Intelligent cryptocurrency trading system based on LLM, using DeepSeek-R1 model to generate trading strategies.

[中文](README.md) | [English](README_EN.md)

## Features

- 🤖 **AI Strategy Generation** - Use DeepSeek-R1 model to analyze market and generate trading strategies
- 📊 **Real-time Data** - Get the latest market data and quotes from exchanges
- ⚡ **Auto Execution** - Automatically execute buy/sell orders, running 24/7
- 🛡️ **Risk Control** - Built-in stop loss, take profit, daily loss limit, position management
- 🔧 **Flexible Configuration** - Support both environment variables and config files

## Architecture

### Modular Structure

```
apps/agent/
├── main.py              # Main program (schedules all modules)
├── ai_strategist.py     # AI strategist (generates trading strategies)
├── data_fetcher.py      # Data fetcher (gets market data)
├── executor.py          # Executor (executes buy/sell orders)
├── risk_manager.py      # Risk manager (controls trading risks)
├── config_manager.py    # Config manager (manages configuration)
├── ollama_client.py     # Ollama client
└── test_*.py            # Test files
```

### Module Description

#### AI Strategist (`ai_strategist.py`)
- Use DeepSeek-R1 to generate trading strategies
- Generate buy/sell decisions based on market data
- Includes confidence assessment

#### Data Fetcher (`data_fetcher.py`)
- Get real-time market data from exchanges
- K-line data fetching
- Trend analysis
- ⚠️ **TODO**: Need to integrate with actual exchange API

#### Executor (`executor.py`)
- Execute buy/sell orders
- Query balance and positions
- ⚠️ **TODO**: Need to integrate with actual trading system

#### Risk Manager (`risk_manager.py`)
- Control single trade amount
- Stop loss and take profit logic
- Daily loss limit

## Quick Start

### 1. Environment Variables

```bash
# Set Ollama server (http:// prefix is optional, will be added automatically)
export OLLAMA_BASE_URL="localhost:11434"
export OLLAMA_MODEL="deepseek-r1:32b"

# Set exchange and account
export EXCHANGE="okx"
export ACCOUNT_ID="0"
export SYMBOL="BTC/USDT"
```

### 2. Run System

```bash
# Start trading system
cd apps/agent
python main.py
```

### 3. Configuration File (Optional)

Create `ai_trading_config.json`:

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

## Workflow

```
1. Fetch Market Data (DataFetcher)
   ↓
2. AI Analysis & Generate Strategy (AIStrategist)
   ↓
3. Risk Check (RiskManager)
   ↓
4. Execute Trade (Executor)
   ↓
5. Update Position
   ↓
6. Wait for Next Cycle
```

## Configuration

### Ollama Client

The system uses Ollama client to interact with DeepSeek-R1 model, supports proxy configuration:

```python
from ollama_client import OllamaClient

# No proxy (default)
client = OllamaClient(use_proxy=False)

# With proxy
client = OllamaClient(use_proxy=True)
```

For detailed usage, please refer to `ollama_client.py` and test files.

## Usage Examples

### Basic Usage

```python
from main import AITradingSystem

# Create system
system = AITradingSystem()

# Start
system.start()
```

### Custom Configuration

```python
from ai_strategist import AIStrategist
from data_fetcher import DataFetcher
from executor import Executor
from risk_manager import RiskManager

# Initialize modules
ai = AIStrategist()
data = DataFetcher(exchange='okx')
executor = Executor(exchange='okx', account_id=0)
risk = RiskManager(max_position_size=2000)

# Execute one cycle manually
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

## TODO Features

### Data Fetcher Module
- [ ] Integrate with exchange real-time quotes API
- [ ] Implement K-line data fetching
- [ ] Technical indicators calculation
- [ ] Order book depth analysis

### Executor Module
- [ ] Integrate with existing trading system
- [ ] Implement actual order execution
- [ ] Order status query
- [ ] Position management

### Other Features
- [ ] Strategy backtesting
- [ ] Historical data recording
- [ ] Performance monitoring
- [ ] Email/SMS notifications

## Testing

```bash
# Run full test suite
python ollama_client.py

# Run connection test
python test_connection.py

# Run chat test
python test_chat.py
```

## Risk Warning

⚠️ **Important Notice**:

1. This system is for research and learning purposes only
2. Live trading involves risks, please use with caution
3. Recommend testing in simulation environment first
4. Set reasonable stop loss and take profit
5. Control single trade amount
6. Monitor system running status regularly

## Tech Stack

- Python 3.10+
- DeepSeek-R1 LLM
- Okx Exchange API
- CTOS Trading Framework

---

**Note**: System reads configuration from environment variables. Please set `OLLAMA_BASE_URL` environment variable to point to your Ollama server.
