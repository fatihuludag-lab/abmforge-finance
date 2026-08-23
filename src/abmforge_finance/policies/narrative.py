"""Deterministic narrative-driven directional trading policy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from abmforge_finance.domain import (
    MarketObservation,
    NarrativeExposure,
    NarrativeSignal,
    NarrativeState,
    Side,
    TradingDecision,
)
from abmforge_finance.domain._validation import require_non_empty_text
from abmforge_finance.domain.narrative import (
    _aggregate_narrative_signal_validated,
    _validate_narrative_configuration,
)
from abmforge_finance.exceptions import InvalidNarrativeError, InvalidPolicyError
from abmforge_finance.policies.base import (
    validate_non_negative_decimal,
    validate_positive_quantity,
)


@dataclass(frozen=True, slots=True)
class NarrativePolicy:
    """Map frozen narrative pressure to market buy/sell/hold decisions.

    The policy is intentionally independent of price and fundamental-value signals.
    Phase 10A isolates the narrative-to-decision mechanism before introducing
    population-homogeneity treatments or external AI/LLM narrative generation.
    """

    quantity: Decimal
    narratives: tuple[NarrativeState, ...]
    exposures: tuple[NarrativeExposure, ...]
    decision_threshold: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        validate_positive_quantity(self.quantity)
        validate_non_negative_decimal(
            self.decision_threshold,
            field_name="decision_threshold",
        )
        try:
            _validate_narrative_configuration(self.narratives, self.exposures)
        except InvalidNarrativeError as error:
            raise InvalidPolicyError(f"invalid narrative configuration: {error}") from error

    def signal(
        self,
        observation: MarketObservation,
        *,
        agent_id: str,
    ) -> NarrativeSignal:
        """Return the exact narrative signal used for one decision."""

        if not isinstance(observation, MarketObservation):
            raise InvalidPolicyError("observation must be a MarketObservation")
        try:
            validated_agent = require_non_empty_text(
                agent_id,
                field_name="agent_id",
                error_type=InvalidNarrativeError,
            )
        except InvalidNarrativeError as error:
            raise InvalidPolicyError(str(error)) from error

        return _aggregate_narrative_signal_validated(
            self.narratives,
            self.exposures,
            agent_id=validated_agent,
            step=observation.step,
        )

    def decide(
        self,
        observation: MarketObservation,
        *,
        agent_id: str,
    ) -> TradingDecision:
        """Buy above the positive threshold, sell below its negative, else hold."""

        signal = self.signal(observation, agent_id=agent_id)
        if signal.value > self.decision_threshold:
            return TradingDecision.market(Side.BUY, self.quantity)
        if signal.value < -self.decision_threshold:
            return TradingDecision.market(Side.SELL, self.quantity)
        return TradingDecision.hold()
