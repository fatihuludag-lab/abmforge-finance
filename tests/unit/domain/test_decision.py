"""Unit tests for immutable policy decisions."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    DecisionKind,
    InvalidDecisionError,
    OrderType,
    Side,
    TimeInForce,
    TradingDecision,
)


def test_hold_decision_carries_no_order_fields() -> None:
    decision = TradingDecision.hold()
    assert decision.kind is DecisionKind.HOLD
    assert decision.is_hold
    assert decision.side is None


def test_market_decision_is_ioc_and_price_free() -> None:
    decision = TradingDecision.market(Side.BUY, Decimal("2"))
    assert decision.kind is DecisionKind.ORDER
    assert decision.order_type is OrderType.MARKET
    assert decision.time_in_force is TimeInForce.IMMEDIATE_OR_CANCEL
    assert decision.price is None


def test_limit_decision_preserves_exact_economic_intent() -> None:
    decision = TradingDecision.limit(Side.SELL, Decimal("3"), Decimal("101.25"))
    assert decision.side is Side.SELL
    assert decision.quantity == Decimal("3")
    assert decision.price == Decimal("101.25")
    assert decision.time_in_force is TimeInForce.GOOD_TIL_CANCELLED


def test_hold_with_order_fields_is_rejected() -> None:
    with pytest.raises(InvalidDecisionError):
        TradingDecision(kind=DecisionKind.HOLD, side=Side.BUY)


def test_invalid_market_time_in_force_is_rejected() -> None:
    with pytest.raises(InvalidDecisionError, match="market decisions must be IOC"):
        TradingDecision(
            kind=DecisionKind.ORDER,
            side=Side.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("1"),
            time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
        )
