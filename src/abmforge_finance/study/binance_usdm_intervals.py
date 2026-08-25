"""Deterministic one-second Binance USD-M empirical interval aggregation."""

from __future__ import annotations

from decimal import Decimal

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.binance_usdm_book import (
    BinanceUsdMLocalBookState,
)
from abmforge_finance.study.binance_usdm_contract import (
    BinanceUsdMEmpiricalContract,
    binance_usdm_empirical_contract,
)
from abmforge_finance.study.binance_usdm_events import (
    BinanceUsdMAggTradeEvent,
)
from abmforge_finance.study.stylized_empirical import (
    EmpiricalMarketInterval,
)

_MILLISECONDS_PER_SECOND = 1_000
_NANOSECONDS_PER_MILLISECOND = 1_000_000
_ZERO = Decimal("0")


class BinanceUsdMIntervalAggregationError(InvalidMetricInputError):
    """Raised when raw synchronized observations cannot form valid intervals."""


def _non_negative_integer(
    value: object,
    *,
    label: str,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BinanceUsdMIntervalAggregationError(f"{label} must be a non-negative integer")

    if value < 0:
        raise BinanceUsdMIntervalAggregationError(f"{label} must be a non-negative integer")

    return value


def _positive_integer(
    value: object,
    *,
    label: str,
) -> int:
    number = _non_negative_integer(
        value,
        label=label,
    )

    if number == 0:
        raise BinanceUsdMIntervalAggregationError(f"{label} must be positive")

    return number


def _validate_book_states(
    states: tuple[BinanceUsdMLocalBookState, ...],
    *,
    contract: BinanceUsdMEmpiricalContract,
    start_timestamp_ms: int,
    stop_timestamp_ms: int,
) -> None:
    if not isinstance(states, tuple):
        raise TypeError("book_states must be a tuple")

    if not states:
        raise BinanceUsdMIntervalAggregationError("book_states must not be empty")

    previous_transaction_time = -1
    previous_update_id = -1

    for index, state in enumerate(states):
        if not isinstance(
            state,
            BinanceUsdMLocalBookState,
        ):
            raise TypeError(f"book_states[{index}] must be a BinanceUsdMLocalBookState")

        if state.symbol != contract.symbol:
            raise BinanceUsdMIntervalAggregationError(
                "book-state symbol does not match the frozen contract"
            )

        if not (start_timestamp_ms <= state.transaction_time_ms < stop_timestamp_ms):
            raise BinanceUsdMIntervalAggregationError(
                "book-state transaction time lies outside the aggregation window"
            )

        if state.transaction_time_ms < previous_transaction_time:
            raise BinanceUsdMIntervalAggregationError(
                "book states must be ordered by transaction time"
            )

        if state.last_update_id <= previous_update_id:
            raise BinanceUsdMIntervalAggregationError(
                "book-state update ids must increase strictly"
            )

        previous_transaction_time = state.transaction_time_ms
        previous_update_id = state.last_update_id


def _validate_trades(
    trades: tuple[BinanceUsdMAggTradeEvent, ...],
    *,
    contract: BinanceUsdMEmpiricalContract,
    start_timestamp_ms: int,
    stop_timestamp_ms: int,
) -> None:
    if not isinstance(trades, tuple):
        raise TypeError("aggregate_trades must be a tuple")

    previous_trade_time = -1
    previous_trade_id = -1

    for index, event in enumerate(trades):
        if not isinstance(
            event,
            BinanceUsdMAggTradeEvent,
        ):
            raise TypeError(f"aggregate_trades[{index}] must be a BinanceUsdMAggTradeEvent")

        if event.symbol != contract.symbol:
            raise BinanceUsdMIntervalAggregationError(
                "aggregate-trade symbol does not match the frozen contract"
            )

        if event.symbol_type != contract.required_symbol_type:
            raise BinanceUsdMIntervalAggregationError(
                "aggregate-trade symbol type does not match the frozen contract"
            )

        if not (start_timestamp_ms <= event.trade_time_ms < stop_timestamp_ms):
            raise BinanceUsdMIntervalAggregationError(
                "aggregate-trade time lies outside the aggregation window"
            )

        if event.trade_time_ms < previous_trade_time:
            raise BinanceUsdMIntervalAggregationError(
                "aggregate trades must be ordered by trade time"
            )

        if event.aggregate_trade_id <= previous_trade_id:
            raise BinanceUsdMIntervalAggregationError("aggregate-trade ids must increase strictly")

        previous_trade_time = event.trade_time_ms
        previous_trade_id = event.aggregate_trade_id


def aggregate_binance_usdm_intervals(
    *,
    start_timestamp_ms: int,
    interval_count: int,
    book_states: tuple[BinanceUsdMLocalBookState, ...],
    aggregate_trades: tuple[BinanceUsdMAggTradeEvent, ...],
    contract: BinanceUsdMEmpiricalContract | None = None,
) -> tuple[EmpiricalMarketInterval, ...]:
    """Aggregate synchronized Binance observations into UTC one-second intervals."""

    active_contract = binance_usdm_empirical_contract() if contract is None else contract

    start = _non_negative_integer(
        start_timestamp_ms,
        label="start_timestamp_ms",
    )
    count = _positive_integer(
        interval_count,
        label="interval_count",
    )

    interval_ms = active_contract.interval_ns // _NANOSECONDS_PER_MILLISECOND

    if interval_ms != _MILLISECONDS_PER_SECOND:
        raise BinanceUsdMIntervalAggregationError(
            "Binance empirical contract must use one-second intervals"
        )

    if start % interval_ms != 0:
        raise BinanceUsdMIntervalAggregationError(
            "start_timestamp_ms must be aligned to a UTC-second boundary"
        )

    stop = start + count * interval_ms

    _validate_book_states(
        book_states,
        contract=active_contract,
        start_timestamp_ms=start,
        stop_timestamp_ms=stop,
    )

    _validate_trades(
        aggregate_trades,
        contract=active_contract,
        start_timestamp_ms=start,
        stop_timestamp_ms=stop,
    )

    states_by_interval: list[list[BinanceUsdMLocalBookState]] = [[] for _ in range(count)]

    for state in book_states:
        index = (state.transaction_time_ms - start) // interval_ms

        states_by_interval[index].append(state)

    buy_quantity = [_ZERO for _ in range(count)]
    sell_quantity = [_ZERO for _ in range(count)]

    for event in aggregate_trades:
        index = (event.trade_time_ms - start) // interval_ms

        if event.buyer_is_maker:
            sell_quantity[index] += event.normal_quantity
        else:
            buy_quantity[index] += event.normal_quantity

    output: list[EmpiricalMarketInterval] = []

    for index in range(count):
        states = states_by_interval[index]

        if not states:
            interval_start = start + index * interval_ms
            raise BinanceUsdMIntervalAggregationError(
                f"no synchronized book state observed in interval beginning at {interval_start}"
            )

        closing_state = states[-1]

        total_quantity = buy_quantity[index] + sell_quantity[index]

        if total_quantity == _ZERO:
            flow = active_contract.no_trade_flow_value
        else:
            flow = float((buy_quantity[index] - sell_quantity[index]) / total_quantity)

        interval_start_ms = start + index * interval_ms
        interval_end_ms = interval_start_ms + interval_ms

        output.append(
            EmpiricalMarketInterval(
                start_timestamp_ns=(interval_start_ms * _NANOSECONDS_PER_MILLISECOND),
                end_timestamp_ns=(interval_end_ms * _NANOSECONDS_PER_MILLISECOND),
                mid_price=float(closing_state.midpoint),
                aggressor_flow=flow,
                thin_side_depth=float(closing_state.thin_side_depth),
            )
        )

    return tuple(output)
