import json
from decimal import Decimal

import pytest

from adapters.mock import MockAdapter
from executor import AuditLog, ToolExecutor
from policy import PolicyEngine

GOOD = "0x" + "a1" * 20
STRANGER = "0x" + "c3" * 20


class Approver:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0

    def __call__(self, args, reason):
        self.calls += 1
        return self.answer


def make(tmp_path, balance=1.0, answer=False):
    adapter = MockAdapter(starting_balance=balance)
    policy = PolicyEngine([GOOD])
    approver = Approver(answer)
    audit = AuditLog(tmp_path / "audit.jsonl")
    return ToolExecutor(adapter, policy, approver, audit), adapter, policy, approver


def test_small_payment_is_sent(tmp_path):
    ex, adapter, policy, approver = make(tmp_path)
    result = ex.run("send_eth", {"to": GOOD, "amount_eth": 0.001})
    assert result["status"] == "sent"
    assert adapter.get_balance() == pytest.approx(0.999)
    assert policy.spent_last_24h() == Decimal("0.001")
    assert approver.calls == 0


def test_unknown_address_is_denied_and_no_money_moves(tmp_path):
    ex, adapter, policy, approver = make(tmp_path)
    result = ex.run("send_eth", {"to": STRANGER, "amount_eth": 0.001})
    assert result["status"] == "denied"
    assert adapter.get_balance() == 1.0


def test_medium_payment_is_sent_when_human_approves(tmp_path):
    ex, adapter, policy, approver = make(tmp_path, answer=True)
    result = ex.run("send_eth", {"to": GOOD, "amount_eth": 0.005})
    assert result["status"] == "sent"
    assert approver.calls == 1


def test_medium_payment_is_blocked_when_human_rejects(tmp_path):
    ex, adapter, policy, approver = make(tmp_path, answer=False)
    result = ex.run("send_eth", {"to": GOOD, "amount_eth": 0.005})
    assert result["status"] == "rejected_by_human"
    assert adapter.get_balance() == 1.0


def test_the_model_cannot_approve_itself(tmp_path):
    ex, adapter, policy, approver = make(tmp_path, answer=False)
    sneaky = {"to": GOOD, "amount_eth": 0.005, "approved": True}
    result = ex.run("send_eth", sneaky)
    assert result["status"] == "rejected_by_human"
    assert adapter.get_balance() == 1.0


def test_adapter_failure_does_not_crash_or_spend(tmp_path):
    ex, adapter, policy, approver = make(tmp_path, balance=0.001)
    result = ex.run("send_eth", {"to": GOOD, "amount_eth": 0.002})
    assert result["status"] == "error"
    assert policy.spent_last_24h() == Decimal("0")


def test_unknown_tool_is_rejected(tmp_path):
    ex, *_ = make(tmp_path)
    assert ex.run("delete_everything", {})["status"] == "error"


def test_missing_arguments_do_not_crash(tmp_path):
    ex, *_ = make(tmp_path)
    assert ex.run("send_eth", {})["status"] == "denied"


def test_audit_log_records_the_steps(tmp_path):
    ex, *_ = make(tmp_path)
    ex.run("send_eth", {"to": GOOD, "amount_eth": 0.001})
    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    events = {json.loads(line)["event"] for line in lines}
    assert {"tool_call", "policy_decision", "tool_result"} <= events


def test_balance_and_limits_tools(tmp_path):
    ex, *_ = make(tmp_path)
    assert ex.run("get_balance", {})["balance_eth"] == 1.0
    limits = ex.run("get_policy_limits", {})
    assert limits["per_payment_cap_eth"] == "0.01"
    assert limits["daily_cap_eth"] == "0.05"