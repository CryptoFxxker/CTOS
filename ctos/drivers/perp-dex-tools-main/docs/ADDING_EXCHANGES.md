# Adding New Exchanges

This document explains how to add support for new exchanges to the modular trading bot.

## Overview

The trading bot has been modularized to support multiple exchanges through a plugin-like architecture. Each exchange is implemented as a separate client that inherits from `BaseExchangeClient`. The bot currently supports EdgeX, Backpack, Paradex, and GRVT exchanges.

## Architecture

```
exchanges/
├── __init__.py          # Module initialization
├── base.py              # Base exchange client interface
├── edgex.py             # EdgeX exchange implementation
├── backpack.py          # Backpack exchange implementation
├── paradex.py           # Paradex exchange implementation
├── aster.py             # Aster exchange implementation
├── factory.py           # Exchange factory for dynamic selection
└── your_exchange.py     # Your new exchange implementation
```

## Steps to Add a New Exchange

### 1. Create Exchange Client

Create a new file `exchanges/your_exchange.py` that implements the `BaseExchangeClient` interface:

```python
import os
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from .base import BaseExchangeClient, OrderResult, OrderInfo, query_retry
from helpers.logger import TradingLogger

class YourExchangeClient(BaseExchangeClient):
    """Your exchange client implementation."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)

        # Initialize your exchange-specific client here
        self.api_key = os.getenv('YOUR_EXCHANGE_API_KEY')
        self.secret_key = os.getenv('YOUR_EXCHANGE_SECRET_KEY')

        # Initialize logger
        self.logger = TradingLogger(exchange="your_exchange", ticker=self.config.ticker, log_to_console=False)

        # Initialize your exchange SDK
        self.client = YourExchangeSDK(self.api_key, self.secret_key)

    def _validate_config(self) -> None:
        """Validate exchange-specific configuration."""
        required_env_vars = ['YOUR_EXCHANGE_API_KEY', 'YOUR_EXCHANGE_SECRET_KEY']
        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {missing_vars}")

    async def connect(self) -> None:
        """Connect to the exchange (WebSocket, etc.)."""
        # Establish connection to your exchange
        await self.client.connect()
        # Wait for connection to establish
        await asyncio.sleep(2)

    async def disconnect(self) -> None:
        """Disconnect from the exchange."""
        # Clean up connections
        await self.client.disconnect()

    def get_exchange_name(self) -> str:
        """Get the exchange name."""
        return "your_exchange"

    def setup_order_update_handler(self, handler) -> None:
        """Setup order update handler for WebSocket."""
        self._order_update_handler = handler
        # Set up WebSocket or polling for order updates
        self.client.setup_order_callback(handler)

    @query_retry(default_return=(0, 0))
    async def fetch_bbo_prices(self, contract_id: str) -> Tuple[Decimal, Decimal]:
        """Fetch best bid and offer prices for a contract."""
        # Implement market data fetching
        order_book = await self.client.get_order_book(contract_id)
        best_bid = Decimal(order_book['bids'][0][0]) if order_book['bids'] else 0
        best_ask = Decimal(order_book['asks'][0][0]) if order_book['asks'] else 0
        return best_bid, best_ask

    async def place_open_order(self, contract_id: str, quantity: Decimal, direction: str) -> OrderResult:
        """Place an open order."""
        try:
            # Get current market prices
            best_bid, best_ask = await self.fetch_bbo_prices(contract_id)

            if direction == 'buy':
                order_price = best_ask - self.config.tick_size
            else:
                order_price = best_bid + self.config.tick_size

            # Place order with your exchange
            order_result = await self.client.place_order(
                symbol=contract_id,
                side=direction,
                quantity=float(quantity),
                price=float(self.round_to_tick(order_price)),
                order_type='LIMIT'
            )

            return OrderResult(
                success=True,
                order_id=order_result['id'],
                side=direction,
                size=quantity,
                price=order_price,
                status=order_result['status']
            )
        except Exception as e:
            return OrderResult(success=False, error_message=str(e))

    async def place_close_order(self, contract_id: str, quantity: Decimal, price: Decimal, side: str) -> OrderResult:
        """Place a close order."""
        try:
            # Adjust price to ensure maker order
            best_bid, best_ask = await self.fetch_bbo_prices(contract_id)

            if side == 'sell' and price <= best_bid:
                adjusted_price = best_bid + self.config.tick_size
            elif side == 'buy' and price >= best_ask:
                adjusted_price = best_ask - self.config.tick_size
            else:
                adjusted_price = price

            order_result = await self.client.place_order(
                symbol=contract_id,
                side=side,
                quantity=float(quantity),
                price=float(self.round_to_tick(adjusted_price)),
                order_type='LIMIT'
            )

            return OrderResult(
                success=True,
                order_id=order_result['id'],
                side=side,
                size=quantity,
                price=adjusted_price,
                status=order_result['status']
            )
        except Exception as e:
            return OrderResult(success=False, error_message=str(e))

    async def cancel_order(self, order_id: str) -> OrderResult:
        """Cancel an order."""
        try:
            await self.client.cancel_order(order_id)
            return OrderResult(success=True)
        except Exception as e:
            return OrderResult(success=False, error_message=str(e))

    @query_retry()
    async def get_order_info(self, order_id: str) -> Optional[OrderInfo]:
        """Get order information."""
        try:
            order_data = await self.client.get_order(order_id)
            return OrderInfo(
                order_id=order_data['id'],
                side=order_data['side'].lower(),
                size=Decimal(order_data['quantity']),
                price=Decimal(order_data['price']),
                status=order_data['status'],
                filled_size=Decimal(order_data.get('filled_quantity', 0)),
                remaining_size=Decimal(order_data.get('remaining_quantity', 0))
            )
        except Exception as e:
            self.logger.log(f"Error getting order info: {e}", "ERROR")
            return None

    @query_retry(default_return=[])
    async def get_active_orders(self, contract_id: str) -> List[OrderInfo]:
        """Get active orders for a contract."""
        try:
            orders = await self.client.get_open_orders(contract_id)
            order_list = []

            for order in orders:
                order_list.append(OrderInfo(
                    order_id=order['id'],
                    side=order['side'].lower(),
                    size=Decimal(order['quantity']),
                    price=Decimal(order['price']),
                    status=order['status'],
                    filled_size=Decimal(order.get('filled_quantity', 0)),
                    remaining_size=Decimal(order.get('remaining_quantity', 0))
                ))

            return order_list
        except Exception as e:
            self.logger.log(f"Error getting active orders: {e}", "ERROR")
            return []

    @query_retry(default_return=0)
    async def get_account_positions(self) -> Decimal:
        """Get account positions."""
        try:
            positions = await self.client.get_positions()
            for position in positions:
                if position['symbol'] == self.config.contract_id:
                    return abs(Decimal(position['size']))
            return Decimal(0)
        except Exception as e:
            self.logger.log(f"Error getting positions: {e}", "ERROR")
            return Decimal(0)

    async def get_contract_attributes(self) -> Tuple[str, Decimal]:
        """Get contract ID and tick size for a ticker."""
        ticker = self.config.ticker
        if not ticker:
            raise ValueError("Ticker is empty")

        # Get market info from your exchange
        markets = await self.client.get_markets()
        for market in markets:
            if market['base_asset'] == ticker and market['quote_asset'] == 'USDT':
                self.config.contract_id = market['symbol']
                self.config.tick_size = Decimal(market['tick_size'])
                return self.config.contract_id, self.config.tick_size

        raise ValueError(f"Contract not found for ticker: {ticker}")
```

