"""Immutable executed-trade value object."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.domain._validation import (
    require_decimal,
    require_non_empty_text,
    require_non_negative_int,
    require_non_negative_timestamp,
)
from abmforge_finance.domain.enums import Side
from abmforge_finance.exceptions import InvalidTradeError

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class Trade:
    """Represent one deterministic execution produced by a matching engine.

    Parameters
    ----------
    trade_id, instrument_id
        Stable non-empty trade and instrument identifiers.
    buy_order_id, sell_order_id
        Matched order identifiers.
    buyer_id, seller_id
        Participant identifiers. Self-trades are representable and may be rejected
        later by an exchange policy.
    price, quantity
        Positive finite decimal execution values.
    executed_at
        Finite non-negative simulation time.
    sequence_number
        Non-negative deterministic trade sequence.
    maker_order_id, taker_order_id
        Must be distinct and exactly cover the buy and sell order identifiers.
    buyer_fee, seller_fee
        Finite signed decimal fees. Negative values represent rebates.

    Raises
    ------
    InvalidTradeError
        If any value violates the executed-trade contract.

    Determinism
    -----------
    The object is immutable and contains the sequence and maker/taker attribution
    needed to reproduce downstream clearing records.
    """

    trade_id: str
    instrument_id: str
    buy_order_id: str
    sell_order_id: str
    buyer_id: str
    seller_id: str
    price: Decimal
    quantity: Decimal
    executed_at: int | float
    sequence_number: int
    maker_order_id: str
    taker_order_id: str
    buyer_fee: Decimal = _ZERO
    seller_fee: Decimal = _ZERO

    def __post_init__(self) -> None:
        for field_name, value in (
            ("trade_id", self.trade_id),
            ("instrument_id", self.instrument_id),
            ("buy_order_id", self.buy_order_id),
            ("sell_order_id", self.sell_order_id),
            ("buyer_id", self.buyer_id),
            ("seller_id", self.seller_id),
            ("maker_order_id", self.maker_order_id),
            ("taker_order_id", self.taker_order_id),
        ):
            require_non_empty_text(value, field_name=field_name, error_type=InvalidTradeError)

        if self.buy_order_id == self.sell_order_id:
            raise InvalidTradeError("buy_order_id and sell_order_id must differ")
        if self.maker_order_id == self.taker_order_id:
            raise InvalidTradeError("maker_order_id and taker_order_id must differ")
        if {self.maker_order_id, self.taker_order_id} != {
            self.buy_order_id,
            self.sell_order_id,
        }:
            raise InvalidTradeError(
                "maker_order_id and taker_order_id must identify the matched orders"
            )

        require_decimal(
            self.price,
            field_name="price",
            error_type=InvalidTradeError,
            minimum=_ZERO,
            minimum_inclusive=False,
        )
        require_decimal(
            self.quantity,
            field_name="quantity",
            error_type=InvalidTradeError,
            minimum=_ZERO,
            minimum_inclusive=False,
        )
        require_decimal(
            self.buyer_fee,
            field_name="buyer_fee",
            error_type=InvalidTradeError,
        )
        require_decimal(
            self.seller_fee,
            field_name="seller_fee",
            error_type=InvalidTradeError,
        )
        require_non_negative_timestamp(
            self.executed_at,
            field_name="executed_at",
            error_type=InvalidTradeError,
        )
        require_non_negative_int(
            self.sequence_number,
            field_name="sequence_number",
            error_type=InvalidTradeError,
        )

    @property
    def notional(self) -> Decimal:
        """Return the exact gross cash value ``price * quantity``."""
        return self.price * self.quantity

    @property
    def total_fees(self) -> Decimal:
        """Return the signed sum of buyer and seller fees."""
        return self.buyer_fee + self.seller_fee

    @property
    def maker_side(self) -> Side:
        """Return the side of the resting maker order."""
        return Side.BUY if self.maker_order_id == self.buy_order_id else Side.SELL

    @property
    def taker_side(self) -> Side:
        """Return the side of the incoming taker order."""
        return self.maker_side.opposite

    @property
    def maker_fee(self) -> Decimal:
        """Return the signed fee or rebate applied to the maker."""
        return self.buyer_fee if self.maker_side is Side.BUY else self.seller_fee

    @property
    def taker_fee(self) -> Decimal:
        """Return the signed fee or rebate applied to the taker."""
        return self.seller_fee if self.maker_side is Side.BUY else self.buyer_fee
