"""Immutable policy-facing market observation values."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.domain._validation import (
    require_decimal,
    require_non_empty_text,
    require_non_negative_int,
)
from abmforge_finance.exceptions import InvalidObservationError

_ZERO = Decimal("0")
_ONE = Decimal("1")


def _optional_decimal(
    value: Decimal | None,
    *,
    field_name: str,
    positive: bool = False,
    non_negative: bool = False,
) -> Decimal | None:
    if value is None:
        return None
    minimum = _ZERO if positive or non_negative else None
    return require_decimal(
        value,
        field_name=field_name,
        error_type=InvalidObservationError,
        minimum=minimum,
        minimum_inclusive=not positive,
    )


@dataclass(frozen=True, slots=True)
class MarketObservation:
    """Represent one immutable policy-facing snapshot of market and trader state.

    The observation is deliberately detached from :class:`Exchange` and ABMForge.
    Orchestration code is responsible for constructing it from the live market state.
    Policies therefore cannot mutate the order book, accounts, or portfolios through
    the observation object.
    """

    step: int
    instrument_id: str
    fundamental_value: Decimal
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    mid_price: Decimal | None = None
    spread: Decimal | None = None
    bid_depth: Decimal = _ZERO
    ask_depth: Decimal = _ZERO
    imbalance: Decimal | None = None
    last_trade_price: Decimal | None = None
    price_change: Decimal | None = None
    cash: Decimal = _ZERO
    inventory: Decimal = _ZERO

    def __post_init__(self) -> None:
        require_non_negative_int(
            self.step,
            field_name="step",
            error_type=InvalidObservationError,
        )
        require_non_empty_text(
            self.instrument_id,
            field_name="instrument_id",
            error_type=InvalidObservationError,
        )
        require_decimal(
            self.fundamental_value,
            field_name="fundamental_value",
            error_type=InvalidObservationError,
            minimum=_ZERO,
            minimum_inclusive=False,
        )
        _optional_decimal(self.best_bid, field_name="best_bid", positive=True)
        _optional_decimal(self.best_ask, field_name="best_ask", positive=True)
        _optional_decimal(self.mid_price, field_name="mid_price", positive=True)
        _optional_decimal(self.spread, field_name="spread", non_negative=True)
        require_decimal(
            self.bid_depth,
            field_name="bid_depth",
            error_type=InvalidObservationError,
            minimum=_ZERO,
        )
        require_decimal(
            self.ask_depth,
            field_name="ask_depth",
            error_type=InvalidObservationError,
            minimum=_ZERO,
        )
        imbalance = _optional_decimal(self.imbalance, field_name="imbalance")
        if imbalance is not None and not (-_ONE <= imbalance <= _ONE):
            raise InvalidObservationError("imbalance must be in [-1, 1]")
        _optional_decimal(self.last_trade_price, field_name="last_trade_price", positive=True)
        _optional_decimal(self.price_change, field_name="price_change")
        require_decimal(self.cash, field_name="cash", error_type=InvalidObservationError)
        require_decimal(
            self.inventory,
            field_name="inventory",
            error_type=InvalidObservationError,
        )
        if (
            self.best_bid is not None
            and self.best_ask is not None
            and self.best_bid >= self.best_ask
        ):
            raise InvalidObservationError("best_bid must be less than best_ask")

    @property
    def reference_price(self) -> Decimal | None:
        """Return a deterministic price reference for directional baseline policies.

        The midpoint is preferred when available, followed by the last trade, then a
        one-sided best quote. ``None`` denotes an observation with no price reference.
        """

        if self.mid_price is not None:
            return self.mid_price
        if self.last_trade_price is not None:
            return self.last_trade_price
        if self.best_bid is not None:
            return self.best_bid
        return self.best_ask