### 2. Register the Exchange

Add your exchange to the factory in `exchanges/factory.py`:

```python
from .your_exchange import YourExchangeClient

class ExchangeFactory:
    _registered_exchanges = {
        'edgex': EdgeXClient,
        'backpack': BackpackClient,
        'paradex': ParadexClient,
        'aster': AsterClient,
        'your_exchange': YourExchangeClient,  # Add this line
    }
```

### 3. Update Module Imports

Add your exchange to `exchanges/__init__.py`:

```python
from .your_exchange import YourExchangeClient

__all__ = ['BaseExchangeClient', 'EdgeXClient', 'BackpackClient', 'ParadexClient', 'AsterClient', 'YourExchangeClient', 'ExchangeFactory']
```

### 4. Test Your Implementation

Test your exchange client:

```python
from exchanges import ExchangeFactory

# Test exchange creation
config = {
    'ticker': 'BTC',
    'quantity': Decimal('0.01'),
    'take_profit': Decimal('0.5'),
    'direction': 'buy',
    'max_orders': 5,
    'wait_time': 10,
    'grid_step': Decimal('0.1'),
    'stop_price': Decimal('-1'),
    'pause_price': Decimal('-1')
}

client = ExchangeFactory.create_exchange('your_exchange', config)
print(f"Created {client.get_exchange_name()} client")
```

## Required Methods

All exchange clients must implement these methods from `BaseExchangeClient`:

### Core Methods

- `_validate_config()` - Validate exchange-specific configuration
- `connect()` - Establish connection to exchange
- `disconnect()` - Clean up connections
- `get_exchange_name()` - Return exchange name

### Order Management

- `place_open_order(contract_id, quantity, direction)` - Place opening orders
- `place_close_order(contract_id, quantity, price, side)` - Place closing orders
- `cancel_order(order_id)` - Cancel orders
- `get_order_info(order_id)` - Get order details
- `get_active_orders(contract_id)` - Get all active orders

### Data Retrieval

