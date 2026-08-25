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


def test_local_book_state_integrity_edges_v3() -> None:
    from decimal import Decimal

    from abmforge_finance.study.binance_usdm_book import (
        BinanceUsdMBookSynchronizationError,
        BinanceUsdMLocalBookState,
    )
    from abmforge_finance.study.binance_usdm_events import (
        BinanceUsdMBookLevel,
    )

    bid_100 = BinanceUsdMBookLevel(
        Decimal("100"),
        Decimal("1"),
    )
    bid_99 = BinanceUsdMBookLevel(
        Decimal("99"),
        Decimal("1"),
    )
    ask_101 = BinanceUsdMBookLevel(
        Decimal("101"),
        Decimal("1"),
    )
    ask_102 = BinanceUsdMBookLevel(
        Decimal("102"),
        Decimal("1"),
    )

    def make_state(
        *,
        bids: tuple[BinanceUsdMBookLevel, ...],
        asks: tuple[BinanceUsdMBookLevel, ...],
    ) -> BinanceUsdMLocalBookState:
        return BinanceUsdMLocalBookState(
            symbol="BTCUSDT",
            last_update_id=10,
            event_time_ms=1000,
            transaction_time_ms=999,
            bids=bids,
            asks=asks,
        )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="at least one bid",
    ):
        make_state(
            bids=(),
            asks=(ask_101,),
        )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="at least one ask",
    ):
        make_state(
            bids=(bid_100,),
            asks=(),
        )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="strictly descending",
    ):
        make_state(
            bids=(bid_99, bid_100),
            asks=(ask_101,),
        )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="strictly ascending",
    ):
        make_state(
            bids=(bid_100,),
            asks=(ask_102, ask_101),
        )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="positive spread",
    ):
        make_state(
            bids=(ask_101,),
            asks=(ask_101,),
        )


def test_unsynchronized_local_book_api_is_guarded_v3() -> None:
    from abmforge_finance.study.binance_usdm_book import (
        BinanceUsdMBookSynchronizationError,
        BinanceUsdMLocalBook,
    )
    from abmforge_finance.study.binance_usdm_contract import (
        binance_usdm_empirical_contract,
    )

    book = BinanceUsdMLocalBook(contract=binance_usdm_empirical_contract())

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="not synchronized",
    ):
        _ = book.last_update_id

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="not synchronized",
    ):
        book.state()

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="not synchronized",
    ):
        book.apply(_bridge())


def test_synchronization_input_type_and_identity_guards_v3() -> None:
    from dataclasses import replace
    from typing import cast

    from abmforge_finance.study.binance_usdm_book import (
        BinanceUsdMBookSynchronizationError,
        BinanceUsdMLocalBook,
    )
    from abmforge_finance.study.binance_usdm_events import (
        BinanceUsdMDepthSnapshot,
        BinanceUsdMDepthUpdateEvent,
    )

    with pytest.raises(
        TypeError,
        match="snapshot",
    ):
        BinanceUsdMLocalBook.synchronize(
            cast(
                BinanceUsdMDepthSnapshot,
                object(),
            ),
            (),
        )

    with pytest.raises(
        TypeError,
        match=r"buffered_events\[0\]",
    ):
        BinanceUsdMLocalBook.synchronize(
            _snapshot(),
            (
                cast(
                    BinanceUsdMDepthUpdateEvent,
                    object(),
                ),
            ),
        )

    wrong_symbol_snapshot = replace(
        _snapshot(),
        symbol="ETHUSDT",
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="snapshot symbol",
    ):
        BinanceUsdMLocalBook.synchronize(
            wrong_symbol_snapshot,
            (_bridge(),),
        )


def test_snapshot_duplicate_price_levels_are_rejected_v3() -> None:
    from dataclasses import replace

    from abmforge_finance.study.binance_usdm_book import (
        BinanceUsdMBookSynchronizationError,
        BinanceUsdMLocalBook,
    )

    snapshot = _snapshot()

    duplicate_bids = replace(
        snapshot,
        bids=(
            snapshot.bids[0],
            snapshot.bids[0],
        ),
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="duplicate bid",
    ):
        BinanceUsdMLocalBook.synchronize(
            duplicate_bids,
            (_bridge(),),
        )

    duplicate_asks = replace(
        snapshot,
        asks=(
            snapshot.asks[0],
            snapshot.asks[0],
        ),
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="duplicate ask",
    ):
        BinanceUsdMLocalBook.synchronize(
            duplicate_asks,
            (_bridge(),),
        )


def test_applied_event_pair_and_symbol_type_are_guarded_v3() -> None:
    from dataclasses import replace

    from abmforge_finance.study.binance_usdm_book import (
        BinanceUsdMBookSynchronizationError,
        BinanceUsdMLocalBook,
    )

    book = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (_bridge(),),
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="pair does not match",
    ):
        book.apply(
            replace(
                _bridge(),
                pair="ETHUSDT",
            )
        )

    # symbol_type=2 cannot normally be constructed because the
    # event-level validator correctly rejects it first. Corrupt one
    # otherwise valid event deliberately to exercise the book layer's
    # defense-in-depth identity guard.
    invalid_symbol_type_event = _bridge()
    object.__setattr__(
        invalid_symbol_type_event,
        "symbol_type",
        2,
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="symbol type",
    ):
        book.apply(invalid_symbol_type_event)


def test_book_remaining_defense_paths_v4() -> None:
    from dataclasses import replace
    from decimal import Decimal
    from typing import cast

    from abmforge_finance.study.binance_usdm_book import (
        BinanceUsdMBookSynchronizationError,
        BinanceUsdMLocalBook,
    )
    from abmforge_finance.study.binance_usdm_events import (
        BinanceUsdMBookLevel,
        BinanceUsdMDepthUpdateEvent,
    )

    first = _bridge()

    second = replace(
        first,
        event_time_ms=first.event_time_ms + 1,
        transaction_time_ms=(first.transaction_time_ms + 1),
        first_update_id=(first.final_update_id + 1),
        final_update_id=(first.final_update_id + 2),
        previous_final_update_id=(first.final_update_id),
    )

    book = BinanceUsdMLocalBook.synchronize(
        _snapshot(),
        (
            first,
            second,
        ),
    )

    assert book.last_update_id == second.final_update_id

    with pytest.raises(
        TypeError,
        match="event must be",
    ):
        book.apply(
            cast(
                BinanceUsdMDepthUpdateEvent,
                object(),
            )
        )

    state = book.state()

    removals = tuple(
        BinanceUsdMBookLevel(
            level.price,
            Decimal("0"),
        )
        for level in state.asks
    )

    event = replace(
        first,
        event_time_ms=first.event_time_ms + 10,
        transaction_time_ms=(first.transaction_time_ms + 10),
        first_update_id=(book.last_update_id + 1),
        final_update_id=(book.last_update_id + 1),
        previous_final_update_id=(book.last_update_id),
        bid_updates=(),
        ask_updates=removals,
    )

    with pytest.raises(
        BinanceUsdMBookSynchronizationError,
        match="lost all ask levels",
    ):
        book.apply(event)
