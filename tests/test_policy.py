import pytest

from policy import APPROVE_ALL, LIMITED_AUTO, READ_ONLY, PolicyEngine

GOOD = "0x" + "a1" * 20
STRANGER = "0x" + "c3" * 20


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(tier=LIMITED_AUTO, clock=None):
    return PolicyEngine([GOOD], tier=tier, clock=clock or Clock())


def ask(policy, amount, to=GOOD):
    return policy.check({"to": to, "amount_eth": amount})


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
        p.record(0.01)  # pretend each one was approved and sent
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