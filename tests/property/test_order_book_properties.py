"""Property-based tests for order-book ordering and accounting invariants."""

from __future__ import annotations

from decimal import Decimal
from random import Random

from hypothesis import given
from hypothesis import strategies as st

from abmforge_finance import Instrument, LimitOrderBook, Order, OrderType, Side, TimeInForce

_ORDER_SPECS = st.lists(
    st.tuples(
        st.integers(min_value=0, max_value=10_000),
        st.integers(min_value=9_900, max_value=10_000),
        st.integers(min_value=0, max_value=100),
        st.integers(min_value=1, max_value=100),
    ),
    min_size=1,
    max_size=20,
    unique_by=lambda spec: spec[0],
)


def build_orders(specs: list[tuple[int, int, int, int]], *, side: Side = Side.BUY) -> list[Order]:
    """Build unique one-sided orders from generated exact-grid fields."""
    return [
        Order(
            order_id=f"order-{index}",
            agent_id=f"agent-{index}",
            instrument_id="ACME",
            side=side,
            order_type=OrderType.LIMIT,
            quantity=Decimal(quantity),
            remaining_quantity=Decimal(quantity),
            price=Decimal(price_ticks) * Decimal("0.01"),
            submitted_at=submitted_at,
            sequence_number=sequence_number,
            time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
        )
        for index, (sequence_number, price_ticks, submitted_at, quantity) in enumerate(specs)
    ]


@given(
    _ORDER_SPECS,
    st.sampled_from([Side.BUY, Side.SELL]),
    st.randoms(use_true_random=False),
)
def test_insertion_permutation_does_not_change_priority(
    specs: list[tuple[int, int, int, int]], side: Side, random_source: Random
) -> None:
    """Explicit price-time fields make state independent of submission call order."""
    instrument = Instrument("ACME", Decimal("0.01"), Decimal("1"))
    original = LimitOrderBook(instrument)
    permuted = LimitOrderBook(instrument)
    orders = build_orders(specs, side=side)

    for order in orders:
        original.add(order)
    shuffled = list(orders)
    random_source.shuffle(shuffled)
    for order in shuffled:
        permuted.add(order)

    assert original.orders_by_priority(side) == permuted.orders_by_priority(side)
    assert original.snapshot() == permuted.snapshot()
    original.validate_invariants()
    permuted.validate_invariants()


@given(
    quantity=st.integers(min_value=1, max_value=1_000),
    fill_source=st.integers(min_value=1, max_value=10_000),
)
def test_fill_never_produces_negative_remaining_quantity(quantity: int, fill_source: int) -> None:
    """Accepted fills preserve non-negative active remaining quantity."""
    fill = 1 + ((fill_source - 1) % quantity)
    instrument = Instrument("ACME", Decimal("0.01"), Decimal("1"))
    book = LimitOrderBook(instrument)
    order = Order(
        order_id="order",
        agent_id="agent",
        instrument_id="ACME",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal(quantity),
        remaining_quantity=Decimal(quantity),
        price=Decimal("100.00"),
        submitted_at=0,
        sequence_number=0,
        time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
    )
    book.add(order)

    updated = book.apply_fill("order", Decimal(fill))

    assert updated.remaining_quantity >= Decimal("0")
    assert updated.remaining_quantity == Decimal(quantity - fill)
    book.validate_invariants()


@given(
    side=st.sampled_from([Side.BUY, Side.SELL]),
    quantity=st.integers(min_value=1, max_value=1_000),
    remove_with_fill=st.booleans(),
)
def test_cancel_or_full_fill_removes_all_active_book_state(
    side: Side, quantity: int, remove_with_fill: bool
) -> None:
    """Terminal order removal leaves no orphaned price level or active index."""
    instrument = Instrument("ACME", Decimal("0.01"), Decimal("1"))
    book = LimitOrderBook(instrument)
    order = Order(
        order_id="order",
        agent_id="agent",
        instrument_id="ACME",
        side=side,
        order_type=OrderType.LIMIT,
        quantity=Decimal(quantity),
        remaining_quantity=Decimal(quantity),
        price=Decimal("100.00"),
        submitted_at=0,
        sequence_number=0,
        time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
    )
    book.add(order)

    if remove_with_fill:
        book.apply_fill(order.order_id, order.remaining_quantity)
    else:
        book.cancel(order.order_id)

    assert book.order_count == 0
    assert book.get(order.order_id) is None
    assert book.depth(side) == ()
    assert book.best_order(side) is None
    book.validate_invariants()


@given(_ORDER_SPECS, st.sampled_from([Side.BUY, Side.SELL]))
def test_aggregated_depth_equals_active_remaining_quantity(
    specs: list[tuple[int, int, int, int]], side: Side
) -> None:
    """Aggregated depth is exactly the sum of active immutable order quantities."""
    instrument = Instrument("ACME", Decimal("0.01"), Decimal("1"))
    book = LimitOrderBook(instrument)
    orders = build_orders(specs, side=side)
    for order in orders:
        book.add(order)

    for index, order in enumerate(orders):
        if index % 2 == 0 and order.remaining_quantity > Decimal("1"):
            book.apply_fill(order.order_id, Decimal("1"))

    active_total = sum(
        (order.remaining_quantity for order in book.orders_by_priority(side)),
        start=Decimal("0"),
    )
    depth_total = sum(
        (level.total_quantity for level in book.depth(side)),
        start=Decimal("0"),
    )

    assert depth_total == active_total
    book.validate_invariants()
