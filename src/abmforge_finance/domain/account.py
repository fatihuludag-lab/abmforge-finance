"""Immutable participant cash-account value object."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from abmforge_finance.domain._validation import require_decimal, require_non_empty_text
from abmforge_finance.exceptions import InvalidAccountError


@dataclass(frozen=True, slots=True)
class Account:
    """Represent one participant's exact cash balance.

    ``Account`` is policy-neutral: finite negative balances are representable so a
    later margin or credit model can reuse the value object. The baseline
    :class:`~abmforge_finance.market.ClearingEngine` rejects settlements that would
    produce negative participant cash.
    """

    participant_id: str
    cash: Decimal

    def __post_init__(self) -> None:
        require_non_empty_text(
            self.participant_id,
            field_name="participant_id",
            error_type=InvalidAccountError,
        )
        require_decimal(self.cash, field_name="cash", error_type=InvalidAccountError)

    def with_cash_delta(self, delta: Decimal) -> Account:
        """Return a new account after applying an exact finite cash delta."""
        validated = require_decimal(delta, field_name="delta", error_type=InvalidAccountError)
        return replace(self, cash=self.cash + validated)
