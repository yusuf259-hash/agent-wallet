import json
import os
import re
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

# Permission tiers
READ_ONLY = 0      # the agent can look but never send
APPROVE_ALL = 1    # every payment needs a human yes
LIMITED_AUTO = 2   # small payments are automatic, bigger ones need a yes

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
DAY_SECONDS = 24 * 60 * 60


@dataclass
class Decision:
    status: str  # "allow", "deny", or "needs_approval"
    reason: str
    risk_score: int = 0
    risk_level: str = "LOW"


class PolicyEngine:
    def __init__(
        self,
        allowlist,
        tier=LIMITED_AUTO,
        per_tx_cap="0.01",
        daily_cap="0.05",
        approval_threshold="0.002",
        min_reserve_eth="0.002",
        max_gas_gwei="50",
        state_file=None,
        clock=time.time,
    ):
        self.allowlist = {a.lower() for a in allowlist if a}
        self.tier = tier
        self.per_tx_cap = Decimal(str(per_tx_cap))
        self.daily_cap = Decimal(str(daily_cap))
        self.approval_threshold = Decimal(str(approval_threshold))
        self.min_reserve_eth = Decimal(str(min_reserve_eth))
        self.max_gas_gwei = Decimal(str(max_gas_gwei))
        self.clock = clock
        self.state_file = Path(state_file) if state_file else None
        self.spent = []  # list of (time, amount) for money really sent
        self._load_state()

    def _load_state(self):
        if not self.state_file or not self.state_file.exists():
            return
        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
            self.spent = [
                (float(item["time"]), Decimal(str(item["amount"])))
                for item in raw.get("spent", [])
            ]
        except Exception:
            self.spent = []

    def _save_state(self):
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "spent": [
                {"time": sent_at, "amount": str(amount)}
                for sent_at, amount in self.spent
            ]
        }
        self.state_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def from_env(cls, tier=LIMITED_AUTO, state_file="logs/policy_state.json"):
        from dotenv import load_dotenv

        load_dotenv()
        raw_recipients = os.environ.get("RECIPIENT", "")
        extra_recipients = os.environ.get("EXTRA_RECIPIENTS", "")
        combined = [
            addr.strip()
            for addr in (raw_recipients + "," + extra_recipients).split(",")
            if addr.strip()
        ]
        return cls(allowlist=combined, tier=tier, state_file=state_file)

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
        self._save_state()

    def assess_risk(self, args):
        """Calculate a 0 to 100 quantitative risk score for a transaction."""
        score = 0
        to = str(args.get("to", ""))
        if not ADDRESS_RE.match(to) or to.lower() not in self.allowlist:
            score += 60
        try:
            amount = Decimal(str(args.get("amount_eth")))
            if not amount.is_finite() or amount <= 0:
                score += 50
            else:
                ratio = float(amount / self.per_tx_cap) if self.per_tx_cap > 0 else 1.0
                score += min(40, int(ratio * 30))
                if amount > self.approval_threshold:
                    score += 15
                if self.spent_last_24h() + amount > self.daily_cap:
                    score += 35
        except InvalidOperation:
            score += 50

        if args.get("gas_gwei") is not None:
            try:
                if Decimal(str(args["gas_gwei"])) > self.max_gas_gwei:
                    score += 25
            except InvalidOperation:
                score += 25

        score = min(100, score)
        if score >= 70:
            level = "CRITICAL"
        elif score >= 40:
            level = "HIGH"
        elif score >= 20:
            level = "MEDIUM"
        else:
            level = "LOW"
        return score, level

    def check(self, args):
        """Look at a payment request and decide. This never sends anything."""
        score, level = self.assess_risk(args)

        if self.tier == READ_ONLY:
            return Decision("deny", "Read-only mode: sending money is not allowed.", score, level)

        to = str(args.get("to", ""))
        if not ADDRESS_RE.match(to):
            return Decision("deny", "That is not a valid wallet address.", score, level)

        try:
            amount = Decimal(str(args.get("amount_eth")))
        except InvalidOperation:
            return Decision("deny", "The amount is not a valid number.", score, level)

        if not amount.is_finite() or amount <= 0:
            return Decision("deny", "The amount must be greater than zero.", score, level)

        if to.lower() not in self.allowlist:
            return Decision("deny", "This address is not on the approved list.", score, level)

        if amount > self.per_tx_cap:
            return Decision(
                "deny",
                f"Over the per-transaction limit of {self.per_tx_cap} ETH.",
                score,
                level,
            )

        if self.spent_last_24h() + amount > self.daily_cap:
            return Decision(
                "deny",
                f"This would go over the daily limit of {self.daily_cap} ETH.",
                score,
                level,
            )

        if args.get("balance_eth") is not None:
            try:
                bal = Decimal(str(args["balance_eth"]))
                if bal - amount < self.min_reserve_eth:
                    return Decision(
                        "deny",
                        f"Would breach treasury reserve floor of {self.min_reserve_eth} ETH.",
                        score,
                        level,
                    )
            except InvalidOperation:
                return Decision("deny", "Invalid wallet balance provided.", score, level)

        if args.get("gas_gwei") is not None:
            try:
                gas = Decimal(str(args["gas_gwei"]))
                if gas > self.max_gas_gwei:
                    return Decision(
                        "deny",
                        f"Network gas ({gas} Gwei) exceeds safety ceiling of {self.max_gas_gwei} Gwei.",
                        score,
                        level,
                    )
            except InvalidOperation:
                return Decision("deny", "Invalid gas price provided.", score, level)

        if self.tier == APPROVE_ALL or amount > self.approval_threshold:
            return Decision(
                "needs_approval",
                "A human must approve this payment first.",
                score,
                level,
            )

        return Decision("allow", "Within all limits.", score, level)