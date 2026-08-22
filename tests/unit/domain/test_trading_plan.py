"""Tests for immutable cancel/replace trading plans."""

import pytest

from abmforge_finance import (
    CancelIntent,
    InvalidTradingPlanError,
    TradingDecision,
    TradingPlan,
)


def test_cancel_intent_requires_non_empty_identifier() -> None:
    assert CancelIntent("order-1").order_id == "order-1"
    with pytest.raises(InvalidTradingPlanError):
        CancelIntent("")
    with pytest.raises(InvalidTradingPlanError):
        CancelIntent(1)  # type: ignore[arg-type]


def test_plan_normalizes_legacy_decision() -> None:
    decision = TradingDecision.hold()
    assert TradingPlan.from_decision(decision) == TradingPlan((), decision)


def test_plan_rejects_duplicate_cancellation_identifiers() -> None:
    with pytest.raises(InvalidTradingPlanError, match="duplicate"):
        TradingPlan(
            (CancelIntent("order-1"), CancelIntent("order-1")),
            TradingDecision.hold(),
        )


def test_plan_rejects_invalid_payload_types() -> None:
    with pytest.raises(InvalidTradingPlanError, match="cancellations"):
        TradingPlan([], TradingDecision.hold())  # type: ignore[arg-type]
    with pytest.raises(InvalidTradingPlanError, match="decision"):
        TradingPlan((), object())  # type: ignore[arg-type]
