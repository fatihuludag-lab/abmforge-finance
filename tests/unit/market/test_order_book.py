"""Unit tests for deterministic resting limit-order-book state."""

from __future__ import annotations

from decimal import Decimal

import pytest

from abmforge_finance import (
    CrossingOrderError,
    DuplicateOrderError,
    DuplicateSequenceNumberError,
    Instrument,
    InvalidBookOrderError,
    InvalidDepthError,
    InvalidPriceError,
    InvalidQuantityError,
    LimitOrderBook,
    Order,
    OrderNotFoundError,
    OrderType,
    OverfillError,
    Side,
    TimeInForce,
)


def make_instrument() -> Instrument:
    """Return the standard test instrument."""
    return Instrument("ACME", Decimal("0.01"), Decimal("1"))


def make_order(
    order_id: str,
    *,
    side: Side = Side.BUY,
    price: str = "100.00",
    quantity: str = "10",
    remaining_quantity: str | None = None,
    submitted_at: int | float = 0,
    sequence_number: int = 1,
    instrument_id: str = "ACME",
    order_type: OrderType = OrderType.LIMIT,
    time_in_force: TimeInForce = TimeInForce.GOOD_TIL_CANCELLED,
) -> Order:
    """Create a valid order with concise overrides."""
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


def populated_book() -> LimitOrderBook:
    """Return a non-crossed two-sided book with multiple levels."""
    book = LimitOrderBook(make_instrument())
    book.add(make_order("b-low", price="99.00", quantity="4", sequence_number=1))
    book.add(
        make_order(
            "b-best-2",
            price="100.00",
            quantity="3",
            submitted_at=2,
            sequence_number=3,
        )
    )
    book.add(
        make_order(
            "b-best-1",
            price="100.00",
            quantity="2",
            submitted_at=1,
            sequence_number=2,
        )
    )
    book.add(
        make_order(
            "a-best",
            side=Side.SELL,
            price="101.00",
            quantity="5",
            sequence_number=4,
        )
    )
    book.add(
        make_order(
            "a-high",
            side=Side.SELL,
            price="102.00",
            quantity="6",
            sequence_number=5,
        )
    )
    return book


def test_empty_book_has_no_quotes_or_imbalance() -> None:
    """An empty book reports missing rather than fabricated quote statistics."""
    book = LimitOrderBook(make_instrument())

    assert len(book) == 0
    assert book.order_count == 0
    assert book.best_bid is None
    assert book.best_ask is None
    assert book.spread is None
    assert book.mid_price is None
    assert book.depth_imbalance() is None
    assert book.best_order(Side.BUY) is None
    assert book.best_order(Side.SELL) is None


def test_constructor_requires_instrument() -> None:
    """The book cannot be created without an exact instrument grid."""
    with pytest.raises(TypeError):
        LimitOrderBook("ACME")  # type: ignore[arg-type]


def test_add_get_contains_and_count() -> None:
    """A valid resting order is indexed by identifier."""
    book = LimitOrderBook(make_instrument())
    order = make_order("b-1")

    book.add(order)

    assert len(book) == 1
    assert "b-1" in book
    assert 1 not in book
    assert book.get("b-1") is order
    assert book.get("missing") is None
    assert book.instrument == make_instrument()


def test_price_priority_is_best_to_worst() -> None:
    """Higher bids and lower asks receive priority independent of insertion order."""
    book = populated_book()

    assert [order.order_id for order in book.orders_by_priority(Side.BUY)] == [
        "b-best-1",
        "b-best-2",
        "b-low",
    ]
    assert [order.order_id for order in book.orders_by_priority(Side.SELL)] == [
        "a-best",
        "a-high",
    ]
    assert book.best_order(Side.BUY).order_id == "b-best-1"  # type: ignore[union-attr]
    assert book.best_order(Side.SELL).order_id == "a-best"  # type: ignore[union-attr]


