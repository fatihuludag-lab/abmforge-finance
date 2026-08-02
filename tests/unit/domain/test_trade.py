"""Tests for immutable trade value objects."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from abmforge_finance import InvalidTradeError, Side, Trade


def make_trade(**overrides: object) -> Trade:
    """Create a valid trade with selected field overrides."""
    values: dict[str, object] = {
        "trade_id": "t-1",
        "instrument_id": "ACME",
        "buy_order_id": "buy-1",
        "sell_order_id": "sell-1",
        "buyer_id": "buyer",
        "seller_id": "seller",
        "price": Decimal("100.25"),
        "quantity": Decimal("3"),
        "executed_at": 2,
        "sequence_number": 7,
        "maker_order_id": "sell-1",
        "taker_order_id": "buy-1",
        "buyer_fee": Decimal("0.30"),
        "seller_fee": Decimal("-0.05"),
    }
    values.update(overrides)
    return Trade(**values)  # type: ignore[arg-type]


def test_trade_derives_notional_fees_and_liquidity_sides() -> None:
    """Trade accounting and maker/taker attribution are exact."""
    trade = make_trade()

    assert trade.notional == Decimal("300.75")
    assert trade.total_fees == Decimal("0.25")
    assert trade.maker_side is Side.SELL
    assert trade.taker_side is Side.BUY
    assert trade.maker_fee == Decimal("-0.05")
    assert trade.taker_fee == Decimal("0.30")


def test_buy_maker_fee_attribution() -> None:
    """Maker fee attribution follows the maker order rather than participant order."""
    trade = make_trade(maker_order_id="buy-1", taker_order_id="sell-1")

    assert trade.maker_side is Side.BUY
    assert trade.taker_side is Side.SELL
    assert trade.maker_fee == Decimal("0.30")
    assert trade.taker_fee == Decimal("-0.05")


def test_trade_is_frozen() -> None:
    """Executed trades cannot be mutated after construction."""
    trade = make_trade()

    with pytest.raises(FrozenInstanceError):
        trade.quantity = Decimal("4")  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    [
        "trade_id",
        "instrument_id",
        "buy_order_id",
        "sell_order_id",
        "buyer_id",
        "seller_id",
        "maker_order_id",
        "taker_order_id",
    ],
)
def test_trade_rejects_blank_identifiers(field: str) -> None:
    """All trade identifiers must be non-empty."""
    with pytest.raises(InvalidTradeError):
        make_trade(**{field: " "})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("price", Decimal("0")),
        ("price", Decimal("NaN")),
        ("price", 100.0),
        ("quantity", Decimal("0")),
        ("quantity", Decimal("-1")),
        ("buyer_fee", Decimal("Infinity")),
        ("buyer_fee", 0.1),
        ("seller_fee", Decimal("NaN")),
        ("executed_at", -1),
        ("executed_at", float("nan")),
        ("executed_at", False),
        ("sequence_number", -1),
        ("sequence_number", 1.5),
        ("sequence_number", True),
    ],
)
def test_trade_rejects_invalid_numeric_fields(field: str, value: object) -> None:
    """Trade values must satisfy exact type and numeric constraints."""
    with pytest.raises(InvalidTradeError):
        make_trade(**{field: value})


def test_trade_rejects_same_buy_and_sell_order() -> None:
    """One order cannot occupy both sides of a trade."""
    with pytest.raises(InvalidTradeError):
        make_trade(sell_order_id="buy-1", maker_order_id="buy-1", taker_order_id="buy-1")


def test_trade_rejects_same_maker_and_taker_order() -> None:
    """Maker and taker must be distinct matched orders."""
    with pytest.raises(InvalidTradeError):
        make_trade(maker_order_id="buy-1", taker_order_id="buy-1")


def test_trade_rejects_unmatched_maker_or_taker_identifier() -> None:
    """Maker and taker identifiers must exactly cover the matched orders."""
    with pytest.raises(InvalidTradeError):
        make_trade(maker_order_id="other", taker_order_id="buy-1")
