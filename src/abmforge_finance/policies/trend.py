"""Directional baseline trend-following policy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.domain import MarketObservation, Side, TradingDecision
from abmforge_finance.exceptions import InvalidPolicyError
from abmforge_finance.policies.base import (
    validate_non_negative_decimal,
    validate_positive_quantity,
)


@dataclass(frozen=True, slots=True)
class TrendFollowingPolicy:
    """Follow the signed price change supplied by the observation builder."""

    quantity: Decimal
    minimum_change: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        validate_positive_quantity(self.quantity)
        validate_non_negative_decimal(self.minimum_change, field_name="minimum_change")

    def decide(
        self,
        observation: MarketObservation,
        *,
        agent_id: str,
    ) -> TradingDecision:
        """Buy positive trends, sell negative trends, and hold inside the dead band."""

        if not isinstance(observation, MarketObservation):
            raise InvalidPolicyError("observation must be a MarketObservation")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise InvalidPolicyError("agent_id must be a non-empty string")
        change = observation.price_change
        if change is None:
            return TradingDecision.hold()
        if change > self.minimum_change:
            return TradingDecision.market(Side.BUY, self.quantity)
        if change < -self.minimum_change:
            return TradingDecision.market(Side.SELL, self.quantity)
        return TradingDecision.hold()
