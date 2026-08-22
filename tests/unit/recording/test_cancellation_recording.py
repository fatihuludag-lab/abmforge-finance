"""Tests for cancellation provenance recording."""

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
    Trader,
    TradingDecision,
)
from abmforge_finance.exceptions import RecordingStateError
from abmforge_finance.recording import FinanceRecordingConfig, FinanceResearchRecorder


class HoldPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.hold()


def _fixture() -> tuple[Exchange, FinanceResearchRecorder, Order]:
    exchange = Exchange(Instrument("ACME", Decimal("1"), Decimal("1")))
    exchange.register(Account("a", Decimal("1000")), Portfolio("a"))
    recorder = FinanceResearchRecorder()
    recorder.start(exchange, (Trader("a", HoldPolicy()),))
    order = Order(
        "o-1",
        "a",
        "ACME",
        Side.BUY,
        OrderType.LIMIT,
        Decimal("2"),
        Decimal("2"),
        Decimal("99"),
        0,
        0,
        TimeInForce.GOOD_TIL_CANCELLED,
    )
    exchange.submit(order)
    return exchange, recorder, order


def test_successful_cancellation_preserves_order_provenance() -> None:
    exchange, recorder, _ = _fixture()
    cancelled = exchange.cancel("o-1", participant_id="a")
    recorder.record_cancellation(period=1, sequence_number=0, order=cancelled)

    row = recorder.dataset.cancellations[0]
    assert row.period == 1
    assert row.sequence_number == 0
    assert row.agent_id == "a"
    assert row.order_id == "o-1"
    assert row.order_sequence_number == 0
    assert row.limit_price == Decimal("99")
    assert row.cancelled_quantity == Decimal("2")


def test_cancellation_recording_can_be_disabled() -> None:
    exchange = Exchange(Instrument("ACME", Decimal("1"), Decimal("1")))
    exchange.register(Account("a", Decimal("1000")), Portfolio("a"))
    recorder = FinanceResearchRecorder(FinanceRecordingConfig(record_cancellations=False))
    recorder.start(exchange, (Trader("a", HoldPolicy()),))
    order = Order(
        "o-1",
        "a",
        "ACME",
        Side.BUY,
        OrderType.LIMIT,
        Decimal("1"),
        Decimal("1"),
        Decimal("99"),
        0,
        0,
        TimeInForce.GOOD_TIL_CANCELLED,
    )
    exchange.submit(order)
    cancelled = exchange.cancel("o-1", participant_id="a")
    recorder.record_cancellation(period=1, sequence_number=0, order=cancelled)
    assert recorder.dataset.cancellations == ()


def test_invalid_cancellation_sequence_is_rejected() -> None:
    _, recorder, order = _fixture()
    with pytest.raises(RecordingStateError, match="sequence_number"):
        recorder.record_cancellation(period=1, sequence_number=-1, order=order)
