"""Unit tests for deterministic incoming-order matching."""

from __future__ import annotations

from decimal import Decimal

import pytest

from abmforge_finance import (
    DuplicateOrderError,
    DuplicateSequenceNumberError,
    Instrument,
    InvalidIncomingOrderError,
    InvalidPriceError,
    InvalidQuantityError,
    MatchingEngine,
    MatchResult,
    Order,
    OrderType,
    Side,
    TimeInForce,
)


def make_instrument() -> Instrument:
    """Return the standard exact-grid instrument."""
    return Instrument("ACME", Decimal("0.01"), Decimal("1"))


def make_order(
    order_id: str,
    *,
    side: Side,
    sequence_number: int,
    quantity: str = "10",
    price: str = "100.00",
    order_type: OrderType = OrderType.LIMIT,
    time_in_force: TimeInForce = TimeInForce.GOOD_TIL_CANCELLED,
    submitted_at: int | float = 0,
    remaining_quantity: str | None = None,
    instrument_id: str = "ACME",
) -> Order:
    """Build one concise valid domain order."""
    quantity_value = Decimal(quantity)
    return Order(
        order_id=order_id,
        agent_id=f"agent-{order_id}",
        instrument_id=instrument_id,
        side=side,
        order_type=order_type,
        quantity=quantity_value,
        remaining_quantity=(
            quantity_value if remaining_quantity is None else Decimal(remaining_quantity)
        ),
        price=None if order_type is OrderType.MARKET else Decimal(price),
        submitted_at=submitted_at,
        sequence_number=sequence_number,
        time_in_force=time_in_force,
    )


def seed_ask(
    engine: MatchingEngine,
    order_id: str,
    *,
    sequence_number: int,
    price: str,
    quantity: str,
    submitted_at: int | float = 0,
) -> None:
    """Submit one non-marketable resting ask."""
    result = engine.submit(
        make_order(
            order_id,
            side=Side.SELL,
            sequence_number=sequence_number,
            price=price,
            quantity=quantity,
            submitted_at=submitted_at,
        )
    )
    assert result.rested
    assert result.trades == ()


def seed_bid(
    engine: MatchingEngine,
    order_id: str,
    *,
    sequence_number: int,
    price: str,
    quantity: str,
    submitted_at: int | float = 0,
) -> None:
    """Submit one non-marketable resting bid."""
    result = engine.submit(
        make_order(
            order_id,
            side=Side.BUY,
            sequence_number=sequence_number,
            price=price,
            quantity=quantity,
            submitted_at=submitted_at,
        )
    )
    assert result.rested
    assert result.trades == ()


def test_constructor_requires_instrument() -> None:
    """Matching requires an explicit exact-grid instrument."""
    with pytest.raises(TypeError):
        MatchingEngine("ACME")  # type: ignore[arg-type]


def test_non_crossing_gtc_limit_rests_without_trade() -> None:
    """Passive GTC liquidity is delegated to the resting book."""
    engine = MatchingEngine(make_instrument())
    order = make_order("bid", side=Side.BUY, sequence_number=1, price="99.00")

    result = engine.submit(order)

    assert result == MatchResult(final_order=order, trades=(), rested=True)
    assert result.executed_quantity == Decimal("0")
    assert result.cancelled_quantity == Decimal("0")
    assert result.resting_order_id == "bid"
    assert engine.book.get("bid") == order


def test_market_order_on_empty_book_is_cancelled_unfilled() -> None:
    """An IOC market order never fabricates liquidity or rests."""
    engine = MatchingEngine(make_instrument())
    order = make_order(
        "market",
        side=Side.BUY,
        sequence_number=1,
        quantity="7",
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
    )

    result = engine.submit(order)

    assert result.trades == ()
    assert not result.rested
    assert result.unfilled_quantity == Decimal("7")
    assert result.cancelled_quantity == Decimal("7")
    assert result.resting_order_id is None
    assert len(engine.book) == 0


def test_crossing_limit_executes_at_resting_maker_price() -> None:
    """The taker receives the maker's resting limit price."""
    engine = MatchingEngine(make_instrument())
    seed_ask(engine, "ask", sequence_number=1, price="100.00", quantity="5")

    result = engine.submit(
        make_order("buy", side=Side.BUY, sequence_number=2, price="101.00", quantity="5")
    )

    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.price == Decimal("100.00")
    assert trade.quantity == Decimal("5")
    assert trade.maker_order_id == "ask"
    assert trade.taker_order_id == "buy"
    assert trade.buyer_id == "agent-buy"
    assert trade.seller_id == "agent-ask"
    assert trade.executed_at == 0
    assert trade.sequence_number == 0
    assert trade.trade_id == "trade-000000000000"
    assert result.final_order.is_filled
    assert not result.rested
    assert len(engine.book) == 0


