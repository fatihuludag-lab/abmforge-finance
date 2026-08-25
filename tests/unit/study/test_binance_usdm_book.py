"""Tests for deterministic Binance USD-M local-book synchronization."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

import pytest

from abmforge_finance.study.binance_usdm_book import (
    BinanceUsdMBookSynchronizationError,
    BinanceUsdMLocalBook,
)
from abmforge_finance.study.binance_usdm_events import (
    BinanceUsdMBookLevel,
    BinanceUsdMDepthSnapshot,
    BinanceUsdMDepthUpdateEvent,
)


def _snapshot() -> BinanceUsdMDepthSnapshot:
    return BinanceUsdMDepthSnapshot(
        symbol="BTCUSDT",
        last_update_id=100,
        event_time_ms=1_000,
        transaction_time_ms=999,
        bids=(
            BinanceUsdMBookLevel(
                Decimal("100"),
                Decimal("5"),
            ),
            BinanceUsdMBookLevel(
                Decimal("99"),
                Decimal("4"),
            ),
        ),
        asks=(
            BinanceUsdMBookLevel(
                Decimal("101"),
                Decimal("6"),
            ),
            BinanceUsdMBookLevel(
                Decimal("102"),
                Decimal("7"),
            ),
        ),
    )


def _event(
    *,
    first: int,
    final: int,
    previous: int,
    bids: tuple[BinanceUsdMBookLevel, ...] = (),
    asks: tuple[BinanceUsdMBookLevel, ...] = (),
) -> BinanceUsdMDepthUpdateEvent:
    return BinanceUsdMDepthUpdateEvent(
        event_time_ms=2_000 + final,
        transaction_time_ms=1_900 + final,
        symbol="BTCUSDT",
        pair="BTCUSDT",
        symbol_type=1,
        first_update_id=first,
        final_update_id=final,
        previous_final_update_id=previous,
        bid_updates=bids,
        ask_updates=asks,
    )


def _bridge() -> BinanceUsdMDepthUpdateEvent:
    return _event(
        first=99,
        final=102,
        previous=98,
        bids=(
            BinanceUsdMBookLevel(
                Decimal("100"),
                Decimal("3"),
            ),
            BinanceUsdMBookLevel(
                Decimal("98"),
                Decimal("2"),
            ),
        ),
        asks=(
            BinanceUsdMBookLevel(
                Decimal("101"),
                Decimal("0"),
            ),
            BinanceUsdMBookLevel(
                Decimal("103"),
                Decimal("1"),
            ),
        ),
    )


def test_synchronization_applies_snapshot_bridge() -> None:
    book = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (_bridge(),),
    )

    state = book.state()

    assert book.is_synchronized is True
    assert state.last_update_id == 102
    assert state.best_bid == Decimal("100")
    assert state.best_ask == Decimal("102")
    assert state.midpoint == Decimal("101")

    assert state.bid_depth == Decimal("9")
    assert state.ask_depth == Decimal("8")
    assert state.thin_side_depth == Decimal("8")


def test_synchronization_discards_pre_snapshot_events() -> None:
    stale = _event(
        first=90,
        final=95,
        previous=89,
    )

    book = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (stale, _bridge()),
    )

    assert book.last_update_id == 102


def test_absolute_quantity_overwrites_existing_level() -> None:
    book = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (_bridge(),),
    )

    event = _event(
        first=103,
        final=105,
        previous=102,
        bids=(
            BinanceUsdMBookLevel(
                Decimal("100"),
                Decimal("1.25"),
            ),
        ),
    )

    book.apply(event)

    state = book.state()

    level = next(level for level in state.bids if level.price == Decimal("100"))

    assert level.quantity == Decimal("1.25")
    assert level.quantity != Decimal("4.25")


def test_zero_quantity_removes_existing_level() -> None:
    book = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (_bridge(),),
    )

    book.apply(
        _event(
            first=103,
            final=104,
            previous=102,
            bids=(
                BinanceUsdMBookLevel(
                    Decimal("100"),
                    Decimal("0"),
                ),
            ),
        )
    )

    assert all(level.price != Decimal("100") for level in book.state().bids)


def test_removing_unknown_level_is_normal() -> None:
    book = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (_bridge(),),
    )

    book.apply(
        _event(
            first=103,
            final=104,
            previous=102,
            bids=(
                BinanceUsdMBookLevel(
                    Decimal("50"),
                    Decimal("0"),
                ),
            ),
        )
    )

    assert book.last_update_id == 104


def test_subsequent_event_requires_pu_equal_previous_u() -> None:
    book = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (_bridge(),),
    )

    broken = _event(
        first=103,
        final=105,
        previous=101,
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="pu must equal previous u",
    ):
        book.apply(broken)


def test_update_ids_must_advance() -> None:
    book = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (_bridge(),),
    )

    non_advancing = _event(
        first=102,
        final=102,
        previous=102,
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="advance monotonically",
    ):
        book.apply(non_advancing)


def test_synchronization_requires_bridge_event() -> None:
    stale = _event(
        first=90,
        final=95,
        previous=89,
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="does not contain a snapshot bridge",
    ):
        BinanceUsdMLocalBook.synchronize(
            _snapshot(),
            (stale,),
        )


def test_first_retained_event_must_cover_snapshot_id() -> None:
    missed = _event(
        first=101,
        final=103,
        previous=100,
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="does not bridge",
    ):
        BinanceUsdMLocalBook.synchronize(
            _snapshot(),
            (missed,),
        )


def test_synchronization_does_not_reorder_buffer() -> None:
    later = _event(
        first=103,
        final=104,
        previous=102,
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="does not bridge",
    ):
        BinanceUsdMLocalBook.synchronize(
            _snapshot(),
            (later, _bridge()),
        )


def test_book_rejects_crossed_state_after_update() -> None:
    book = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (_bridge(),),
    )

    crossed = _event(
        first=103,
        final=104,
        previous=102,
        bids=(
            BinanceUsdMBookLevel(
                Decimal("103"),
                Decimal("1"),
            ),
        ),
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="crossed or locked",
    ):
        book.apply(crossed)


def test_book_rejects_loss_of_all_bid_levels() -> None:
    snapshot = BinanceUsdMDepthSnapshot(
        symbol="BTCUSDT",
        last_update_id=100,
        event_time_ms=1000,
        transaction_time_ms=999,
        bids=(
            BinanceUsdMBookLevel(
                Decimal("100"),
                Decimal("1"),
            ),
        ),
        asks=(
            BinanceUsdMBookLevel(
                Decimal("101"),
                Decimal("1"),
            ),
        ),
    )

    bridge = _event(
        first=100,
        final=101,
        previous=99,
        bids=(
            BinanceUsdMBookLevel(
                Decimal("100"),
                Decimal("0"),
            ),
        ),
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="lost all bid levels",
    ):
        BinanceUsdMLocalBook.synchronize(
            snapshot,
            (bridge,),
        )


def test_event_identity_is_checked_during_apply() -> None:
    book = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (_bridge(),),
    )

    wrong_symbol = replace(
        _event(
            first=103,
            final=104,
            previous=102,
        ),
        symbol="ETHUSDT",
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="symbol does not match",
    ):
        book.apply(wrong_symbol)


def test_buffer_must_be_tuple() -> None:
    with pytest.raises(
        TypeError,
        match="buffered_events must be a tuple",
    ):
        BinanceUsdMLocalBook.synchronize(
            _snapshot(),
            [_bridge()],  # type: ignore[arg-type]
        )


def test_local_book_state_is_immutable() -> None:
    state = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (_bridge(),),
    ).state()

    with pytest.raises(FrozenInstanceError):
        state.last_update_id = 999  # type: ignore[misc]
