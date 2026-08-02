"""Tests for finance-domain enumerations."""

from abmforge_finance import OrderType, Side, TimeInForce


def test_enum_values_are_stable_strings() -> None:
    """Serialized enum values remain explicit and lowercase."""
    assert Side.BUY.value == "buy"
    assert Side.SELL.value == "sell"
    assert OrderType.LIMIT.value == "limit"
    assert OrderType.MARKET.value == "market"
    assert TimeInForce.GOOD_TIL_CANCELLED.value == "gtc"
    assert TimeInForce.IMMEDIATE_OR_CANCEL.value == "ioc"


def test_side_opposite_is_involutive() -> None:
    """Taking the opposite side twice returns the original side."""
    assert Side.BUY.opposite is Side.SELL
    assert Side.SELL.opposite is Side.BUY
    assert Side.BUY.opposite.opposite is Side.BUY
