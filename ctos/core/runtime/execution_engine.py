"""
Execution engine dispatches strategy intents to driver syscalls.
"""
class ExecutionEngine:
    def __init__(self, driver):
        self.driver = driver

    # def place(order): call driver.place_order(...)
