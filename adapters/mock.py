import itertools
import time

from adapters.base import ExecutionAdapter


class MockAdapter(ExecutionAdapter):
    name = "mock"

    def __init__(self, agent_address="0xAGENT", starting_balance=1.0):
        self.agent_address = agent_address
        self.balances = {agent_address: starting_balance}
        self.history = []
        self._counter = itertools.count(1)

    def get_balance(self, address=None):
        return self.balances.get(address or self.agent_address, 0.0)

    def transfer(self, to, amount_eth):
        if amount_eth <= 0:
            raise ValueError("Amount must be greater than zero")
        if self.balances[self.agent_address] < amount_eth:
            raise ValueError("Insufficient balance")

        self.balances[self.agent_address] -= amount_eth
        self.balances[to] = self.balances.get(to, 0.0) + amount_eth

        tx_id = f"mock-{next(self._counter):04d}"
        self.history.append(
            {"tx": tx_id, "to": to, "amount_eth": amount_eth, "time": time.time()}
        )
        return tx_id