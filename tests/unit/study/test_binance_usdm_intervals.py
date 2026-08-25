"""Tests for deterministic Binance USD-M one-second aggregation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from abmforge_finance.study.binance_usdm_book import (
    BinanceUsdMLocalBookState,
)
from abmforge_finance.study.binance_usdm_events import (
    BinanceUsdMAggTradeEvent,
    BinanceUsdMBookLevel,
)
from abmforge_finance.study.binance_usdm_intervals import (
    BinanceUsdMIntervalAggregationError,
    aggregate_binance_usdm_intervals,
)

_START = 10_000


def _state(
    *,
    transaction_time_ms: int,
    update_id: int,
    bid: str = "100",
    ask: str = "102",
    bid_quantity: str = "5",
    ask_quantity: str = "7",
) -> BinanceUsdMLocalBookState:
    return BinanceUsdMLocalBookState(
        symbol="BTCUSDT",
        last_update_id=update_id,
        event_time_ms=transaction_time_ms + 2,
        transaction_time_ms=transaction_time_ms,
        bids=(
            BinanceUsdMBookLevel(
                Decimal(bid),
                Decimal(bid_quantity),
            ),
        ),
        asks=(
            BinanceUsdMBookLevel(
                Decimal(ask),
                Decimal(ask_quantity),
            ),
        ),
    )


def _trade(
    *,
    trade_time_ms: int,
    trade_id: int,
    normal_quantity: str,
    buyer_is_maker: bool,
    quantity: str | None = None,
) -> BinanceUsdMAggTradeEvent:
    total_quantity = normal_quantity if quantity is None else quantity

    return BinanceUsdMAggTradeEvent(
        event_time_ms=trade_time_ms + 3,
        trade_time_ms=trade_time_ms,
        symbol="BTCUSDT",
        symbol_type=1,
        aggregate_trade_id=trade_id,
        price=Decimal("101"),
        quantity=Decimal(total_quantity),
        normal_quantity=Decimal(normal_quantity),
        first_trade_id=trade_id * 10,
        last_trade_id=trade_id * 10,
        buyer_is_maker=buyer_is_maker,
    )


def test_interval_uses_last_synchronized_book_state() -> None:
    intervals = aggregate_binance_usdm_intervals(
        start_timestamp_ms=_START,
        interval_count=1,
        book_states=(
            _state(
                transaction_time_ms=_START + 100,
                update_id=1,
                bid="100",
                ask="102",
            ),
            _state(
                transaction_time_ms=_START + 900,
                update_id=2,
                bid="102",
                ask="104",
                bid_quantity="8",
                ask_quantity="6",
            ),
        ),
        aggregate_trades=(),
    )

    interval = intervals[0]

    assert interval.mid_price == pytest.approx(103.0)
    assert interval.thin_side_depth == pytest.approx(6.0)


def test_no_trade_interval_has_measured_zero_flow() -> None:
    intervals = aggregate_binance_usdm_intervals(
        start_timestamp_ms=_START,
        interval_count=1,
        book_states=(
            _state(
                transaction_time_ms=_START + 500,
                update_id=1,
            ),
        ),
        aggregate_trades=(),
    )

    assert intervals[0].aggressor_flow == 0.0


def test_flow_uses_normal_quantity_and_aggressor_direction() -> None:
    intervals = aggregate_binance_usdm_intervals(
        start_timestamp_ms=_START,
        interval_count=1,
        book_states=(
            _state(
                transaction_time_ms=_START + 900,
                update_id=1,
            ),
        ),
        aggregate_trades=(
            _trade(
                trade_time_ms=_START + 100,
                trade_id=1,
                normal_quantity="3",
                quantity="30",
                buyer_is_maker=False,
            ),
            _trade(
                trade_time_ms=_START + 200,
                trade_id=2,
                normal_quantity="1",
                quantity="20",
                buyer_is_maker=True,
            ),
        ),
    )

    # (3 - 1) / (3 + 1) = 0.5.
    assert intervals[0].aggressor_flow == pytest.approx(0.5)


def test_zero_normal_quantity_does_not_change_flow() -> None:
    intervals = aggregate_binance_usdm_intervals(
        start_timestamp_ms=_START,
        interval_count=1,
        book_states=(
            _state(
                transaction_time_ms=_START + 900,
                update_id=1,
            ),
        ),
        aggregate_trades=(
            _trade(
                trade_time_ms=_START + 100,
                trade_id=1,
                normal_quantity="0",
                quantity="10",
                buyer_is_maker=False,
            ),
        ),
    )

    assert intervals[0].aggressor_flow == 0.0


def test_trade_time_not_event_time_determines_interval() -> None:
    trade = _trade(
        trade_time_ms=_START + 999,
        trade_id=1,
        normal_quantity="2",
        buyer_is_maker=False,
    )

    trade = BinanceUsdMAggTradeEvent(
        event_time_ms=_START + 1_050,
        trade_time_ms=trade.trade_time_ms,
        symbol=trade.symbol,
        symbol_type=trade.symbol_type,
        aggregate_trade_id=trade.aggregate_trade_id,
        price=trade.price,
        quantity=trade.quantity,
        normal_quantity=trade.normal_quantity,
        first_trade_id=trade.first_trade_id,
        last_trade_id=trade.last_trade_id,
        buyer_is_maker=trade.buyer_is_maker,
    )

    intervals = aggregate_binance_usdm_intervals(
        start_timestamp_ms=_START,
        interval_count=2,
        book_states=(
            _state(
                transaction_time_ms=_START + 900,
                update_id=1,
            ),
            _state(
                transaction_time_ms=_START + 1_900,
                update_id=2,
            ),
        ),
        aggregate_trades=(trade,),
    )

    assert intervals[0].aggressor_flow == 1.0
    assert intervals[1].aggressor_flow == 0.0


def test_book_transaction_time_not_event_time_determines_interval() -> None:
    first = _state(
        transaction_time_ms=_START + 999,
        update_id=1,
        bid="100",
        ask="102",
    )

    first = BinanceUsdMLocalBookState(
        symbol=first.symbol,
        last_update_id=first.last_update_id,
        event_time_ms=_START + 1_050,
        transaction_time_ms=first.transaction_time_ms,
        bids=first.bids,
        asks=first.asks,
    )

    intervals = aggregate_binance_usdm_intervals(
        start_timestamp_ms=_START,
        interval_count=2,
        book_states=(
            first,
            _state(
                transaction_time_ms=_START + 1_900,
                update_id=2,
                bid="104",
                ask="106",
            ),
        ),
        aggregate_trades=(),
    )

    assert intervals[0].mid_price == pytest.approx(101.0)
    assert intervals[1].mid_price == pytest.approx(105.0)


def test_boundary_observation_belongs_to_next_interval() -> None:
    intervals = aggregate_binance_usdm_intervals(
        start_timestamp_ms=_START,
        interval_count=2,
        book_states=(
            _state(
                transaction_time_ms=_START + 900,
                update_id=1,
                bid="100",
                ask="102",
            ),
            _state(
                transaction_time_ms=_START + 1_000,
                update_id=2,
                bid="104",
                ask="106",
            ),
        ),
        aggregate_trades=(
            _trade(
                trade_time_ms=_START + 1_000,
                trade_id=1,
                normal_quantity="2",
                buyer_is_maker=False,
            ),
        ),
    )

    assert intervals[0].mid_price == pytest.approx(101.0)
    assert intervals[0].aggressor_flow == 0.0

    assert intervals[1].mid_price == pytest.approx(105.0)
    assert intervals[1].aggressor_flow == 1.0


def test_interval_timestamps_are_utc_aligned_nanoseconds() -> None:
    intervals = aggregate_binance_usdm_intervals(
        start_timestamp_ms=_START,
        interval_count=2,
        book_states=(
            _state(
                transaction_time_ms=_START + 500,
                update_id=1,
            ),
            _state(
                transaction_time_ms=_START + 1_500,
                update_id=2,
            ),
        ),
        aggregate_trades=(),
    )

    assert intervals[0].start_timestamp_ns == 10_000_000_000
    assert intervals[0].end_timestamp_ns == 11_000_000_000

    assert intervals[1].start_timestamp_ns == 11_000_000_000
    assert intervals[1].end_timestamp_ns == 12_000_000_000


def test_synchronized_book_state_persists_across_quiet_interval() -> None:
    intervals = aggregate_binance_usdm_intervals(
        start_timestamp_ms=_START,
        interval_count=2,
        book_states=(
            _state(
                transaction_time_ms=_START + 500,
                update_id=1,
                bid="100",
                ask="102",
            ),
        ),
        aggregate_trades=(),
    )

    assert intervals[0].mid_price == pytest.approx(101.0)
    assert intervals[1].mid_price == pytest.approx(101.0)


def test_first_interval_requires_state_before_its_close() -> None:
    with pytest.raises(
        BinanceUsdMIntervalAggregationError,
        match="before interval close",
    ):
        aggregate_binance_usdm_intervals(
            start_timestamp_ms=_START,
            interval_count=2,
            book_states=(
                _state(
                    transaction_time_ms=_START + 1_500,
                    update_id=1,
                ),
            ),
            aggregate_trades=(),
        )


def test_start_must_be_utc_second_aligned() -> None:
    with pytest.raises(
        BinanceUsdMIntervalAggregationError,
        match="UTC-second boundary",
    ):
        aggregate_binance_usdm_intervals(
            start_timestamp_ms=_START + 1,
            interval_count=1,
            book_states=(
                _state(
                    transaction_time_ms=_START + 500,
                    update_id=1,
                ),
            ),
            aggregate_trades=(),
        )


def test_book_states_must_be_ordered() -> None:
    with pytest.raises(
        BinanceUsdMIntervalAggregationError,
        match="ordered by transaction time",
    ):
        aggregate_binance_usdm_intervals(
            start_timestamp_ms=_START,
            interval_count=1,
            book_states=(
                _state(
                    transaction_time_ms=_START + 900,
                    update_id=1,
                ),
                _state(
                    transaction_time_ms=_START + 500,
                    update_id=2,
                ),
            ),
            aggregate_trades=(),
        )


def test_book_update_ids_must_increase() -> None:
    with pytest.raises(
        BinanceUsdMIntervalAggregationError,
        match="update ids must increase strictly",
    ):
        aggregate_binance_usdm_intervals(
            start_timestamp_ms=_START,
            interval_count=1,
            book_states=(
                _state(
                    transaction_time_ms=_START + 500,
                    update_id=2,
                ),
                _state(
                    transaction_time_ms=_START + 600,
                    update_id=1,
                ),
            ),
            aggregate_trades=(),
        )


def test_trades_must_be_ordered_by_trade_time() -> None:
    with pytest.raises(
        BinanceUsdMIntervalAggregationError,
        match="ordered by trade time",
    ):
        aggregate_binance_usdm_intervals(
            start_timestamp_ms=_START,
            interval_count=1,
            book_states=(
                _state(
                    transaction_time_ms=_START + 900,
                    update_id=1,
                ),
            ),
            aggregate_trades=(
                _trade(
                    trade_time_ms=_START + 500,
                    trade_id=1,
                    normal_quantity="1",
                    buyer_is_maker=False,
                ),
                _trade(
                    trade_time_ms=_START + 400,
                    trade_id=2,
                    normal_quantity="1",
                    buyer_is_maker=False,
                ),
            ),
        )


def test_trade_ids_must_increase() -> None:
    with pytest.raises(
        BinanceUsdMIntervalAggregationError,
        match="ids must increase strictly",
    ):
        aggregate_binance_usdm_intervals(
            start_timestamp_ms=_START,
            interval_count=1,
            book_states=(
                _state(
                    transaction_time_ms=_START + 900,
                    update_id=1,
                ),
            ),
            aggregate_trades=(
                _trade(
                    trade_time_ms=_START + 400,
                    trade_id=2,
                    normal_quantity="1",
                    buyer_is_maker=False,
                ),
                _trade(
                    trade_time_ms=_START + 500,
                    trade_id=1,
                    normal_quantity="1",
                    buyer_is_maker=False,
                ),
            ),
        )


def test_trade_outside_window_is_rejected() -> None:
    with pytest.raises(
        BinanceUsdMIntervalAggregationError,
        match="trade time lies outside",
    ):
        aggregate_binance_usdm_intervals(
            start_timestamp_ms=_START,
            interval_count=1,
            book_states=(
                _state(
                    transaction_time_ms=_START + 900,
                    update_id=1,
                ),
            ),
            aggregate_trades=(
                _trade(
                    trade_time_ms=_START + 1_000,
                    trade_id=1,
                    normal_quantity="1",
                    buyer_is_maker=False,
                ),
            ),
        )


def test_book_state_outside_window_is_rejected() -> None:
    with pytest.raises(
        BinanceUsdMIntervalAggregationError,
        match="book-state transaction time lies outside",
    ):
        aggregate_binance_usdm_intervals(
            start_timestamp_ms=_START,
            interval_count=1,
            book_states=(
                _state(
                    transaction_time_ms=_START + 1_000,
                    update_id=1,
                ),
            ),
            aggregate_trades=(),
        )


def test_interval_count_must_be_positive() -> None:
    with pytest.raises(
        BinanceUsdMIntervalAggregationError,
        match="interval_count must be positive",
    ):
        aggregate_binance_usdm_intervals(
            start_timestamp_ms=_START,
            interval_count=0,
            book_states=(),
            aggregate_trades=(),
        )


def test_book_states_must_not_be_empty() -> None:
    with pytest.raises(
        BinanceUsdMIntervalAggregationError,
        match="must not be empty",
    ):
        aggregate_binance_usdm_intervals(
            start_timestamp_ms=_START,
            interval_count=1,
            book_states=(),
            aggregate_trades=(),
        )
