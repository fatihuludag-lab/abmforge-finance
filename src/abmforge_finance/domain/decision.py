"""Immutable policy decisions that remain separate from exchange order identity."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from abmforge_finance.domain._validation import require_decimal
from abmforge_finance.domain.enums import OrderType, Side, TimeInForce
from abmforge_finance.exceptions import InvalidDecisionError

_ZERO = Decimal("0")


class DecisionKind(str, Enum):
    """High-level decision types emitted by baseline trading policies."""

    HOLD = "hold"
    ORDER = "order"


@dataclass(frozen=True, slots=True)
class TradingDecision:
    """Represent one immutable policy output without assigning exchange identity.

    Order identifiers, submission sequence numbers, and timestamps are intentionally
    absent. A later orchestration boundary converts an ``ORDER`` decision into a domain
    :class:`Order` using the authoritative market clock and exchange sequencing rules.
    """

    kind: DecisionKind
    side: Side | None = None
    order_type: OrderType | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    time_in_force: TimeInForce | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DecisionKind):
            raise InvalidDecisionError("kind must be a DecisionKind")
        if self.kind is DecisionKind.HOLD:
            if any(
                value is not None
                for value in (
                    self.side,
                    self.order_type,
                    self.quantity,
                    self.price,
                    self.time_in_force,
                )
            ):
                raise InvalidDecisionError("hold decisions cannot carry order fields")
            return

        if not isinstance(self.side, Side):
            raise InvalidDecisionError("order decisions require a Side")
        if not isinstance(self.order_type, OrderType):
            raise InvalidDecisionError("order decisions require an OrderType")
        if not isinstance(self.time_in_force, TimeInForce):
            raise InvalidDecisionError("order decisions require a TimeInForce")
        require_decimal(
            self.quantity,
            field_name="quantity",
            error_type=InvalidDecisionError,
            minimum=_ZERO,
            minimum_inclusive=False,
        )
        if self.order_type is OrderType.MARKET:
            if self.price is not None:
                raise InvalidDecisionError("market decisions must not carry a price")
            if self.time_in_force is not TimeInForce.IMMEDIATE_OR_CANCEL:
                raise InvalidDecisionError("market decisions must be IOC")
            return
        require_decimal(
            self.price,
            field_name="price",
            error_type=InvalidDecisionError,
            minimum=_ZERO,
            minimum_inclusive=False,
        )

    @property
    def is_hold(self) -> bool:
        """Return whether the policy intentionally emits no order."""

        return self.kind is DecisionKind.HOLD

    @classmethod
    def hold(cls) -> TradingDecision:
        """Return the canonical no-order decision."""

        return cls(kind=DecisionKind.HOLD)

    @classmethod
    def market(cls, side: Side, quantity: Decimal) -> TradingDecision:
        """Return one market IOC decision."""

        return cls(
            kind=DecisionKind.ORDER,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            price=None,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        )

    @classmethod
    def limit(
        cls,
        side: Side,
        quantity: Decimal,
        price: Decimal,
        *,
        time_in_force: TimeInForce = TimeInForce.GOOD_TIL_CANCELLED,
    ) -> TradingDecision:
        """Return one limit-order decision without assigning exchange identity."""

        return cls(
            kind=DecisionKind.ORDER,
            side=side,
            order_type=OrderType.LIMIT,
            quantity=quantity,
            price=price,
            time_in_force=time_in_force,
        )
