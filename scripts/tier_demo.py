import os

from dotenv import load_dotenv

from adapters.mock import MockAdapter
from executor import AuditLog, ToolExecutor
from policy import PolicyEngine

load_dotenv()
to = os.environ["RECIPIENT"]


class Approver:
    """Pretends a human typed yes, and remembers if a human was asked."""

    def __init__(self):
        self.asked = 0

    def __call__(self, args, reason):
        self.asked += 1
        return True


for tier, name in [
    (0, "Tier 0 (read-only)"),
    (1, "Tier 1 (approve everything)"),
    (2, "Tier 2 (small = automatic)"),
]:
    approver = Approver()
    executor = ToolExecutor(
        MockAdapter(),
        PolicyEngine([to], tier=tier),
        approver=approver,
        audit=AuditLog("logs/tier_demo.jsonl"),
    )
    result = executor.run("send_eth", {"to": to, "amount_eth": 0.001})
    asked = "yes" if approver.asked else "no"
    print(f"{name:30} result={result['status']:8} human asked={asked}")