"""
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
