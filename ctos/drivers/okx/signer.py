"""
Request signer/authorizer for this exchange.
- HMAC/Ed25519 etc. depending on the exchange
"""
class Signer:
    def __init__(self, secrets):
        self.secrets = secrets

    # TODO: implement sign(payload) -> headers/params
