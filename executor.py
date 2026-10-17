import json
import time
from pathlib import Path

# The tools the AI is allowed to ask for. Nothing else exists for it.
TOOLS = [
    {
        "type": "function",
        "name": "get_balance",
        "description": "Get the agent wallet balance in ETH.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "get_policy_limits",
        "description": "Get the safety limits that apply to payments.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "send_eth",
        "description": (
            "Request a payment of ETH from the agent wallet. "
            "A safety policy decides whether it is allowed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient wallet address, starting with 0x",
                },
                "amount_eth": {
                    "type": "number",
                    "description": "Amount in ETH, for example 0.001",
                },
            },
            "required": ["to", "amount_eth"],
        },
    },
]


class AuditLog:
    """The logbook: one line per event. Evidence for the security report."""

    def __init__(self, path="logs/audit.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event, **details):
        record = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "event": event}
        record.update(details)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")


def terminal_approver(args, reason):
    """Only a human typing in the terminal can approve. The AI cannot."""
    print()
    print("=== APPROVAL NEEDED ===")
    print(f"Send {args.get('amount_eth')} ETH to {args.get('to')}")
    print(f"Reason: {reason}")
    answer = input("Type yes to approve, anything else to reject: ")
    return answer.strip().lower() == "yes"


class ToolExecutor:
    def __init__(self, adapter, policy, approver=None, audit=None):
        self.adapter = adapter
        self.policy = policy
        self.approver = approver or terminal_approver
        self.audit = audit or AuditLog()

    def run(self, name, args):
        self.audit.write("tool_call", tool=name, args=args)
        try:
            if name == "get_balance":
                result = {
                    "balance_eth": self.adapter.get_balance(),
                    "network": self.adapter.name,
                }
            elif name == "get_policy_limits":
                result = self._limits()
            elif name == "send_eth":
                result = self._send(args)
            else:
                result = {"status": "error", "reason": "Unknown tool."}
        except Exception as e:
            # Only the error type is logged. Full messages can contain secrets.
            self.audit.write("tool_error", tool=name, error_type=type(e).__name__)
            result = {
                "status": "error",
                "reason": "The wallet could not complete that request.",
            }
        self.audit.write("tool_result", tool=name, result=result)
        return result

    def _limits(self):
        p = self.policy
        return {
            "per_payment_cap_eth": str(p.per_tx_cap),
            "daily_cap_eth": str(p.daily_cap),
            "needs_approval_above_eth": str(p.approval_threshold),
            "spent_last_24h_eth": str(p.spent_last_24h()),
            "approved_recipients": sorted(p.allowlist),
            "tier": p.tier,
        }

    def _send(self, args):
        decision = self.policy.check(args)
        self.audit.write(
            "policy_decision", status=decision.status, reason=decision.reason, args=args
        )

        if decision.status == "deny":
            return {"status": "denied", "reason": decision.reason}

        if decision.status == "needs_approval":
            approved = self.approver(args, decision.reason)
            self.audit.write("human_approval", approved=approved, args=args)
            if not approved:
                return {
                    "status": "rejected_by_human",
                    "reason": "The human did not approve this payment.",
                }

        to = args["to"]
        amount = float(args["amount_eth"])
        tx = self.adapter.transfer(to, amount)
        self.policy.record(amount)  # only after money really moved
        return {"status": "sent", "tx": tx, "amount_eth": amount, "to": to}