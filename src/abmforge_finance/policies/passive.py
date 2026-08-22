"""Deterministic one-shot passive-liquidity baseline policy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from abmforge_finance.domain import MarketObservation, Side, TimeInForce, TradingDecision
from abmforge_finance.exceptions import InvalidPolicyError
from abmforge_finance.policies.base import validate_positive_quantity

_ZERO = Decimal("0")


def _positive_decimal(value: object, *, field_name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise InvalidPolicyError(f"{field_name} must be a Decimal")
    if not value.is_finite() or value <= _ZERO:
        raise InvalidPolicyError(f"{field_name} must be finite and positive")
    return value


@dataclass(frozen=True, slots=True)
class PassiveLiquidityPolicy:
    """Emit one passive GTC quote around the latent fundamental value.

    One policy instance owns exactly one side of liquidity. Two independently funded
    traders can therefore form a deterministic two-sided baseline without extending
    the one-decision-per-trader contract. The quote is emitted only on ``quote_step``;
    all other periods produce ``HOLD``.

    ``offset_ticks`` is measured outward from the executable tick grid nearest the
    fundamental: BUY uses floor(reference/tick) minus the offset, while SELL uses
    ceiling(reference/tick) plus the offset. This guarantees a non-crossing quote pair
    when BUY and SELL policies share the same configuration.
    """

    side: Side
    quantity: Decimal
    tick_size: Decimal
    offset_ticks: int = 1
    quote_step: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.side, Side):
            raise InvalidPolicyError("side must be a Side")
        validate_positive_quantity(self.quantity)
        _positive_decimal(self.tick_size, field_name="tick_size")
        if (
            isinstance(self.offset_ticks, bool)
            or not isinstance(self.offset_ticks, int)
            or self.offset_ticks < 1
        ):
            raise InvalidPolicyError("offset_ticks must be a positive integer")
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

        if not isinstance(observation, MarketObservation):
            raise InvalidPolicyError("observation must be a MarketObservation")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise InvalidPolicyError("agent_id must be a non-empty string")
        if observation.step != self.quote_step:
            return TradingDecision.hold()

        ratio = observation.fundamental_value / self.tick_size
        if self.side is Side.BUY:
            anchor = int(ratio.to_integral_value(rounding=ROUND_FLOOR))
            quote_ticks = anchor - self.offset_ticks
        else:
            anchor = int(ratio.to_integral_value(rounding=ROUND_CEILING))
            quote_ticks = anchor + self.offset_ticks

        if quote_ticks <= 0:
            raise InvalidPolicyError(
                "passive quote would be non-positive; reduce tick_size/offset or "
                "increase the fundamental reference"
            )

        price = self.tick_size * quote_ticks
        return TradingDecision.limit(
            self.side,
            self.quantity,
            price,
            time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
        )
