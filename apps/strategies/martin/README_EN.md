# Simplified Single-Coin Martingale Strategy System

> **Language / 语言**: [简体中文](README.md) | [English](README_EN.md)

![Strategy Diagram](image.png)

## System Overview

This is a highly simplified single-coin Martingale strategy system that integrates all functions (strategy execution, management, monitoring) into one file, supporting parallel management of multiple coins, multiple exchanges, and multiple accounts.

## Core Features

### 🎯 Simplified Design
- **Single-File System**: All functions integrated in `SimpleMartinSystem.py`
- **Engine Reuse**: Multiple coins of the same exchange+account share one engine
- **Configuration Driven**: Manage all parameters through `simple_martin_config.json`
- **Real-time Management**: Support adding, deleting, enabling/disabling strategies during runtime
- **Status Monitoring**: Rotating print of strategy status, real-time view of positions and P&L
- **Data Persistence**: Orders and parameters automatically saved, auto-recover after restart

### 🏗️ Architecture Advantages
- **Engine Reuse**: Coins of the same exchange+account share engine instances
- **Pre-initialization**: Pre-initialize all needed engines at system startup, avoiding repeated creation
- **Smart Management**: Automatically detect engine requirements, automatically disable related strategies on failure
- **Modular Class**: `SimpleMartinSystem` class encapsulates all functions
- **Thread Safe**: Strategy execution runs in independent threads
- **Exception Handling**: Comprehensive error handling and recovery mechanisms

## File Structure

```
apps/strategies/martin/
├── SimpleMartinSystem.py      # Main system file (integrated all functions)
├── simple_martin_config.json  # Configuration file
└── simplified_martin_strategy_doc.md  # This document
```

## Quick Start

### 1. Start System
```bash
python SimpleMartinSystem.py
```

### 2. Basic Operations
- **Start Strategy**: Select option 1 to start all enabled strategies (auto-initialize engines)
- **Add Strategy**: Select option 4 to add new coin strategy (auto-initialize new engine)
- **View Status**: Select option 7 to view system running status
- **View Engines**: Select option 8 to view engine initialization status
- **Re-initialize**: Select option 9 to re-initialize all engines
- **Manage Strategies**: Select options 3, 5, 6 for strategy management

## Configuration

### Strategy Configuration
```json
{
  "coin": "ETH",                    // Coin
  "exchange": "bp",                 // Exchange
  "account_id": 0,                  // Account ID
  "base_amount": 50.0,              // Base order amount (USDT)
  "martin_multiplier": 1.5,         // Martingale multiplier
  "max_positions": 8,               // Maximum position layers
  "add_position_rate": 0.05,        // Add position rate (5%)
  "reduce_position_rate": 0.1,      // Reduce position rate (10%)
  "stop_loss_rate": 0.3,            // Stop loss rate (30%)
  "enabled": true                   // Enable status
}
```

### Global Settings
```json
{
  "monitor_interval": 30,           // Monitor interval (seconds)
  "status_print_interval": 3,       // Status print interval (print every N cycles)
  "emergency_stop": false,          // Emergency stop
  "log_level": "INFO"               // Log level
}
```

## Core Functions

### 1. Strategy Execution
- **Martingale Strategy**: Layer-by-layer position adding on price drops, each layer amount increases by Martingale multiplier
- **Risk Control**: Built-in stop loss, take profit, maximum position layers limit
- **Real-time Monitoring**: Continuous monitoring of price changes and strategy status

### 2. Engine Management
- **Smart Reuse**: Coins of the same exchange+account share engine instances
- **Auto Initialization**: Automatically create engine on first use
- **Exception Handling**: Automatically skip when engine creation fails

### 3. Strategy Management
- **Dynamic Add**: Add new coin strategy during runtime
- **Dynamic Delete**: Delete unneeded strategies during runtime
- **Status Control**: Enable/disable strategies anytime
- **Lifecycle Management**: Each strategy controlled by `enabled` field

