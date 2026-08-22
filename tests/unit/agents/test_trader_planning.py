"""Tests for trader normalization to the planning contract."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    CancelIntent,
    InvalidTraderError,
    MarketObservation,
    Trader,
    TradingDecision,
    TradingPlan,
)


def _observation() -> MarketObservation:
    return MarketObservation(
        step=0,
        instrument_id="ACME",
        fundamental_value=Decimal("100"),
    )


class HoldPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.hold()


class PlanOnlyPolicy:
    def plan(  # type: ignore[no-untyped-def]
        self,
        observation,
        *,
        agent_id,
        active_order_ids,
    ):
        del observation, agent_id
        return TradingPlan(
            tuple(CancelIntent(order_id) for order_id in active_order_ids),
            TradingDecision.hold(),
        )


def test_legacy_policy_is_normalized_to_no_cancel_plan() -> None:
    trader = Trader("a", HoldPolicy())
    plan = trader.plan(_observation(), active_order_ids=("ignored-by-legacy",))
    assert plan.cancellations == ()
    assert plan.decision.is_hold


def test_plan_policy_receives_active_order_ids() -> None:
    trader = Trader("a", PlanOnlyPolicy())
    plan = trader.plan(_observation(), active_order_ids=("order-1", "order-2"))
    assert tuple(intent.order_id for intent in plan.cancellations) == (
        "order-1",
        "order-2",
    )
    assert plan.decision.is_hold


def test_plan_only_policy_cannot_use_legacy_decide_method() -> None:
    trader = Trader("a", PlanOnlyPolicy())
    with pytest.raises(InvalidTraderError, match="plan-only"):
        trader.decide(_observation())


def test_trader_rejects_unsupported_policy() -> None:
    with pytest.raises(InvalidTraderError, match="policy"):
        Trader("a", object())  # type: ignore[arg-type]