def test_sell_taker_preserves_maker_and_buyer_seller_attribution() -> None:
    """A resting bid remains maker while identities follow economic sides."""
    engine = MatchingEngine(make_instrument())
    seed_bid(engine, "bid", sequence_number=1, price="100.00", quantity="3")

    result = engine.submit(
        make_order("sell", side=Side.SELL, sequence_number=2, price="99.00", quantity="3")
    )
    trade = result.trades[0]

    assert trade.price == Decimal("100.00")
    assert trade.buy_order_id == "bid"
    assert trade.sell_order_id == "sell"
    assert trade.maker_order_id == "bid"
    assert trade.taker_order_id == "sell"
    assert trade.buyer_id == "agent-bid"
    assert trade.seller_id == "agent-sell"


def test_partial_fill_updates_maker_without_losing_priority() -> None:
    """A partial maker fill leaves the immutable replacement active."""
    engine = MatchingEngine(make_instrument())
    seed_ask(engine, "ask", sequence_number=1, price="100.00", quantity="10")

    result = engine.submit(
        make_order(
            "market",
            side=Side.BUY,
            sequence_number=2,
            quantity="4",
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        )
    )

    assert result.executed_quantity == Decimal("4")
    maker = engine.book.get("ask")
    assert maker is not None
    assert maker.remaining_quantity == Decimal("6")
    assert maker.sequence_number == 1
    engine.book.validate_invariants()


def test_market_order_executes_multiple_levels_in_price_time_priority() -> None:
    """One aggressor can create a deterministic trade sequence across ask levels."""
    engine = MatchingEngine(make_instrument())
    seed_ask(engine, "ask-1", sequence_number=1, price="100.00", quantity="2")
    seed_ask(engine, "ask-2", sequence_number=2, price="100.00", quantity="3")
    seed_ask(engine, "ask-3", sequence_number=3, price="101.00", quantity="4")

    result = engine.submit(
        make_order(
            "market",
            side=Side.BUY,
            sequence_number=4,
            quantity="7",
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        )
    )

    assert [(trade.maker_order_id, trade.price, trade.quantity) for trade in result.trades] == [
        ("ask-1", Decimal("100.00"), Decimal("2")),
        ("ask-2", Decimal("100.00"), Decimal("3")),
        ("ask-3", Decimal("101.00"), Decimal("2")),
    ]
    assert [trade.sequence_number for trade in result.trades] == [0, 1, 2]
    assert engine.next_trade_sequence == 3
    assert engine.book.get("ask-1") is None
    assert engine.book.get("ask-2") is None
    remaining = engine.book.get("ask-3")
    assert remaining is not None
    assert remaining.remaining_quantity == Decimal("2")
    engine.book.validate_invariants()


def test_gtc_limit_stops_at_price_constraint_and_rests_residual() -> None:
    """A limit aggressor consumes compatible liquidity then becomes passive."""
    engine = MatchingEngine(make_instrument())
    seed_ask(engine, "ask-100", sequence_number=1, price="100.00", quantity="2")
    seed_ask(engine, "ask-102", sequence_number=2, price="102.00", quantity="5")

    result = engine.submit(
        make_order("buy", side=Side.BUY, sequence_number=3, price="101.00", quantity="5")
    )

    assert [(trade.maker_order_id, trade.quantity) for trade in result.trades] == [
        ("ask-100", Decimal("2"))
    ]
    assert result.final_order.remaining_quantity == Decimal("3")
    assert result.rested
    assert engine.book.best_bid == Decimal("101.00")
    assert engine.book.best_ask == Decimal("102.00")
    assert engine.book.get("buy") == result.final_order
    engine.book.validate_invariants()


def test_ioc_limit_discards_residual_instead_of_resting() -> None:
    """IOC residual quantity is observable but absent from the resting book."""
    engine = MatchingEngine(make_instrument())
    seed_ask(engine, "ask", sequence_number=1, price="100.00", quantity="2")

    result = engine.submit(
        make_order(
            "buy-ioc",
            side=Side.BUY,
            sequence_number=2,
            price="100.00",
            quantity="5",
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        )
    )

    assert result.executed_quantity == Decimal("2")
    assert result.unfilled_quantity == Decimal("3")
    assert result.cancelled_quantity == Decimal("3")
    assert not result.rested
    assert engine.book.get("buy-ioc") is None


def test_market_residual_is_cancelled_after_available_depth() -> None:
    """Market orders consume all available compatible depth and discard the rest."""
    engine = MatchingEngine(make_instrument())
    seed_ask(engine, "ask", sequence_number=1, price="100.00", quantity="2")

    result = engine.submit(
        make_order(
            "market",
            side=Side.BUY,
            sequence_number=2,
            quantity="5",
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        )
    )

    assert result.executed_quantity == Decimal("2")
    assert result.cancelled_quantity == Decimal("3")
    assert not result.rested
    assert len(engine.book) == 0


