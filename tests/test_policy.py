import pytest
from policy import APPROVE_ALL, LIMITED_AUTO, READ_ONLY, PolicyEngine

GOOD = "0x" + "a1" * 20
STRANGER = "0x" + "c3" * 20


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(tier=LIMITED_AUTO, clock=None, state_file=None):
    return PolicyEngine([GOOD], tier=tier, clock=clock or Clock(), state_file=state_file)


def ask(policy, amount, to=GOOD, **extra):
    payload = {"to": to, "amount_eth": amount}
    payload.update(extra)
    return policy.check(payload)


def test_small_payment_is_allowed():
    assert ask(make(), 0.001).status == "allow"


def test_medium_payment_needs_approval():
    assert ask(make(), 0.005).status == "needs_approval"


def test_over_per_transaction_cap_is_denied():
    assert ask(make(), 0.02).status == "deny"


def test_unknown_address_is_denied():
    assert ask(make(), 0.001, to=STRANGER).status == "deny"


@pytest.mark.parametrize("bad_address", ["hello", "0x123", ""])
def test_invalid_address_is_denied(bad_address):
    assert ask(make(), 0.001, to=bad_address).status == "deny"


@pytest.mark.parametrize("bad_amount", [0, -1, "abc", None, "nan"])
def test_bad_amount_is_denied(bad_amount):
    assert ask(make(), bad_amount).status == "deny"


def test_daily_cap_stops_split_payments():
    p = make()
    for _ in range(5):
        assert ask(p, 0.01).status == "needs_approval"
        p.record(0.01)
    assert ask(p, 0.01).status == "deny"


def test_daily_window_resets_after_24_hours():
    clock = Clock()
    p = make(clock=clock)
    p.record(0.05)
    assert ask(p, 0.01).status == "deny"
    clock.now += 25 * 3600
    assert ask(p, 0.01).status == "needs_approval"


def test_read_only_tier_denies_everything():
    assert ask(make(tier=READ_ONLY), 0.001).status == "deny"


def test_approve_all_tier_asks_every_time():
    assert ask(make(tier=APPROVE_ALL), 0.001).status == "needs_approval"


def test_address_match_ignores_upper_and_lower_case():
    upper = "0x" + GOOD[2:].upper()
    assert ask(make(), 0.001, to=upper).status == "allow"


def test_checking_does_not_spend_money():
    p = make()
    for _ in range(10):
        assert ask(p, 0.01).status == "needs_approval"


def test_every_decision_has_a_reason():
    p = make()
    for amount in (0.001, 0.005, 0.02, -1):
        decision = ask(p, amount)
        assert decision.status in {"allow", "needs_approval", "deny"}
        assert decision.reason


def test_persistent_state_survives_restart(tmp_path):
    state_path = tmp_path / "policy_state.json"
    clock = Clock()
    p1 = make(clock=clock, state_file=state_path)
    p1.record(0.045)
    # Create a brand new PolicyEngine reading from the same file (simulating restart)
    p2 = make(clock=clock, state_file=state_path)
    assert ask(p2, 0.01).status == "deny"


def test_reserve_floor_blocks_wallet_drain():
    p = make()
    # Wallet has 0.0025 ETH; sending 0.001 leaves 0.0015, which is below 0.002 reserve floor
    decision = ask(p, 0.001, balance_eth=0.0025)
    assert decision.status == "deny"
    assert "reserve floor" in decision.reason


def test_gas_ceiling_blocks_fee_spike():
    p = make()
    decision = ask(p, 0.001, gas_gwei=85)
    assert decision.status == "deny"
    assert "safety ceiling" in decision.reason


def test_risk_score_scales_with_danger():
    p = make()
    safe_decision = ask(p, 0.001)
    risky_decision = ask(p, 0.05, to=STRANGER, gas_gwei=100)
    assert safe_decision.risk_score < 20
    assert safe_decision.risk_level == "LOW"
    assert risky_decision.risk_score >= 70
    assert risky_decision.risk_level == "CRITICAL"