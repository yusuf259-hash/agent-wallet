import os
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Permission tiers
READ_ONLY = 0      # the agent can look but never send
APPROVE_ALL = 1    # every payment needs a human yes
LIMITED_AUTO = 2   # small payments are automatic, bigger ones need a yes

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
DAY_SECONDS = 24 * 60 * 60


@dataclass
class Decision:
    status: str   # "allow", "deny", or "needs_approval"
    reason: str


class PolicyEngine:
    def __init__(
        self,
        allowlist,
        tier=LIMITED_AUTO,
        per_tx_cap="0.01",
        daily_cap="0.05",
        approval_threshold="0.002",
        clock=time.time,
    ):
        self.allowlist = {a.lower() for a in allowlist}
        self.tier = tier
        self.per_tx_cap = Decimal(str(per_tx_cap))
        self.daily_cap = Decimal(str(daily_cap))
        self.approval_threshold = Decimal(str(approval_threshold))
        self.clock = clock
        self.spent = []  # list of (time, amount) for money really sent

    @classmethod
    def from_env(cls, tier=LIMITED_AUTO):
        from dotenv import load_dotenv
        load_dotenv()
        return cls(allowlist=[os.environ["RECIPIENT"]], tier=tier)

    def spent_last_24h(self):
        now = self.clock()
        total = Decimal("0")
        for sent_at, amount in self.spent:
            if now - sent_at < DAY_SECONDS:
                total += amount
        return total

    def record(self, amount_eth):
        """Call this ONLY after money was really sent."""
        self.spent.append((self.clock(), Decimal(str(amount_eth))))

    def check(self, args):
        """Look at a payment request and decide. This never sends anything."""
        if self.tier == READ_ONLY:
            return Decision("deny", "Read-only mode: sending money is not allowed.")

        to = str(args.get("to", ""))
        if not ADDRESS_RE.match(to):
            return Decision("deny", "That is not a valid wallet address.")

        try:
            amount = Decimal(str(args.get("amount_eth")))
        except InvalidOperation:
            return Decision("deny", "The amount is not a valid number.")
        if not amount.is_finite() or amount <= 0:
            return Decision("deny", "The amount must be greater than zero.")

        if to.lower() not in self.allowlist:
            return Decision("deny", "This address is not on the approved list.")

        if amount > self.per_tx_cap:
            return Decision(
                "deny", f"Over the per-transaction limit of {self.per_tx_cap} ETH."
            )

        if self.spent_last_24h() + amount > self.daily_cap:
            return Decision(
                "deny", f"This would go over the daily limit of {self.daily_cap} ETH."
            )

        if self.tier == APPROVE_ALL or amount > self.approval_threshold:
            return Decision("needs_approval", "A human must approve this payment first.")

        return Decision("allow", "Within all limits.")