def test_sell_market_walks_bids_from_highest_to_lowest() -> None:
    """Sell aggressors consume bid liquidity in deterministic best-price order."""
    engine = MatchingEngine(make_instrument())
    seed_bid(engine, "bid-100", sequence_number=1, price="100.00", quantity="2")
    seed_bid(engine, "bid-99", sequence_number=2, price="99.00", quantity="3")

    result = engine.submit(
        make_order(
            "market",
            side=Side.SELL,
            sequence_number=3,
            quantity="4",
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        )
    )

    assert [(trade.maker_order_id, trade.price, trade.quantity) for trade in result.trades] == [
        ("bid-100", Decimal("100.00"), Decimal("2")),
        ("bid-99", Decimal("99.00"), Decimal("2")),
    ]
    assert result.final_order.is_filled
    remaining = engine.book.get("bid-99")
    assert remaining is not None
    assert remaining.remaining_quantity == Decimal("1")


def test_duplicate_order_id_is_rejected_even_after_non_resting_ioc() -> None:
    """Submission identity is unique beyond the set of orders that ever rested."""
    engine = MatchingEngine(make_instrument())
    first = make_order(
        "same",
        side=Side.BUY,
        sequence_number=1,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
    )
    engine.submit(first)

    with pytest.raises(DuplicateOrderError):
        engine.submit(make_order("same", side=Side.BUY, sequence_number=2))


def test_duplicate_submission_sequence_is_rejected_after_ioc() -> None:
    """Submission sequence provenance includes orders that never rest."""
    engine = MatchingEngine(make_instrument())
    engine.submit(
        make_order(
            "first",
            side=Side.BUY,
            sequence_number=7,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        )
    )

    with pytest.raises(DuplicateSequenceNumberError):
        engine.submit(make_order("second", side=Side.BUY, sequence_number=7))


def test_partially_filled_value_cannot_be_resubmitted_as_fresh_order() -> None:
    """Hidden prior execution state is rejected at the submission boundary."""
    engine = MatchingEngine(make_instrument())
    order = make_order(
        "partial",
        side=Side.BUY,
        sequence_number=1,
        quantity="10",
        remaining_quantity="4",
    )

    with pytest.raises(InvalidIncomingOrderError):
        engine.submit(order)

    assert len(engine.book) == 0


def test_wrong_instrument_is_rejected_before_mutation() -> None:
    """Single-instrument matching cannot silently route foreign orders."""
    engine = MatchingEngine(make_instrument())

    with pytest.raises(InvalidIncomingOrderError):
        engine.submit(
            make_order("foreign", side=Side.BUY, sequence_number=1, instrument_id="OTHER")
        )

    assert len(engine.book) == 0


def test_off_grid_limit_price_is_rejected_before_mutation() -> None:
    """Incoming price validation uses the same exact instrument grid."""
    engine = MatchingEngine(make_instrument())

    with pytest.raises(InvalidPriceError):
        engine.submit(make_order("off-price", side=Side.BUY, sequence_number=1, price="100.005"))

    assert len(engine.book) == 0


def test_off_lot_quantity_is_rejected_before_mutation() -> None:
    """Incoming quantity validation uses the same exact lot grid."""
    engine = MatchingEngine(Instrument("ACME", Decimal("0.01"), Decimal("2")))

    with pytest.raises(InvalidQuantityError):
        engine.submit(make_order("off-lot", side=Side.BUY, sequence_number=1, quantity="3"))

    assert len(engine.book) == 0


def test_submitted_at_cannot_move_backwards() -> None:
    """Synchronous execution cannot create a trade before an earlier accepted event."""
    engine = MatchingEngine(make_instrument())
    engine.submit(
        make_order("first", side=Side.BUY, sequence_number=1, submitted_at=10, price="99.00")
    )

    with pytest.raises(InvalidIncomingOrderError):
        engine.submit(
            make_order("second", side=Side.BUY, sequence_number=2, submitted_at=9, price="98.00")
        )


def test_submission_sequence_must_increase_with_call_order() -> None:
    """Python call order must agree with explicit deterministic submission order."""
    engine = MatchingEngine(make_instrument())
    engine.submit(make_order("first", side=Side.BUY, sequence_number=10, price="99.00"))

    with pytest.raises(InvalidIncomingOrderError):
        engine.submit(make_order("second", side=Side.BUY, sequence_number=9, price="98.00"))


def test_trade_sequence_continues_across_multiple_takers() -> None:
    """Trade provenance is contiguous over the lifetime of one engine."""
    engine = MatchingEngine(make_instrument())
    seed_ask(engine, "ask-1", sequence_number=1, price="100.00", quantity="1")
    first = engine.submit(
        make_order(
            "market-1",
            side=Side.BUY,
            sequence_number=2,
            quantity="1",
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        )
    )
    seed_ask(engine, "ask-2", sequence_number=3, price="101.00", quantity="1")
    second = engine.submit(
        make_order(
            "market-2",
            side=Side.BUY,
            sequence_number=4,
            quantity="1",
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        )
    )

    assert first.trades[0].sequence_number == 0
    assert second.trades[0].sequence_number == 1
    assert second.trades[0].trade_id == "trade-000000000001"
    assert engine.next_trade_sequence == 2