### 4. Data Persistence
- **Auto Save**: Automatically save after each order operation (add position, reduce position, stop loss)
- **Parameter Recovery**: All strategy parameters (base amount, Martingale multiplier, max layers, etc.) fully saved
- **Order Recovery**: All order information (price, quantity, P&L, timestamp) persistently saved
- **State Recovery**: Automatically recover all strategy status and order data on system startup
- **Save Timing**:
  - After each successful position adding
  - After each position reducing
  - On stop loss trigger
  - After each strategy execution loop
  - On system exit

### 5. Risk Control
- **Multi-layer Protection**: Strategy-level and system-level risk control
- **Emergency Stop**: Global emergency stop mechanism
- **Auto Stop Loss**: Automatically stop when loss exceeds set ratio

## Usage Examples

### Add ETH Strategy
1. Start system: `python SimpleMartinSystem.py`
2. Select option 4: Add strategy
3. Enter parameters:
   - Coin: ETH
   - Exchange: bp
   - Account ID: 0
   - Base Amount: 50

### Add BTC Strategy to Same Account
1. Select option 4: Add strategy
2. Enter parameters:
   - Coin: BTC
   - Exchange: bp
   - Account ID: 0
   - Base Amount: 100

**Note**: BTC and ETH will share the same bp-0 engine instance.

### Add Different Exchange Strategy
1. Select option 4: Add strategy
2. Enter parameters:
   - Coin: SOL
   - Exchange: okx
   - Account ID: 1
   - Base Amount: 30

**Note**: This will create a new okx-1 engine instance.

## Strategy Logic

### Martingale Strategy Flow
1. **First Position**: Establish first layer position with base amount at strategy start
2. **Price Monitoring**: Continuously monitor coin price changes
3. **Add Position Trigger**: Trigger position adding when price drops beyond set ratio
4. **Amount Increase**: Each layer position amount increases by Martingale multiplier
5. **Reduce Position & Take Profit**: Reduce position when total profit exceeds set ratio
6. **Stop Loss Protection**: Stop strategy when total loss exceeds set ratio

### Risk Control Mechanism
- **Maximum Position Layers**: Prevent unlimited position adding
- **Stop Loss Mechanism**: Automatically stop when loss exceeds 30%
- **Take Profit Mechanism**: Reduce position when profit exceeds 10%
- **Emergency Stop**: Globally emergency stop all strategies

## Engine Management Mechanism

### Pre-initialization Mechanism
- **Initialize at Startup**: Pre-initialize all needed engines at system startup
- **Smart Detection**: Automatically detect engine requirements for all enabled strategies
- **Failure Handling**: Automatically disable related strategies when engine initialization fails
- **Status Tracking**: Real-time tracking of engine initialization status

### Reuse Rules
- **Key**: `{exchange}_{account_id}`
- **Reuse Condition**: Same exchange + same account ID
- **Independent Engines**: Different exchanges or different account IDs use independent engines

### Examples
```python
# The following strategies will share the same engine
{"coin": "ETH", "exchange": "bp", "account_id": 0}
{"coin": "BTC", "exchange": "bp", "account_id": 0}
{"coin": "SOL", "exchange": "bp", "account_id": 0}

# The following strategies will use different engines
{"coin": "ETH", "exchange": "okx", "account_id": 0}  # New engine
{"coin": "ETH", "exchange": "bp", "account_id": 1}   # New engine
```

### Engine Management Functions
- **View Engine Status**: Display all initialized engines
- **Re-initialize**: Re-initialize engines when configuration changes
- **Auto Management**: Automatically initialize required engines when adding new strategies

## Monitoring and Logging

### Real-time Monitoring
- **Price Display**: Real-time display of current price for each coin
- **Position Status**: Display current position layers
- **P&L Statistics**: Real-time calculation and display of total P&L
- **Strategy Status**: Display strategy enabled/disabled status

### Rotating Strategy Status Print
System automatically prints detailed status of all strategies periodically, including:
- Strategy active status (🟢 with position/⚪ no position)
- Current price and position layers
- Invested capital and total P&L (with percentage)
- Detailed position information (each layer price, amount, P&L)