- `get_account_positions()` - Get account positions
- `setup_order_update_handler(handler)` - Set up real-time order updates
- `fetch_bbo_prices(contract_id)` - Get best bid/offer prices
- `get_contract_attributes()` - Get contract ID and tick size for ticker

## Data Structures

### OrderResult

```python
@dataclass
class OrderResult:
    success: bool
    order_id: Optional[str] = None
    side: Optional[str] = None
    size: Optional[Decimal] = None
    price: Optional[Decimal] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
    filled_size: Optional[Decimal] = None
```

### OrderInfo

```python
@dataclass
class OrderInfo:
    order_id: str
    side: str
    size: Decimal
    price: Decimal
    status: str
    filled_size: Decimal = 0.0
    remaining_size: Decimal = 0.0
    cancel_reason: str = ''
```

## Environment Variables

Each exchange requires specific environment variables. Here are the current implementations:

### EdgeX

- `EDGEX_ACCOUNT_ID` - Your EdgeX account ID
- `EDGEX_STARK_PRIVATE_KEY` - Your Stark private key
- `EDGEX_BASE_URL` - API base URL (optional, defaults to https://pro.edgex.exchange)
- `EDGEX_WS_URL` - WebSocket URL (optional, defaults to wss://quote.edgex.exchange)

### Backpack

- `BACKPACK_PUBLIC_KEY` - Your Backpack public key
- `BACKPACK_SECRET_KEY` - Your Backpack secret key (base64 encoded)

### Paradex

- `PARADEX_L1_ADDRESS` - Your Ethereum L1 address
- `PARADEX_L2_PRIVATE_KEY` - Your L2 private key (hex format)
- `PARADEX_L2_ADDRESS` - Your L2 address (optional)
- `PARADEX_ENVIRONMENT` - Environment (prod/testnet/nightly, defaults to prod)

### GRVT

- `GRVT_TRADING_ACCOUNT_ID` - Your GRVT trading account ID
- `GRVT_PRIVATE_KEY` - Your GRVT private key
- `GRVT_API_KEY` - Your GRVT API key
- `GRVT_ENVIRONMENT` - Environment (prod/testnet/staging/dev, defaults to prod)

## Usage

Once implemented, users can select your exchange:

```bash
python runbot.py --exchange your_exchange --ticker BTC --quantity 0.01 --direction buy
```

## Best Practices

1. **Error Handling**: Always return appropriate `OrderResult` objects with error messages
2. **Async/Await**: All methods should be async for non-blocking operations
3. **Configuration**: Use environment variables for API keys and endpoints
4. **Logging**: Use the provided `TradingLogger` for consistent logging
5. **Testing**: Test thoroughly with paper trading before live trading
6. **Documentation**: Document any exchange-specific requirements
7. **Retry Logic**: Use the `@query_retry` decorator for API calls that might fail
8. **Price Rounding**: Use `self.round_to_tick()` for price adjustments
9. **WebSocket Handling**: Implement proper order update handlers for real-time updates
10. **Order Types**: Use POST_ONLY orders to avoid taker fees when possible

## Current Exchange Implementations

### EdgeX

- Uses official EdgeX SDK
- Supports WebSocket order updates
- Implements retry logic for POST_ONLY rejections
- Requires Stark private key authentication

### Backpack

- Uses official Backpack SDK (bpx)
- Custom WebSocket manager for order updates
- ED25519 signature authentication
- Supports perpetual futures

### Paradex

- Uses official Paradex SDK (paradex_py)
- L2 credentials only (no L1 private key required)
- WebSocket subscription for order updates
- Supports StarkNet-based trading

### GRVT

- Uses official GRVT SDK (grvt-pysdk)
- REST API and WebSocket support
- Private key authentication
- Supports perpetual futures trading

## Example: Binance Futures

Here's a simplified example of how you might implement Binance Futures:

```python
import ccxt

class BinanceFuturesClient(BaseExchangeClient):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = os.getenv('BINANCE_API_KEY')
        self.secret_key = os.getenv('BINANCE_SECRET_KEY')
        self.client = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.secret_key,
            'sandbox': False,  # Set to True for testnet
            'options': {'defaultType': 'future'}
        })

    def _validate_config(self) -> None:
        if not self.api_key or not self.secret_key:
            raise ValueError("BINANCE_API_KEY and BINANCE_SECRET_KEY required")

    async def place_open_order(self, contract_id: str, quantity: Decimal, direction: str) -> OrderResult:
        try:
            order = self.client.create_order(
                symbol=contract_id,
                type='limit',
                side=direction,
                amount=float(quantity),
                price=float(self.round_to_tick(await self._get_market_price(contract_id, direction))),
                params={'postOnly': True}
            )
            return OrderResult(success=True, order_id=order['id'])
        except Exception as e:
            return OrderResult(success=False, error_message=str(e))
```

This modular approach makes it easy to add new exchanges while maintaining a consistent interface for the trading bot.
