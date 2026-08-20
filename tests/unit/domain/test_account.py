"""Unit tests for immutable participant cash accounts."""

from decimal import Decimal

import pytest

from abmforge_finance import Account, InvalidAccountError


def test_account_accepts_finite_signed_cash() -> None:
    account = Account("agent-1", Decimal("-5.25"))
    assert account.participant_id == "agent-1"
    assert account.cash == Decimal("-5.25")


@pytest.mark.parametrize("participant_id", ["", "   ", 1, None])
def test_account_requires_non_empty_participant_id(participant_id: object) -> None:
    with pytest.raises(InvalidAccountError):
        Account(participant_id, Decimal("1"))  # type: ignore[arg-type]


@pytest.mark.parametrize("cash", [1, 1.0, Decimal("NaN"), Decimal("Infinity")])
def test_account_requires_finite_decimal_cash(cash: object) -> None:
    with pytest.raises(InvalidAccountError):
        Account("agent-1", cash)  # type: ignore[arg-type]


def test_with_cash_delta_is_pure() -> None:
    original = Account("agent-1", Decimal("10"))
    updated = original.with_cash_delta(Decimal("-2.5"))
    assert original.cash == Decimal("10")
    assert updated.cash == Decimal("7.5")
    assert updated.participant_id == original.participant_id


def test_with_cash_delta_validates_decimal() -> None:
    account = Account("agent-1", Decimal("10"))
    with pytest.raises(InvalidAccountError):
        account.with_cash_delta(1)  # type: ignore[arg-type]
