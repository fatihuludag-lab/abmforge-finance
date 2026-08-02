"""Immutable order value object."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from abmforge_finance.domain._validation import (
    require_decimal,
    require_non_empty_text,
    require_non_negative_int,
    require_non_negative_timestamp,
)
from abmforge_finance.domain.enums import OrderType, Side, TimeInForce
from abmforge_finance.exceptions import InvalidOrderError

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class Order:
    """Represent one immutable order instruction and its remaining quantity.

    Parameters
    ----------
    order_id, agent_id, instrument_id
        Stable non-empty identifiers.
    side
        Buy or sell direction.
    order_type
        Limit or market instruction.
    quantity
        Original positive order quantity as ``Decimal``.
    remaining_quantity
        Unfilled quantity in the inclusive range ``[0, quantity]``.
    price
        Positive limit price, or ``None`` for a market order.
    submitted_at
        Finite non-negative simulation time.
    sequence_number
        Non-negative deterministic submission sequence.
    time_in_force
        ``GTC`` or ``IOC``. Market orders must be ``IOC`` in the first core.

    Raises
    ------
    InvalidOrderError
        If any field violates the order contract.

    Determinism
    -----------
    The object is immutable. Priority is represented explicitly by
    ``submitted_at`` and ``sequence_number`` rather than object identity or list order.

    Examples
    --------
    >>> from decimal import Decimal
    >>> from abmforge_finance import Order, OrderType, Side, TimeInForce
    >>> order = Order(
    ...     order_id="o-1",
    ...     agent_id="a-1",
    ...     instrument_id="ACME",
    ...     side=Side.BUY,
    ...     order_type=OrderType.LIMIT,
    ...     quantity=Decimal("10"),
    ...     remaining_quantity=Decimal("10"),
    ...     price=Decimal("99.50"),
    ...     submitted_at=0,
    ...     sequence_number=1,
    ...     time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
    ... )
    >>> order.filled_quantity
    Decimal('0')
    """

    order_id: str
    agent_id: str
    instrument_id: str
    side: Side
    order_type: OrderType
    quantity: Decimal
    remaining_quantity: Decimal
    price: Decimal | None
    submitted_at: int | float
    sequence_number: int
    time_in_force: TimeInForce

    def __post_init__(self) -> None:
        for field_name, value in (
            ("order_id", self.order_id),
            ("agent_id", self.agent_id),
            ("instrument_id", self.instrument_id),
        ):
            require_non_empty_text(value, field_name=field_name, error_type=InvalidOrderError)

        if not isinstance(self.side, Side):
            raise InvalidOrderError("side must be a Side")
        if not isinstance(self.order_type, OrderType):
            raise InvalidOrderError("order_type must be an OrderType")
        if not isinstance(self.time_in_force, TimeInForce):
            raise InvalidOrderError("time_in_force must be a TimeInForce")

        quantity = require_decimal(
            self.quantity,
            field_name="quantity",
            error_type=InvalidOrderError,
            minimum=_ZERO,
            minimum_inclusive=False,
        )
        remaining = require_decimal(
            self.remaining_quantity,
            field_name="remaining_quantity",
            error_type=InvalidOrderError,
            minimum=_ZERO,
        )
        if remaining > quantity:
            raise InvalidOrderError("remaining_quantity cannot exceed quantity")

        require_non_negative_timestamp(
            self.submitted_at,
            field_name="submitted_at",
            error_type=InvalidOrderError,
        )
        require_non_negative_int(
            self.sequence_number,
            field_name="sequence_number",
            error_type=InvalidOrderError,
        )

        if self.order_type is OrderType.LIMIT:
            require_decimal(
                self.price,
                field_name="price",
                error_type=InvalidOrderError,
                minimum=_ZERO,
                minimum_inclusive=False,
            )
        elif self.price is not None:
            raise InvalidOrderError("market orders must not carry a price")

        if (
            self.order_type is OrderType.MARKET
            and self.time_in_force is not TimeInForce.IMMEDIATE_OR_CANCEL
        ):
            raise InvalidOrderError("market orders must use immediate-or-cancel")

    @property
    def filled_quantity(self) -> Decimal:
        """Return the exact quantity already filled.

        Returns
        -------
        Decimal
            ``quantity - remaining_quantity``.
        """
        return self.quantity - self.remaining_quantity

    @property
    def is_filled(self) -> bool:
        """Return whether no quantity remains active."""
        return self.remaining_quantity == _ZERO

    def with_remaining_quantity(self, remaining_quantity: Decimal) -> Order:
        """Return a new order with a monotonically reduced remaining quantity.

        Parameters
        ----------
        remaining_quantity
            New remaining quantity. It may be zero but cannot exceed the current
            remaining quantity.

        Returns
        -------
        Order
            A new validated immutable value.

        Raises
        ------
        InvalidOrderError
            If the new value is invalid or would increase the remaining quantity.

        Determinism
        -----------
        The method is a pure transformation and does not mutate the original order.
        """
        validated = require_decimal(
            remaining_quantity,
            field_name="remaining_quantity",
            error_type=InvalidOrderError,
            minimum=_ZERO,
        )
        if validated > self.remaining_quantity:
            raise InvalidOrderError("remaining_quantity cannot increase")
        return replace(self, remaining_quantity=validated)
