"""Unit tests for exact finance research recording."""

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


def _exchange_and_traders() -> tuple[Exchange, tuple[Trader, ...]]:
    exchange = Exchange(Instrument("ACME", Decimal("1"), Decimal("1")))
    exchange.register(Account("b", Decimal("200")), Portfolio("b", (("ACME", Decimal("2")),)))
    exchange.register(Account("a", Decimal("100")), Portfolio("a"))
    return exchange, (Trader("b", HoldPolicy()), Trader("a", HoldPolicy()))


def test_start_captures_sorted_participants_and_initial_balances() -> None:
    exchange, traders = _exchange_and_traders()
    recorder = FinanceResearchRecorder()
    recorder.start(exchange, traders)
    dataset = recorder.dataset

    assert tuple(row.agent_id for row in dataset.participants) == ("a", "b")
    assert tuple(row.agent_id for row in dataset.accounts) == ("a", "b")
    assert tuple(row.phase for row in dataset.accounts) == ("initial", "initial")
    assert tuple(row.quantity for row in dataset.positions) == (Decimal("0"), Decimal("2"))
    assert dataset.participants[1].initial_cash == Decimal("200")


def test_recorder_requires_start_and_rejects_duplicate_start() -> None:
    exchange, traders = _exchange_and_traders()
    recorder = FinanceResearchRecorder()
    with pytest.raises(RecordingStateError, match="not been started"):
        recorder.record_decision(period=0, agent_id="a", decision=TradingDecision.hold())

    recorder.start(exchange, traders)
    with pytest.raises(RecordingStateError, match="only start once"):
        recorder.start(exchange, traders)


def test_recording_config_can_disable_optional_tables() -> None:
    exchange, traders = _exchange_and_traders()
    recorder = FinanceResearchRecorder(
        FinanceRecordingConfig(
            record_decisions=False,
            record_orders=False,
            record_trades=False,
            record_market_states=False,
            record_accounts=False,
            record_positions=False,
        )
    )
    recorder.start(exchange, traders)
    recorder.record_decision(period=0, agent_id="a", decision=TradingDecision.hold())
    recorder.record_market_state(
        period=0,
        fundamental_value=Decimal("100"),
        snapshot=exchange.snapshot(),
        last_trade_price=None,
        price_change=None,
        fee_balance=exchange.fee_balance,
    )
    assert recorder.dataset.row_counts == {
        "participants": 2,
        "decisions": 0,
        "cancellations": 0,
        "orders": 0,
        "trades": 0,
        "market_states": 0,
        "accounts": 0,
        "positions": 0,
    }


def test_rejected_and_accepted_orders_preserve_exact_outcomes() -> None:
    exchange, traders = _exchange_and_traders()
    recorder = FinanceResearchRecorder()
    recorder.start(exchange, traders)

    rejected = Order(
        order_id="rejected",
        agent_id="a",
        instrument_id="ACME",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        price=Decimal("99"),
        submitted_at=0,
        sequence_number=0,
        time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
    )
    recorder.record_order(
        period=0,
        order=rejected,
        exchange_result=None,
        rejection_type="SyntheticRejection",
        rejection_message="controlled",
    )

    accepted = Order(
        order_id="accepted",
        agent_id="a",
        instrument_id="ACME",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        price=Decimal("98"),
        submitted_at=0,
        sequence_number=1,
        time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
    )
    result = exchange.submit(accepted)
    recorder.record_order(period=0, order=accepted, exchange_result=result)

    rows = recorder.dataset.orders
    assert rows[0].accepted is False
    assert rows[0].executed_quantity == Decimal("0")
    assert rows[0].rejection_type == "SyntheticRejection"
    assert rows[1].accepted is True
    assert rows[1].rested is True
    assert rows[1].remaining_quantity == Decimal("1")


def test_order_outcome_metadata_must_be_consistent() -> None:
    exchange, traders = _exchange_and_traders()
    recorder = FinanceResearchRecorder()
    recorder.start(exchange, traders)
    order = Order(
        order_id="o",
        agent_id="a",
        instrument_id="ACME",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        price=Decimal("99"),
        submitted_at=0,
        sequence_number=0,
        time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
    )
    result = exchange.submit(order)
    with pytest.raises(RecordingStateError, match="accepted orders"):
        recorder.record_order(
            period=0,
            order=order,
            exchange_result=result,
            rejection_type="bad",
        )

    other = Order(
        order_id="other",
        agent_id="a",
        instrument_id="ACME",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        price=Decimal("97"),
        submitted_at=0,
        sequence_number=1,
        time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
    )
    with pytest.raises(RecordingStateError, match="require rejection_type"):
        recorder.record_order(period=0, order=other, exchange_result=None)


def test_market_state_and_post_balances_are_exact() -> None:
    exchange, traders = _exchange_and_traders()
    recorder = FinanceResearchRecorder()
    recorder.start(exchange, traders)
    exchange.submit(
        Order(
            order_id="bid",
            agent_id="a",
            instrument_id="ACME",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("1"),
            remaining_quantity=Decimal("1"),
            price=Decimal("99"),
            submitted_at=0,
            sequence_number=0,
            time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
        )
    )
    recorder.record_market_state(
        period=0,
        fundamental_value=Decimal("100.25"),
        snapshot=exchange.snapshot(),
        last_trade_price=None,
        price_change=None,
        fee_balance=exchange.fee_balance,
    )
    recorder.record_balances(period=0, phase="post", exchange=exchange)

    dataset = recorder.dataset
    state = dataset.market_states[0]
    assert state.fundamental_value == Decimal("100.25")
    assert state.best_bid == Decimal("99")
    assert state.bid_depth == Decimal("1")
    assert tuple(row.phase for row in dataset.accounts[-2:]) == ("post", "post")
