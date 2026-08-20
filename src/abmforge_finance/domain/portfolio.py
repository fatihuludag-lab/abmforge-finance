"""Immutable deterministic participant portfolio value object."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.domain._validation import require_decimal, require_non_empty_text
from abmforge_finance.exceptions import InvalidPortfolioError

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class Portfolio:
    """Represent exact instrument quantities owned by one participant.

    Positions are stored as a sorted tuple of ``(instrument_id, quantity)`` pairs.
    Zero positions are omitted, producing a deterministic sparse representation.
    Negative quantities are representable at the domain layer; the clearing policy
    decides whether short positions are admissible.
    """

    participant_id: str
    positions: tuple[tuple[str, Decimal], ...] = ()

    def __post_init__(self) -> None:
        require_non_empty_text(
            self.participant_id,
            field_name="participant_id",
            error_type=InvalidPortfolioError,
        )
        if not isinstance(self.positions, tuple):
            raise InvalidPortfolioError("positions must be a tuple")

        normalized: list[tuple[str, Decimal]] = []
        seen: set[str] = set()
        for entry in self.positions:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise InvalidPortfolioError(
                    "each position must be a (instrument_id, quantity) tuple"
                )
            instrument_id, quantity = entry
            validated_id = require_non_empty_text(
                instrument_id,
                field_name="instrument_id",
                error_type=InvalidPortfolioError,
            )
            if validated_id in seen:
                raise InvalidPortfolioError(
                    f"instrument_id {validated_id!r} appears more than once"
                )
            seen.add(validated_id)
            validated_quantity = require_decimal(
                quantity,
                field_name="quantity",
                error_type=InvalidPortfolioError,
            )
            if validated_quantity != _ZERO:
                normalized.append((validated_id, validated_quantity))

        normalized.sort(key=lambda item: item[0])
        object.__setattr__(self, "positions", tuple(normalized))

    def quantity(self, instrument_id: str) -> Decimal:
        """Return the exact quantity held for ``instrument_id`` or zero."""
        validated_id = require_non_empty_text(
            instrument_id,
            field_name="instrument_id",
            error_type=InvalidPortfolioError,
        )
        for current_id, current_quantity in self.positions:
            if current_id == validated_id:
                return current_quantity
        return _ZERO

    def with_quantity_delta(self, instrument_id: str, delta: Decimal) -> Portfolio:
        """Return a new portfolio after an exact quantity delta."""
        validated_id = require_non_empty_text(
            instrument_id,
            field_name="instrument_id",
            error_type=InvalidPortfolioError,
        )
        validated_delta = require_decimal(
            delta,
            field_name="delta",
            error_type=InvalidPortfolioError,
        )
        updated = dict(self.positions)
        new_quantity = updated.get(validated_id, _ZERO) + validated_delta
        if new_quantity == _ZERO:
            updated.pop(validated_id, None)
        else:
            updated[validated_id] = new_quantity
        return Portfolio(self.participant_id, tuple(updated.items()))
