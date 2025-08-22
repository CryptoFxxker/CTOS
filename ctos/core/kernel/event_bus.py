"""
Trivial event bus placeholder (pub/sub).
Replace with a real bus or use asyncio signals.
"""
class EventBus:
    def publish(self, topic, message):
        pass

    def subscribe(self, topic, handler):
        pass