def test_time_sequence_priority_ignores_add_call_order() -> None:
    """Orders at one price are sorted by explicit time and sequence fields."""
    book = LimitOrderBook(make_instrument())
    later = make_order("later", submitted_at=5, sequence_number=3)
    same_time_later_sequence = make_order("same-2", submitted_at=1, sequence_number=2)
    first = make_order("first", submitted_at=1, sequence_number=1)

    book.add(later)
    book.add(same_time_later_sequence)
    book.add(first)

    assert [order.order_id for order in book.orders_at(Side.BUY, Decimal("100.00"))] == [
        "first",
        "same-2",
        "later",
    ]


def test_duplicate_order_identifier_is_rejected_after_cancellation() -> None:
    """Order identifiers are unique for the lifetime of one book."""
    book = LimitOrderBook(make_instrument())
    book.add(make_order("same", sequence_number=1))
    book.cancel("same")

    with pytest.raises(DuplicateOrderError):
        book.add(make_order("same", sequence_number=2))


def test_duplicate_sequence_number_is_rejected_after_cancellation() -> None:
    """Sequence numbers cannot be reused and silently change audit ordering."""
    book = LimitOrderBook(make_instrument())
    book.add(make_order("first", sequence_number=7))
    book.cancel("first")

    with pytest.raises(DuplicateSequenceNumberError):
        book.add(make_order("second", sequence_number=7))


@pytest.mark.parametrize(
    "order",
    [
        make_order("wrong-instrument", instrument_id="OTHER"),
        make_order(
            "market",
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        ),
        make_order("ioc", time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL),
        make_order("filled", remaining_quantity="0"),
    ],
)
def test_resting_book_rejects_non_resting_orders(order: Order) -> None:
    """Only active GTC limit liquidity for the book instrument may rest."""
    book = LimitOrderBook(make_instrument())

    with pytest.raises(InvalidBookOrderError):
        book.add(order)


def test_resting_book_rejects_non_order_objects() -> None:
    """The mutation API rejects untyped order-like objects."""
    book = LimitOrderBook(make_instrument())

    with pytest.raises(InvalidBookOrderError):
        book.add(object())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("order", "error"),
    [
        (make_order("off-tick", price="100.005"), InvalidPriceError),
        (make_order("off-lot", quantity="1.5"), InvalidQuantityError),
        (
            make_order("off-remaining-lot", quantity="2", remaining_quantity="1.5"),
            InvalidQuantityError,
        ),
    ],
)
def test_add_validates_instrument_price_and_quantity_grids(
    order: Order, error: type[Exception]
) -> None:
    """Book entry validates both the original and active grids."""
    book = LimitOrderBook(make_instrument())

    with pytest.raises(error):
        book.add(order)


def test_crossing_limit_order_is_reserved_for_matching_engine() -> None:
    """The resting state never accepts marketable or locked liquidity."""
    book = LimitOrderBook(make_instrument())
    book.add(make_order("ask", side=Side.SELL, price="101.00", sequence_number=1))

    with pytest.raises(CrossingOrderError):
        book.add(make_order("cross", price="101.00", sequence_number=2))


def test_would_cross_supports_limit_and_market_orders() -> None:
    """Marketability can be queried without mutating resting state."""
    book = LimitOrderBook(make_instrument())
    book.add(make_order("ask", side=Side.SELL, price="101.00", sequence_number=1))

    assert not book.would_cross(make_order("below", price="100.99", sequence_number=2))
    assert book.would_cross(make_order("at", price="101.00", sequence_number=3))
    assert book.would_cross(
        make_order(
            "market",
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
            sequence_number=4,
        )
    )
    assert not LimitOrderBook(make_instrument()).would_cross(
        make_order(
            "empty-market",
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
        )
    )


def test_would_cross_rejects_wrong_instrument_and_non_order() -> None:
    """Marketability queries preserve the book's typed instrument boundary."""
    book = LimitOrderBook(make_instrument())

    with pytest.raises(InvalidBookOrderError):
        book.would_cross(make_order("other", instrument_id="OTHER"))
    with pytest.raises(InvalidBookOrderError):
        book.would_cross(object())  # type: ignore[arg-type]


