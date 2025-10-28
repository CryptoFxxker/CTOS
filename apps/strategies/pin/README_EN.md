# Pin Catching Strategy 【无敌接针王】

> **Language / 语言**: [简体中文](README.md) | [English](README_EN.md)

![Strategy Diagram](image_en.png)

## Overview

The Pin Catching Strategy is a trading strategy based on order disappearance detection. It places multiple orders above and below the current price to "catch the pin" (capture price fluctuations). When orders are filled, it checks profit margins and decides whether to close positions.

## Strategy Features

- **Pin Catching Mechanism**: Places K orders above and below current price, waiting for price fluctuations to trigger them
- **Intelligent Profit Detection**: Automatically calculates profit after catching, only closing positions when threshold is met
- **Multiple Order Modes**: Supports arithmetic/geometric price distribution, equal amount/equal quantity/increasing quantity modes
- **Resume from Checkpoint**: Supports local caching, can restore state after program restart
- **Multi-Account Support**: Supports running multiple exchanges and accounts simultaneously
- **Auto Refresh**: Regularly cancels and re-places orders to ensure strategy remains effective

## File Structure

```
pin/
├── PinCatchingStrategy.py    # Main strategy file
├── configs/                 # Configuration directory
│   ├── pin_config_bp_0.json
│   ├── pin_config_bp_3.json
│   └── ...
├── PinPositions/           # Position data cache
│   ├── bp_Account0_PINCATCHINGSTRATEGY_PinPositions.json
│   └── ...
└── symbols/                # Focus symbols file
    ├── bp_Account0_focus_symbols.json
    └── ...
```

## Configuration Parameters

Configuration files are located at `configs/pin_config_{exchange}_{account}.json` with the following parameters:

### Basic Parameters
- `exchange`: Exchange name (bp/okx/bnb)
- `account`: Account ID (0-6)
- `MODE`: Activation status (ACTIVATED/DEACTIVATED)

### Order Parameters
- `k_orders`: Number of orders in each direction (default 3)
- `price_gap_pct`: Percentage gap from current price (default 0.01 = 1%)
- `order_gap_pct`: Gap between orders (default 0.005 = 0.5%)
- `gap_type`: Price distribution type (arithmetic/geometric)

### Quantity Parameters
- `size_mode`: Quantity mode (equal_amount/equal_quantity/increasing)
- `base_amount`: Base amount (USDT)
- `base_quantity`: Base quantity
- `increasing_factor`: Increasing factor

### Strategy Parameters
- `profit_threshold`: Profit threshold (default 0.01 = 1%)
- `check_interval`: Check interval in seconds (default 300 = 5 minutes)
- `force_refresh`: Whether to force refresh cache

## Strategy Logic

1. **Initialization**: Load configuration files, get positions, set focus symbols
2. **Order Placement**: Place K orders above and below current price
3. **Monitoring Loop**: 
   - Check order status
   - If pin caught (order disappeared) → Check profit → Close position if threshold met
   - If no pin caught → Regularly cancel and re-place orders
4. **State Saving**: Regularly save position and order status

## Usage

### 1. First Run
```bash
python apps/strategies/pin/PinCatchingStrategy.py
```

First run will:
- Automatically create configuration files
- Prompt to confirm enabling each configuration
- Create focus symbols file

### 2. View Help
```bash
python apps/strategies/pin/PinCatchingStrategy.py --help
```

### 3. Configuration Example

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
  "description": "Pin catching strategy configuration"
}
```

## Strategy Advantages

1. **Risk Control**: Only closes positions when profitable, avoiding losses
2. **Automation**: Fully automatic operation, no manual intervention required
3. **Flexibility**: Supports multiple parameter configurations, adapts to different markets
4. **Stability**: Checkpoint resume design, can recover after program exceptions
5. **Monitoring**: Complete operation logs and status monitoring

## Notes

1. **Capital Management**: Ensure account has sufficient funds to support multiple orders
2. **Parameter Tuning**: Adjust price gaps and profit thresholds according to market volatility
3. **Monitoring**: Regularly check strategy running status and profitability
4. **Risk**: Pin catching strategy carries risk of adverse price movements

## Technical Implementation

- **Order Management**: Based on `get_open_orders` to detect order status
- **Position Management**: Based on `get_position` to get position information
- **Price Calculation**: Supports arithmetic and geometric distribution
- **Cache Mechanism**: Local JSON file caching for position status
- **Exception Handling**: Comprehensive error handling and logging

## Version Information

- Version: 1.0
- Created: 2025.10.24 19:30
- Edited by `Cursor`
- Author [CryptoHunter](https://github.com/CryptoFxxker/CTOS), [DisCord](https://discord.gg/KvqEFMft), [X](https://x.com/Crypto_Fxxker)
- Supported By [`CTOS`](https://github.com/CryptoFxxker/CTOS) Trading Framework

