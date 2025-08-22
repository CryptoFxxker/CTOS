"""
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
