from abc import ABC, abstractmethod


class ExecutionAdapter(ABC):
    """The agent talks to this interface only.
    It never knows whether the money is pretend or real."""

    name = "base"

    @abstractmethod
    def get_balance(self, address=None) -> float:
        """Balance in ETH. With no address, use the agent's own wallet."""

    @abstractmethod
    def transfer(self, to: str, amount_eth: float) -> str:
        """Send ETH. Returns a transaction ID."""