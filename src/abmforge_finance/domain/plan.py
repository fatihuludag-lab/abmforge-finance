"""Immutable cancel/replace planning primitives."""

from __future__ import annotations

from dataclasses import dataclass

from abmforge_finance.domain.decision import TradingDecision
from abmforge_finance.exceptions import InvalidTradingPlanError


@dataclass(frozen=True, slots=True)
class CancelIntent:
    """Request cancellation of one active order owned by the planning trader."""

    order_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.order_id, str) or not self.order_id.strip():
            raise InvalidTradingPlanError("cancel order_id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class TradingPlan:
    """Zero or more cancellations plus exactly one existing trading decision."""

    cancellations: tuple[CancelIntent, ...]
    decision: TradingDecision

    def __post_init__(self) -> None:
        if not isinstance(self.cancellations, tuple) or not all(
            isinstance(intent, CancelIntent) for intent in self.cancellations
        ):
            raise InvalidTradingPlanError("cancellations must be a tuple of CancelIntent values")
        if not isinstance(self.decision, TradingDecision):
            raise InvalidTradingPlanError("decision must be a TradingDecision")
        order_ids = tuple(intent.order_id for intent in self.cancellations)
        if len(set(order_ids)) != len(order_ids):
            raise InvalidTradingPlanError("duplicate cancellation order_id values are not allowed")

    @classmethod
    def from_decision(cls, decision: TradingDecision) -> TradingPlan:
        """Normalize one legacy decision into a no-cancellation plan."""

        return cls(cancellations=(), decision=decision)
