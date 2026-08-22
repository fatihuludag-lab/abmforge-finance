"""Policy protocol and shared deterministic validation helpers."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol, runtime_checkable

from abmforge_finance.domain import MarketObservation, TradingDecision, TradingPlan
from abmforge_finance.exceptions import InvalidPolicyError

_ZERO = Decimal("0")


def validate_positive_quantity(quantity: object) -> Decimal:
    """Return a finite positive policy quantity."""

    if not isinstance(quantity, Decimal):
        raise InvalidPolicyError("quantity must be a Decimal")
    if not quantity.is_finite() or quantity <= _ZERO:
        raise InvalidPolicyError("quantity must be finite and positive")
    return quantity


def validate_non_negative_decimal(value: object, *, field_name: str) -> Decimal:
    """Return a finite non-negative policy parameter."""

    if not isinstance(value, Decimal):
        raise InvalidPolicyError(f"{field_name} must be a Decimal")
    if not value.is_finite() or value < _ZERO:
        raise InvalidPolicyError(f"{field_name} must be finite and non-negative")
    return value


@runtime_checkable
class TradingPolicy(Protocol):
    """Structural interface for one-decision trading-policy logic."""

    def decide(
        self,
        observation: MarketObservation,
        *,
        agent_id: str,
    ) -> TradingDecision:
        """Return one immutable decision for an immutable market observation."""

        ...


@runtime_checkable
class TradingPlanPolicy(Protocol):
    """Structural interface for cancel/replace-aware trading-policy logic."""

    def plan(
        self,
        observation: MarketObservation,
        *,
        agent_id: str,
        active_order_ids: tuple[str, ...],
    ) -> TradingPlan:
        """Return cancellations plus exactly one immutable trading decision."""

        ...
