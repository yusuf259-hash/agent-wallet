import json
import time
from decimal import Decimal
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
        "description": "Get the safety limits, reserve floor, gas ceiling, and permission tier that apply to payments.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "get_portfolio_status",
        "description": "Get a complete treasury and asset management report including total balance, spendable balance above reserve floor, 24h spending, and live network gas price.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "type": "function",
        "name": "simulate_transfer",
        "description": "Dry-run a payment without sending money. Returns the policy decision, quantitative risk score (0-100), risk level, estimated gas cost, and projected balance.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient wallet address, starting with 0x",
                },
                "amount_eth": {
                    "type": "number",
                    "description": "Amount in ETH to simulate, for example 0.001",
                },
            },
            "required": ["to", "amount_eth"],
        },
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
    {
        "type": "function",
        "name": "batch_send_eth",
        "description": "Execute a batch of ETH payments to one or more recipients. Each payment is checked against the safety policy individually.",
        "parameters": {
            "type": "object",
            "properties": {
                "payments": {
                    "type": "array",
                    "description": "List of payments, each with 'to' and 'amount_eth'",
                    "items": {
                        "type": "object",
                        "properties": {
                            "to": {"type": "string"},
                            "amount_eth": {"type": "number"},
                        },
                        "required": ["to", "amount_eth"],
                    },
                }
            },
            "required": ["payments"],
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
            elif name == "get_portfolio_status":
                result = self._portfolio_status()
            elif name == "simulate_transfer":
                result = self._simulate(args)
            elif name == "send_eth":
                result = self._send(args)
            elif name == "batch_send_eth":
                result = self._batch_send(args)
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
            "min_reserve_floor_eth": str(p.min_reserve_eth),
            "max_gas_ceiling_gwei": str(p.max_gas_gwei),
            "spent_last_24h_eth": str(p.spent_last_24h()),
            "approved_recipients": sorted(p.allowlist),
            "tier": p.tier,
        }

    def _portfolio_status(self):
        p = self.policy
        bal = Decimal(str(self.adapter.get_balance()))
        gas_gwei = self.adapter.get_gas_price_gwei()
        spendable = max(Decimal("0"), bal - p.min_reserve_eth)
        remaining_daily = max(Decimal("0"), p.daily_cap - p.spent_last_24h())
        return {
            "network": self.adapter.name,
            "balance_eth": float(bal),
            "reserve_floor_eth": float(p.min_reserve_eth),
            "spendable_balance_eth": float(spendable),
            "spent_last_24h_eth": float(p.spent_last_24h()),
            "remaining_daily_budget_eth": float(remaining_daily),
            "current_gas_gwei": round(gas_gwei, 4),
            "gas_status": "SAFE" if Decimal(str(gas_gwei)) <= p.max_gas_gwei else "HIGH_FEE_ALERT",
            "tier": p.tier,
        }

    def _simulate(self, args):
        bal = self.adapter.get_balance()
        gas_gwei = self.adapter.get_gas_price_gwei()
        check_args = dict(args or {})
        check_args.setdefault("balance_eth", bal)
        check_args.setdefault("gas_gwei", gas_gwei)

        decision = self.policy.check(check_args)
        est_gas_eth = round((gas_gwei * 21000) / 1e9, 8)
        try:
            amt = float(args.get("amount_eth", 0))
        except (TypeError, ValueError):
            amt = 0.0

        return {
            "simulation": True,
            "would_status": decision.status,
            "reason": decision.reason,
            "risk_score": decision.risk_score,
            "risk_level": decision.risk_level,
            "current_balance_eth": bal,
            "estimated_gas_eth": est_gas_eth,
            "projected_balance_eth": round(bal - amt - est_gas_eth, 6)
            if decision.status != "deny"
            else bal,
        }

    def _send(self, args):
        check_args = dict(args or {})
        check_args.setdefault("gas_gwei", self.adapter.get_gas_price_gwei())
        decision = self.policy.check(check_args)
        self.audit.write(
            "policy_decision",
            status=decision.status,
            reason=decision.reason,
            risk_score=decision.risk_score,
            risk_level=decision.risk_level,
            args=args,
        )
        if decision.status == "deny":
            return {
                "status": "denied",
                "reason": decision.reason,
                "risk_score": decision.risk_score,
                "risk_level": decision.risk_level,
            }
        if decision.status == "needs_approval":
            approved = self.approver(args, decision.reason)
            self.audit.write("human_approval", approved=approved, args=args)
            if not approved:
                return {
                    "status": "rejected_by_human",
                    "reason": "The human did not approve this payment.",
                    "risk_score": decision.risk_score,
                    "risk_level": decision.risk_level,
                }
        to = args["to"]
        amount = float(args["amount_eth"])
        tx = self.adapter.transfer(to, amount)
        self.policy.record(amount)  # only after money really moved
        return {
            "status": "sent",
            "tx": tx,
            "amount_eth": amount,
            "to": to,
            "risk_score": decision.risk_score,
            "risk_level": decision.risk_level,
        }

    def _batch_send(self, args):
        payments = (args or {}).get("payments")
        if not isinstance(payments, list) or not payments:
            return {"status": "denied", "reason": "Batch payments list cannot be empty."}
        if len(payments) > 5:
            return {"status": "denied", "reason": "Batch size cannot exceed 5 payments at once."}

        results = []
        sent_count = 0
        for item in payments:
            res = self._send(item if isinstance(item, dict) else {})
            results.append(res)
            if res.get("status") == "sent":
                sent_count += 1
        return {
            "status": "batch_completed",
            "total_requested": len(payments),
            "total_sent": sent_count,
            "results": results,
        }