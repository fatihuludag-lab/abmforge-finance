"""Directional baseline policy driven by price-fundamental deviation."""

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
class FundamentalPolicy:
    """Trade toward the latent fundamental value when a price gap exceeds a threshold.

    This first baseline emits market IOC decisions. It represents directional response
    to mispricing, not an optimal execution model or a claim about empirical trader
    behavior.
    """

    quantity: Decimal
    minimum_gap: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        validate_positive_quantity(self.quantity)
        validate_non_negative_decimal(self.minimum_gap, field_name="minimum_gap")

    def decide(
        self,
        observation: MarketObservation,
        *,
        agent_id: str,
    ) -> TradingDecision:
        """Buy below fundamental, sell above fundamental, otherwise hold."""

        if not isinstance(observation, MarketObservation):
            raise InvalidPolicyError("observation must be a MarketObservation")
        if not isinstance(agent_id, str) or not agent_id.strip():
            raise InvalidPolicyError("agent_id must be a non-empty string")
        reference = observation.reference_price
        if reference is None:
            return TradingDecision.hold()
        gap = observation.fundamental_value - reference
        if gap > self.minimum_gap:
            return TradingDecision.market(Side.BUY, self.quantity)
        if gap < -self.minimum_gap:
            return TradingDecision.market(Side.SELL, self.quantity)
        return TradingDecision.hold()