**Sample Output**:
```
================================================================================
📊 Strategy Status Report - 2024-01-15 14:30:25
================================================================================

🟢 [ETH] [bp-0]
   Current Price:   2500.2345 | Position Layers:  3/ 8
   Invested Capital:  175.00 USDT
   📈 Total P&L:      +12.50 USDT ( +7.14%)
   Position Details:
      Layer 1: Price=  2500.0000, Amount=  50.00, P&L=  +0.12 ( +0.24%)
      Layer 2: Price=  2375.0000, Amount=  75.00, P&L=  +7.89 ( +10.52%)
      Layer 3: Price=  2256.2500, Amount=  50.00, P&L=  +4.49 (  +8.98%)

⚪ [BTC] [okx-1]
   Current Price:   42000.0000 | Position Layers:  0/ 6
   Invested Capital:    0.00 USDT
   📊 Total P&L:      +0.00 USDT (  +0.00%)

================================================================================
```

Adjust printing frequency through `status_print_interval` configuration parameter:
- Set to 1: Print every cycle (most detailed)
- Set to 3: Print every 3 cycles (default)
- Set to 10: Print every 10 cycles (less output)

### Log Output
- **Operation Logs**: Record all strategy operations
- **Error Logs**: Record exceptions and errors
- **Status Logs**: Record strategy status changes

## Risk Warnings

### ⚠️ Important Risks
1. **Martingale Strategy Risk**: May cause significant losses in long-term downtrends
2. **Leverage Risk**: Using leverage amplifies gains and losses
3. **Liquidity Risk**: May not be able to close positions in time when market liquidity is insufficient
4. **Technical Risk**: System failures may cause unexpected losses

### 🛡️ Risk Control Recommendations
1. **Reasonable Parameter Settings**: Martingale multiplier should not exceed 2.0, maximum position layers should not exceed 10
2. **Set Stop Loss**: Stop loss ratio recommended not to exceed 30%
3. **Diversify Investment**: Don't invest all capital into a single strategy
4. **Regular Monitoring**: Regularly check strategy status and risk level
5. **Set Emergency Stop**: Stop strategy promptly in exceptional circumstances

## FAQ

### Q: How to add new exchange support?
A: System automatically supports configured exchanges, no additional setup needed.

### Q: How to adjust strategy parameters?
A: You can directly edit the configuration file, or adjust online through system menu.

### Q: What to do when strategy has exceptions?
A: System will automatically handle exceptions, exceptional strategies will be marked as disabled.

### Q: How to backup strategy data?
A: Simply backup the `simple_martin_config.json` file.

### Q: What are the benefits of engine reuse?
A: Reduces resource consumption, improves execution efficiency, avoids repeated initialization.

### Q: Will strategy status be lost after system restart?
A: No. All order information, strategy parameters and status are automatically saved to configuration file, auto-recover after restart.

### Q: How to adjust status printing frequency?
A: Modify the `status_print_interval` parameter in configuration file, the value indicates how many cycles between prints.

### Q: Will configuration file be overwritten?
A: Configuration is automatically saved after each key operation to ensure no data loss. System automatically loads last saved status on startup.

## System Advantages

### 1. Highly Simplified
- Single file contains all functions
- No complex module dependencies
- Easy to deploy and maintain

### 2. Efficient Execution
- Engine reuse reduces resource consumption
- Multiple strategies execute in parallel
- Asynchronous monitoring and operations

### 3. Flexible Management
- Dynamic strategy management during runtime
- Real-time status monitoring
- Comprehensive error handling

### 4. Controllable Risk
- Multi-layer risk control mechanisms
- Emergency stop function
- Real-time status monitoring

## Summary

The simplified single-coin Martingale strategy system realizes complete functions of strategy execution, management, and monitoring through single-file integration. The system adopts engine reuse mechanism, improving execution efficiency while maintaining good maintainability and extensibility. Suitable for small to medium-scale quantitative trading needs.

---

**Disclaimer**: This system is for learning and research purposes only and does not constitute investment advice. Users bear all risks of using this system for actual trading.