def test_best_quotes_spread_and_mid_price() -> None:
    """Top-of-book statistics are exact Decimal values."""
    book = populated_book()

    assert book.best_bid == Decimal("100.00")
    assert book.best_ask == Decimal("101.00")
    assert book.spread == Decimal("1.00")
    assert book.mid_price == Decimal("100.50")


def test_one_sided_book_has_no_spread_or_mid_price() -> None:
    """Two-sided statistics stay missing when only one quote side exists."""
    book = LimitOrderBook(make_instrument())
    book.add(make_order("bid"))

    assert book.best_bid == Decimal("100.00")
    assert book.best_ask is None
    assert book.spread is None
    assert book.mid_price is None


def test_cancel_removes_order_and_empty_price_level() -> None:
    """Cancellation cleans all active indexes while retaining historical identity."""
    book = LimitOrderBook(make_instrument())
    order = make_order("bid")
    book.add(order)

    cancelled = book.cancel("bid")

    assert cancelled is order
    assert len(book) == 0
    assert book.best_bid is None
    assert book.depth(Side.BUY) == ()
    book.validate_invariants()


@pytest.mark.parametrize("order_id", ["missing", "", " "])
def test_cancel_rejects_missing_order(order_id: str) -> None:
    """Cancellation never silently ignores an unknown identifier."""
    with pytest.raises(OrderNotFoundError):
        LimitOrderBook(make_instrument()).cancel(order_id)


def test_partial_fill_preserves_price_time_priority() -> None:
    """Reducing remaining quantity does not move an order behind its peers."""
    book = LimitOrderBook(make_instrument())
    book.add(make_order("first", quantity="10", sequence_number=1))
    book.add(make_order("second", quantity="10", sequence_number=2))

    updated = book.apply_fill("first", Decimal("6"))

    assert updated.remaining_quantity == Decimal("4")
    assert book.get("first") == updated
    assert [order.order_id for order in book.orders_at(Side.BUY, Decimal("100.00"))] == [
        "first",
        "second",
    ]
    book.validate_invariants()


def test_full_fill_returns_filled_order_and_removes_it() -> None:
    """A completed order cannot remain visible or cancellable."""
    book = LimitOrderBook(make_instrument())
    book.add(make_order("only", quantity="3"))

    updated = book.apply_fill("only", Decimal("3"))

    assert updated.is_filled
    assert "only" not in book
    assert book.best_bid is None
    with pytest.raises(OrderNotFoundError):
        book.cancel("only")


@pytest.mark.parametrize("quantity", [Decimal("0"), Decimal("-1"), Decimal("0.5")])
def test_fill_requires_positive_lot_aligned_quantity(quantity: Decimal) -> None:
    """Fill mutation uses the same exact lot grid as incoming orders."""
    book = LimitOrderBook(make_instrument())
    book.add(make_order("bid", quantity="2"))

    with pytest.raises(InvalidQuantityError):
        book.apply_fill("bid", quantity)


def test_fill_rejects_non_decimal_and_missing_order() -> None:
    """Fill operations are typed and target active orders only."""
    book = LimitOrderBook(make_instrument())
    book.add(make_order("bid"))

    with pytest.raises(InvalidQuantityError):
        book.apply_fill("bid", 1)  # type: ignore[arg-type]
    with pytest.raises(OrderNotFoundError):
        book.apply_fill("missing", Decimal("1"))


def test_overfill_is_rejected_without_mutation() -> None:
    """Executed quantity cannot make remaining quantity negative."""
    book = LimitOrderBook(make_instrument())
    original = make_order("bid", quantity="2")
    book.add(original)

    with pytest.raises(OverfillError):
        book.apply_fill("bid", Decimal("3"))

    assert book.get("bid") is original


def test_depth_aggregates_levels_in_best_to_worst_order() -> None:
    """Depth sums remaining quantity and preserves deterministic level ordering."""
    book = populated_book()

    bids = book.depth(Side.BUY)
    asks = book.depth(Side.SELL)

    assert [(level.price, level.total_quantity, level.order_count) for level in bids] == [
        (Decimal("100.00"), Decimal("5"), 2),
        (Decimal("99.00"), Decimal("4"), 1),
    ]
    assert [(level.price, level.total_quantity, level.order_count) for level in asks] == [
        (Decimal("101.00"), Decimal("5"), 1),
        (Decimal("102.00"), Decimal("6"), 1),
    ]
    assert bids[0].price_ticks == 10000
    assert bids[0].side is Side.BUY


