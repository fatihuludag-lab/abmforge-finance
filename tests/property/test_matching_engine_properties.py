"""Property tests for matching-engine conservation and reproducibility."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from abmforge_finance import (
    Instrument,
    MatchingEngine,
    Order,
    OrderType,
    Side,
    TimeInForce,
)

_ASK_BOOKS = st.lists(
    st.tuples(
        st.integers(min_value=10_000, max_value=10_100),
        st.integers(min_value=1, max_value=20),
    ),
    min_size=1,
    max_size=10,
)


def make_limit_ask(index: int, price_ticks: int, quantity: int) -> Order:
    """Create one passive ask with deterministic submission metadata."""
    value = Decimal(quantity)
    return Order(
        order_id=f"ask-{index}",
        agent_id=f"agent-ask-{index}",
        instrument_id="ACME",
        side=Side.SELL,
        order_type=OrderType.LIMIT,
        quantity=value,
        remaining_quantity=value,
        price=Decimal(price_ticks) * Decimal("0.01"),
        submitted_at=0,
        sequence_number=index,
        time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
    )


def make_market_buy(sequence_number: int, quantity: int) -> Order:
    """Create one IOC market buy after the passive ask stream."""
    value = Decimal(quantity)
    return Order(
        order_id="market-buy",
        agent_id="agent-market-buy",
        instrument_id="ACME",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=value,
        remaining_quantity=value,
        price=None,
        submitted_at=1,
        sequence_number=sequence_number,
        time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
    )


@given(_ASK_BOOKS, st.integers(min_value=1, max_value=200))
def test_market_buy_conserves_quantity_across_trades_residual_and_book(
    specs: list[tuple[int, int]], incoming_quantity: int
) -> None:
    """Matching transfers exact lots without creating or destroying quantity."""
    instrument = Instrument("ACME", Decimal("0.01"), Decimal("1"))
    engine = MatchingEngine(instrument)
    initial_depth = sum(quantity for _, quantity in specs)

    for index, (price_ticks, quantity) in enumerate(specs):
        engine.submit(make_limit_ask(index, price_ticks, quantity))

    result = engine.submit(make_market_buy(len(specs), incoming_quantity))
    executed = sum((trade.quantity for trade in result.trades), start=Decimal("0"))
    remaining_book = sum(
        (level.total_quantity for level in engine.book.depth(Side.SELL)), start=Decimal("0")
    )

    assert executed == Decimal(min(incoming_quantity, initial_depth))
    assert result.unfilled_quantity == Decimal(max(incoming_quantity - initial_depth, 0))
    assert remaining_book == Decimal(max(initial_depth - incoming_quantity, 0))
    assert executed + result.unfilled_quantity == Decimal(incoming_quantity)
    assert executed + remaining_book == Decimal(initial_depth)
    assert [trade.sequence_number for trade in result.trades] == list(range(len(result.trades)))
    trade_prices = [trade.price for trade in result.trades]
    assert trade_prices == sorted(trade_prices)
    engine.book.validate_invariants()


@given(_ASK_BOOKS, st.integers(min_value=1, max_value=200))
def test_identical_explicit_order_streams_replay_exactly(
    specs: list[tuple[int, int]], incoming_quantity: int
) -> None:
    """Two engines fed identical events produce identical trades and final state."""
    instrument = Instrument("ACME", Decimal("0.01"), Decimal("1"))
    left = MatchingEngine(instrument)
    right = MatchingEngine(instrument)

    orders = [
        make_limit_ask(index, price_ticks, quantity)
        for index, (price_ticks, quantity) in enumerate(specs)
    ]
    orders.append(make_market_buy(len(specs), incoming_quantity))

    left_results = tuple(left.submit(order) for order in orders)
    right_results = tuple(right.submit(order) for order in orders)

    assert left_results == right_results
    assert left.book.snapshot() == right.book.snapshot()
    assert left.next_trade_sequence == right.next_trade_sequence
