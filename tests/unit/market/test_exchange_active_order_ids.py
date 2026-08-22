"""Tests for participant-scoped active-order introspection."""

from decimal import Decimal

import pytest

from abmforge_finance import (
    Account,
    Exchange,
    Instrument,
    Order,
    OrderType,
    Portfolio,
    Side,
    TimeInForce,
    UnknownParticipantError,
)


def _order(order_id: str, sequence: int, agent_id: str, side: Side, price: str) -> Order:
    return Order(
        order_id=order_id,
        agent_id=agent_id,
        instrument_id="ACME",
        side=side,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        price=Decimal(price),
        submitted_at=0,
        sequence_number=sequence,
        time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
    )


def test_active_order_ids_are_scoped_and_submission_ordered() -> None:
    exchange = Exchange(Instrument("ACME", Decimal("1"), Decimal("1")))
    exchange.register(
        Account("a", Decimal("1000")),
        Portfolio("a", (("ACME", Decimal("2")),)),
    )
    exchange.register(
        Account("b", Decimal("1000")),
        Portfolio("b", (("ACME", Decimal("2")),)),
    )

    exchange.submit(_order("a-bid", 0, "a", Side.BUY, "98"))
    exchange.submit(_order("b-bid", 1, "b", Side.BUY, "97"))
    exchange.submit(_order("a-ask", 2, "a", Side.SELL, "102"))

    assert exchange.active_order_ids("a") == ("a-bid", "a-ask")
    assert exchange.active_order_ids("b") == ("b-bid",)

    exchange.cancel("a-bid", participant_id="a")
    assert exchange.active_order_ids("a") == ("a-ask",)


def test_active_order_ids_requires_registered_participant() -> None:
    exchange = Exchange(Instrument("ACME", Decimal("1"), Decimal("1")))
    with pytest.raises(UnknownParticipantError):
        exchange.active_order_ids("missing")
