"""Deterministic passive-liquidity baseline policies."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from abmforge_finance.domain import (
    CancelIntent,
    MarketObservation,
    Side,
    TimeInForce,
    TradingDecision,
    TradingPlan,
)
from abmforge_finance.exceptions import InvalidPolicyError
from abmforge_finance.policies.base import validate_positive_quantity

_ZERO = Decimal("0")


def _positive_decimal(value: object, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise InvalidPolicyError(f"{field_name} must be a Decimal")
    if not value.is_finite() or value <= _ZERO:
        raise InvalidPolicyError(f"{field_name} must be finite and positive")
    return value


def _validate_quote_config(
    *,
    side: object,
    quantity: object,
    tick_size: object,
    offset_ticks: object,
) -> tuple[Side, Decimal, Decimal, int]:
    if not isinstance(side, Side):
        raise InvalidPolicyError("side must be a Side")
    quantity_value = validate_positive_quantity(quantity)
    tick_value = _positive_decimal(tick_size, field_name="tick_size")
    if isinstance(offset_ticks, bool) or not isinstance(offset_ticks, int) or offset_ticks < 1:
        raise InvalidPolicyError("offset_ticks must be a positive integer")
    return side, quantity_value, tick_value, offset_ticks


def _quote_price(
    *,
    side: Side,
    fundamental_value: Decimal,
    tick_size: Decimal,
    offset_ticks: int,
) -> Decimal:
    ratio = fundamental_value / tick_size
    if side is Side.BUY:
        anchor = int(ratio.to_integral_value(rounding=ROUND_FLOOR))
        quote_ticks = anchor - offset_ticks
    else:
        anchor = int(ratio.to_integral_value(rounding=ROUND_CEILING))
        quote_ticks = anchor + offset_ticks

    if quote_ticks <= 0:
        raise InvalidPolicyError(
            "passive quote would be non-positive; reduce tick_size/offset or "
            "increase the fundamental reference"
        )
    return tick_size * quote_ticks


def _validate_call(observation: object, *, agent_id: object) -> MarketObservation:
    if not isinstance(observation, MarketObservation):
        raise InvalidPolicyError("observation must be a MarketObservation")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise InvalidPolicyError("agent_id must be a non-empty string")
    return observation


@dataclass(frozen=True, slots=True)
class PassiveLiquidityPolicy:
    """Emit one passive GTC quote around the latent fundamental value."""

    side: Side
    quantity: Decimal
    tick_size: Decimal
    offset_ticks: int = 1
    quote_step: int = 0

    def __post_init__(self) -> None:
        _validate_quote_config(
            side=self.side,
            quantity=self.quantity,
            tick_size=self.tick_size,
            offset_ticks=self.offset_ticks,
        )
        if (
            isinstance(self.quote_step, bool)
            or not isinstance(self.quote_step, int)
            or self.quote_step < 0
        ):
            raise InvalidPolicyError("quote_step must be a non-negative integer")

    def decide(
        self,
        observation: MarketObservation,
        *,
        agent_id: str,
    ) -> TradingDecision:
        """Quote once at the configured step, otherwise hold."""

        observation = _validate_call(observation, agent_id=agent_id)
        if observation.step != self.quote_step:
            return TradingDecision.hold()

        return TradingDecision.limit(
            self.side,
            self.quantity,
            _quote_price(
                side=self.side,
                fundamental_value=observation.fundamental_value,
                tick_size=self.tick_size,
                offset_ticks=self.offset_ticks,
            ),
            time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
        )


@dataclass(frozen=True, slots=True)
class DynamicPassiveLiquidityPolicy:
    """Cancel known resting quotes and reprice one side every market period."""

    side: Side
    quantity: Decimal
    tick_size: Decimal
    offset_ticks: int = 1

    def __post_init__(self) -> None:
        _validate_quote_config(
            side=self.side,
            quantity=self.quantity,
            tick_size=self.tick_size,
            offset_ticks=self.offset_ticks,
        )

    def plan(
        self,
        observation: MarketObservation,
        *,
        agent_id: str,
        active_order_ids: tuple[str, ...],
    ) -> TradingPlan:
        """Return cancellation intents plus one replacement GTC decision."""

        observation = _validate_call(observation, agent_id=agent_id)
        if not isinstance(active_order_ids, tuple) or not all(
            isinstance(order_id, str) and order_id.strip() for order_id in active_order_ids
        ):
            raise InvalidPolicyError("active_order_ids must be a tuple of non-empty strings")

        decision = TradingDecision.limit(
            self.side,
            self.quantity,
            _quote_price(
                side=self.side,
                fundamental_value=observation.fundamental_value,
                tick_size=self.tick_size,
                offset_ticks=self.offset_ticks,
            ),
            time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
        )
        return TradingPlan(
            cancellations=tuple(CancelIntent(order_id) for order_id in active_order_ids),
            decision=decision,
        )
