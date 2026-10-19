import pytest
from adapters.mock import MockAdapter


def test_starting_balance():
    a = MockAdapter(starting_balance=1.0)
    assert a.get_balance() == 1.0


def test_transfer_moves_money():
    a = MockAdapter(starting_balance=1.0)
    tx = a.transfer("0xBOB", 0.25)
    assert tx == "mock-0001"
    assert a.get_balance() == pytest.approx(0.75)
    assert a.get_balance("0xBOB") == pytest.approx(0.25)


def test_cannot_overspend():
    a = MockAdapter(starting_balance=0.1)
    with pytest.raises(ValueError):
        a.transfer("0xBOB", 5)


def test_rejects_zero_amount():
    a = MockAdapter()
    with pytest.raises(ValueError):
        a.transfer("0xBOB", 0)


def test_reports_gas_price_gwei():
    a = MockAdapter(gas_gwei=15.5)
    assert a.get_gas_price_gwei() == pytest.approx(15.5)