"""Tests for deterministic dynamic passive-liquidity planning."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    DynamicPassiveLiquidityPolicy,
    InvalidPolicyError,
    MarketObservation,
    Side,
    TimeInForce,
)


def _obs(step: int, fundamental: str) -> MarketObservation:
    return MarketObservation(
        step=step,
        instrument_id="ACME",
        fundamental_value=Decimal(fundamental),
    )


def test_dynamic_policy_cancels_known_quote_and_requotes_current_fundamental() -> None:
    policy = DynamicPassiveLiquidityPolicy(
        Side.BUY,
        Decimal("10"),
        Decimal("1"),
    )

    first = policy.plan(_obs(0, "100"), agent_id="lp", active_order_ids=())
    assert first.cancellations == ()
    assert first.decision.price == Decimal("99")

    second = policy.plan(
        _obs(1, "102"),
        agent_id="lp",
        active_order_ids=("finance-order-000000000000",),
    )
    assert tuple(intent.order_id for intent in second.cancellations) == (
        "finance-order-000000000000",
    )
    assert second.decision.price == Decimal("101")
    assert second.decision.time_in_force is TimeInForce.GOOD_TIL_CANCELLED


def test_dynamic_sell_quote_rounds_outward_on_non_grid_reference() -> None:
    policy = DynamicPassiveLiquidityPolicy(
        Side.SELL,
        Decimal("1"),
        Decimal("1"),
    )
    plan = policy.plan(
        _obs(0, "100.25"),
        agent_id="lp",
        active_order_ids=(),
    )
    assert plan.decision.price == Decimal("102")


@pytest.mark.parametrize("active", [["order-1"], ("",), (1,)])
def test_dynamic_policy_rejects_invalid_active_order_identifiers(active: object) -> None:
    policy = DynamicPassiveLiquidityPolicy(
        Side.BUY,
        Decimal("1"),
        Decimal("1"),
    )
    with pytest.raises(InvalidPolicyError, match="active_order_ids"):
        policy.plan(
            _obs(0, "100"),
            agent_id="lp",
            active_order_ids=active,  # type: ignore[arg-type]
        )


def test_dynamic_policy_reuses_static_quote_configuration_validation() -> None:
    with pytest.raises(InvalidPolicyError):
        DynamicPassiveLiquidityPolicy(
            Side.BUY,
            Decimal("0"),
            Decimal("1"),
        )
