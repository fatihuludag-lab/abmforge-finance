"""Tests for immutable order value objects."""

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from abmforge_finance import InvalidOrderError, Order, OrderType, Side, TimeInForce


def make_limit_order(**overrides: object) -> Order:
    """Create a valid limit order with selected field overrides."""
    values: dict[str, object] = {
        "order_id": "o-1",
        "agent_id": "a-1",
        "instrument_id": "ACME",
        "side": Side.BUY,
        "order_type": OrderType.LIMIT,
        "quantity": Decimal("10"),
        "remaining_quantity": Decimal("10"),
        "price": Decimal("99.50"),
        "submitted_at": 1,
        "sequence_number": 2,
        "time_in_force": TimeInForce.GOOD_TIL_CANCELLED,
    }
    values.update(overrides)
    return Order(**values)  # type: ignore[arg-type]


def test_limit_order_exposes_fill_state_without_mutation() -> None:
    """Fill state is derived exactly and updates return a new value."""
    original = make_limit_order()
    partial = original.with_remaining_quantity(Decimal("4"))
    filled = partial.with_remaining_quantity(Decimal("0"))

    assert original.remaining_quantity == Decimal("10")
    assert partial.filled_quantity == Decimal("6")
    assert not partial.is_filled
    assert filled.filled_quantity == Decimal("10")
    assert filled.is_filled


def test_order_is_frozen() -> None:
    """Orders cannot be mutated in place."""
    order = make_limit_order()

    with pytest.raises(FrozenInstanceError):
        order.price = Decimal("100")  # type: ignore[misc]


def test_valid_market_order_requires_no_price_and_ioc() -> None:
    """Market orders are represented as non-resting IOC instructions."""
    order = make_limit_order(
        order_type=OrderType.MARKET,
        price=None,
        time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
    )

    assert order.price is None
    assert order.order_type is OrderType.MARKET


@pytest.mark.parametrize("field", ["order_id", "agent_id", "instrument_id"])
def test_order_rejects_blank_identifiers(field: str) -> None:
    """All order identifiers must be non-empty."""
    with pytest.raises(InvalidOrderError):
        make_limit_order(**{field: " "})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("side", "buy"),
        ("order_type", "limit"),
        ("time_in_force", "gtc"),
        ("quantity", Decimal("0")),
        ("quantity", Decimal("NaN")),
        ("quantity", 10.0),
        ("remaining_quantity", Decimal("-1")),
        ("remaining_quantity", Decimal("11")),
        ("submitted_at", -1),
        ("submitted_at", float("inf")),
        ("submitted_at", True),
        ("sequence_number", -1),
        ("sequence_number", 1.5),
        ("sequence_number", False),
    ],
)
def test_order_rejects_invalid_general_fields(field: str, value: object) -> None:
    """Invalid typed, numeric, and ordering fields are rejected."""
    with pytest.raises(InvalidOrderError):
        make_limit_order(**{field: value})


@pytest.mark.parametrize("price", [None, Decimal("0"), Decimal("-1"), 99.5])
def test_limit_order_rejects_invalid_price(price: object) -> None:
    """Limit orders require a finite positive Decimal price."""
    with pytest.raises(InvalidOrderError):
        make_limit_order(price=price)


def test_market_order_rejects_price() -> None:
    """A market order cannot carry a limit price."""
    with pytest.raises(InvalidOrderError):
        make_limit_order(
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        )


def test_market_order_rejects_gtc() -> None:
    """A market order cannot rest in the first research core."""
    with pytest.raises(InvalidOrderError):
        make_limit_order(order_type=OrderType.MARKET, price=None)


def test_remaining_quantity_cannot_increase() -> None:
    """Fill transformations are monotonic."""
    partial = make_limit_order(remaining_quantity=Decimal("4"))

    with pytest.raises(InvalidOrderError):
        partial.with_remaining_quantity(Decimal("5"))


@pytest.mark.parametrize("remaining", [Decimal("-1"), Decimal("NaN"), 1.0])
def test_remaining_quantity_transformation_validates_input(remaining: object) -> None:
    """Replacement remaining quantities retain the original validation contract."""
    with pytest.raises(InvalidOrderError):
        make_limit_order().with_remaining_quantity(remaining)  # type: ignore[arg-type]