def test_depth_limit_and_orders_at_missing_level() -> None:
    """Depth can be bounded and missing levels return an empty immutable view."""
    book = populated_book()

    assert len(book.depth(Side.BUY, levels=1)) == 1
    assert book.orders_at(Side.BUY, Decimal("98.00")) == ()


@pytest.mark.parametrize("levels", [0, -1, True, 1.5])
def test_depth_rejects_invalid_level_limits(levels: object) -> None:
    """Snapshot limits must be positive integers rather than truthy values."""
    book = LimitOrderBook(make_instrument())

    with pytest.raises(InvalidDepthError):
        book.depth(Side.BUY, levels=levels)  # type: ignore[arg-type]
    with pytest.raises(InvalidDepthError):
        book.snapshot(levels=levels)  # type: ignore[arg-type]


def test_depth_imbalance_distinguishes_empty_balanced_and_one_sided_books() -> None:
    """Imbalance has explicit missing, balanced, and extreme states."""
    empty = LimitOrderBook(make_instrument())
    bid_only = LimitOrderBook(make_instrument())
    ask_only = LimitOrderBook(make_instrument())
    balanced = LimitOrderBook(make_instrument())

    bid_only.add(make_order("bid", quantity="2"))
    ask_only.add(make_order("ask", side=Side.SELL, price="101.00", quantity="2"))
    balanced.add(make_order("balanced-bid", quantity="2", sequence_number=1))
    balanced.add(
        make_order(
            "balanced-ask",
            side=Side.SELL,
            price="101.00",
            quantity="2",
            sequence_number=2,
        )
    )

    assert empty.depth_imbalance() is None
    assert bid_only.depth_imbalance() == Decimal("1")
    assert ask_only.depth_imbalance() == Decimal("-1")
    assert balanced.depth_imbalance() == Decimal("0")


def test_depth_imbalance_respects_symmetric_level_limit() -> None:
    """A level limit is applied independently to each side before aggregation."""
    book = populated_book()

    assert book.depth_imbalance(levels=1) == Decimal("0")
    assert book.depth_imbalance() == Decimal("-2") / Decimal("20")


def test_snapshot_is_immutable_and_self_consistent() -> None:
    """Snapshot fields agree with direct book queries."""
    book = populated_book()

    snapshot = book.snapshot(levels=1)

    assert snapshot.instrument_id == "ACME"
    assert snapshot.bids == book.depth(Side.BUY, levels=1)
    assert snapshot.asks == book.depth(Side.SELL, levels=1)
    assert snapshot.best_bid == book.best_bid
    assert snapshot.best_ask == book.best_ask
    assert snapshot.spread == book.spread
    assert snapshot.mid_price == book.mid_price
    assert snapshot.imbalance == Decimal("0")
    assert snapshot.order_count == 5


def test_invalid_side_is_rejected_by_query_methods() -> None:
    """Runtime side checks avoid accidental string-keyed state access."""
    book = LimitOrderBook(make_instrument())

    with pytest.raises(InvalidBookOrderError):
        book.best_order("buy")  # type: ignore[arg-type]
    with pytest.raises(InvalidBookOrderError):
        book.orders_by_priority("buy")  # type: ignore[arg-type]
    with pytest.raises(InvalidBookOrderError):
        book.orders_at("buy", Decimal("100"))  # type: ignore[arg-type]
    with pytest.raises(InvalidBookOrderError):
        book.depth("buy")  # type: ignore[arg-type]


def test_public_invariant_validation_accepts_valid_state() -> None:
    """Diagnostic invariant validation succeeds through add, fill, and cancel paths."""
    book = populated_book()
    book.apply_fill("b-best-1", Decimal("1"))
    book.cancel("a-high")

    book.validate_invariants()
