"""Offline deterministic replay of Binance USD-M raw capture artifacts."""

from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal
from heapq import merge
from pathlib import Path

from abmforge_finance.exceptions import FinanceArtifactVerificationError
from abmforge_finance.study.binance_usdm_artifacts import (
    BinanceUsdMRawChannel,
    BinanceUsdMRawRecord,
    verify_binance_usdm_raw_capture,
)
from abmforge_finance.study.binance_usdm_book import (
    BinanceUsdMLocalBookState,
)
from abmforge_finance.study.binance_usdm_collector import (
    BinanceUsdMCaptureProcessor,
    BinanceUsdMCaptureProcessorResult,
)
from abmforge_finance.study.binance_usdm_contract import (
    binance_usdm_empirical_contract,
)
from abmforge_finance.study.binance_usdm_events import (
    BinanceUsdMAggTradeEvent,
    BinanceUsdMDepthSnapshot,
)
from abmforge_finance.study.binance_usdm_intervals import (
    BinanceUsdMIntervalAggregationError,
    aggregate_binance_usdm_intervals,
)
from abmforge_finance.study.stylized_empirical import (
    EmpiricalMarketInterval,
)

_FILE_BY_CHANNEL = {
    BinanceUsdMRawChannel.DEPTH_SNAPSHOT: "depth_snapshot.jsonl",
    BinanceUsdMRawChannel.DEPTH_UPDATE: "depth_updates.jsonl",
    BinanceUsdMRawChannel.AGGREGATE_TRADE: "aggregate_trades.jsonl",
}


def _load_channel(
    root: Path,
    channel: BinanceUsdMRawChannel,
) -> tuple[BinanceUsdMRawRecord, ...]:
    path = root / _FILE_BY_CHANNEL[channel]

    records: list[BinanceUsdMRawRecord] = []

    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)

        if not isinstance(value, dict):
            raise FinanceArtifactVerificationError(f"{path.name} row must contain an object")

        try:
            sequence_number = value["sequence_number"]
            received_at_ns = value["received_at_ns"]
            raw_json = value["raw_json"]
        except KeyError as exc:
            raise FinanceArtifactVerificationError(
                f"{path.name} row is missing required metadata"
            ) from exc

        records.append(
            BinanceUsdMRawRecord(
                sequence_number=sequence_number,
                channel=channel,
                received_at_ns=received_at_ns,
                raw_json=raw_json,
            )
        )

    return tuple(records)


def read_binance_usdm_raw_capture(
    directory: str | Path,
) -> tuple[BinanceUsdMRawRecord, ...]:
    """Read a verified raw artifact in original global capture order."""

    root = Path(directory)

    verify_binance_usdm_raw_capture(root)

    records = tuple(
        record for channel in BinanceUsdMRawChannel for record in _load_channel(root, channel)
    )

    return tuple(
        sorted(
            records,
            key=lambda record: record.sequence_number,
        )
    )


def replay_binance_usdm_raw_capture(
    directory: str | Path,
) -> BinanceUsdMCaptureProcessorResult:
    """Reconstruct a captured session using raw persisted observations only."""

    records = read_binance_usdm_raw_capture(directory)

    processor = BinanceUsdMCaptureProcessor()

    for record in records:
        if record.channel is BinanceUsdMRawChannel.DEPTH_UPDATE:
            processor.accept_depth_update(
                record.raw_json,
                received_at_ns=record.received_at_ns,
            )
            continue

        if record.channel is BinanceUsdMRawChannel.AGGREGATE_TRADE:
            processor.accept_aggregate_trade(
                record.raw_json,
                received_at_ns=record.received_at_ns,
            )
            continue

        if record.channel is BinanceUsdMRawChannel.DEPTH_SNAPSHOT:
            value = json.loads(record.raw_json)

            if not isinstance(value, dict):
                raise FinanceArtifactVerificationError(
                    "depth snapshot raw payload must contain an object"
                )

            snapshot = BinanceUsdMDepthSnapshot.from_mapping(value)

            processor.accept_depth_snapshot(
                record.raw_json,
                snapshot,
                received_at_ns=record.received_at_ns,
            )
            continue

        raise FinanceArtifactVerificationError(f"unsupported raw channel: {record.channel}")

    return processor.finalize()


def reconstruct_binance_usdm_empirical_intervals(
    directory: str | Path,
) -> tuple[EmpiricalMarketInterval, ...]:
    """Reconstruct complete UTC seconds from a verified raw capture."""

    replay = replay_binance_usdm_raw_capture(directory)

    if not replay.book_states:
        raise FinanceArtifactVerificationError(
            "replay contains no synchronized book-state timeline"
        )

    if not replay.aggregate_trades:
        raise FinanceArtifactVerificationError(
            "replay contains no aggregate trade from which "
            "trade-stream readiness can be established"
        )

    first_book_time_ms = replay.book_states[0].transaction_time_ms
    first_trade_time_ms = replay.aggregate_trades[0].trade_time_ms

    # The first accepted empirical second must begin only after both
    # market-data streams have demonstrably become active.
    readiness_time_ms = max(
        first_book_time_ms,
        first_trade_time_ms,
    )

    start_timestamp_ms = ((readiness_time_ms + 999) // 1_000) * 1_000

    # The final accepted interval must end no later than a UTC
    # boundary that precedes the final synchronized depth event.
    # A successful capture artifact also implies the trade reader
    # remained alive until the coupled capture session closed.
    last_state_time_ms = replay.book_states[-1].transaction_time_ms

    stop_timestamp_ms = (last_state_time_ms // 1_000) * 1_000

    if stop_timestamp_ms <= start_timestamp_ms:
        raise FinanceArtifactVerificationError(
            "capture does not span one complete empirical second after market-data readiness"
        )

    interval_count = (stop_timestamp_ms - start_timestamp_ms) // 1_000

    # Include the latest pre-start state so the first accepted
    # interval can begin from a valid synchronized book.
    pre_start_states = tuple(
        state for state in replay.book_states if state.transaction_time_ms < start_timestamp_ms
    )

    if not pre_start_states:
        raise FinanceArtifactVerificationError(
            "no synchronized book state exists before the first complete empirical interval"
        )

    seed_state = pre_start_states[-1]

    in_window_states = tuple(
        state
        for state in replay.book_states
        if (start_timestamp_ms <= state.transaction_time_ms < stop_timestamp_ms)
    )

    states = (
        seed_state,
        *in_window_states,
    )

    trades = tuple(
        event
        for event in replay.aggregate_trades
        if (start_timestamp_ms <= event.trade_time_ms < stop_timestamp_ms)
    )

    return aggregate_binance_usdm_intervals(
        start_timestamp_ms=start_timestamp_ms,
        interval_count=interval_count,
        book_states=states,
        aggregate_trades=trades,
    )


def _iter_channel_streaming(
    root: Path,
    channel: BinanceUsdMRawChannel,
) -> Iterator[BinanceUsdMRawRecord]:
    """Read one already-verified channel one row at a time."""

    path = root / _FILE_BY_CHANNEL[channel]

    with path.open(
        "r",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        for line in handle:
            value = json.loads(line)

            if not isinstance(value, dict):
                raise FinanceArtifactVerificationError(f"{path.name} row must contain an object")

            try:
                sequence_number = value["sequence_number"]
                received_at_ns = value["received_at_ns"]
                raw_json = value["raw_json"]

            except KeyError as exc:
                raise FinanceArtifactVerificationError(
                    f"{path.name} row is missing required metadata"
                ) from exc

            yield BinanceUsdMRawRecord(
                sequence_number=sequence_number,
                channel=channel,
                received_at_ns=received_at_ns,
                raw_json=raw_json,
            )


def _iter_merged_raw_capture(
    root: Path,
) -> Iterator[BinanceUsdMRawRecord]:
    """Merge the three channel streams by global capture sequence."""

    yield from merge(
        *(
            _iter_channel_streaming(
                root,
                channel,
            )
            for channel in BinanceUsdMRawChannel
        ),
        key=lambda record: record.sequence_number,
    )


def _accept_streaming_replay_record(
    processor: BinanceUsdMCaptureProcessor,
    record: BinanceUsdMRawRecord,
) -> None:
    """Feed one persisted raw record into the deterministic processor."""

    if record.channel is BinanceUsdMRawChannel.DEPTH_UPDATE:
        processor.accept_depth_update(
            record.raw_json,
            received_at_ns=record.received_at_ns,
        )
        return

    if record.channel is BinanceUsdMRawChannel.AGGREGATE_TRADE:
        processor.accept_aggregate_trade(
            record.raw_json,
            received_at_ns=record.received_at_ns,
        )
        return

    if record.channel is BinanceUsdMRawChannel.DEPTH_SNAPSHOT:
        value = json.loads(record.raw_json)

        if not isinstance(value, dict):
            raise FinanceArtifactVerificationError(
                "depth snapshot raw payload must contain an object"
            )

        snapshot = BinanceUsdMDepthSnapshot.from_mapping(value)

        processor.accept_depth_snapshot(
            record.raw_json,
            snapshot,
            received_at_ns=record.received_at_ns,
        )
        return

    raise FinanceArtifactVerificationError(f"unsupported raw channel: {record.channel}")


def reconstruct_binance_usdm_empirical_intervals_streaming(
    directory: str | Path,
) -> tuple[EmpiricalMarketInterval, ...]:
    """Reconstruct complete UTC seconds with bounded memory.

    The raw artifact is verified once. Replay then uses two
    deterministic streaming passes. Only O(number of seconds)
    compact aggregation state is retained.
    """

    root = Path(directory)

    verify_binance_usdm_raw_capture(root)

    first_book_time_ms: int | None = None
    first_trade_time_ms: int | None = None
    last_book_time_ms: int | None = None

    def observe_first_pass_book(
        state: BinanceUsdMLocalBookState,
    ) -> None:
        nonlocal first_book_time_ms
        nonlocal last_book_time_ms

        if first_book_time_ms is None:
            first_book_time_ms = state.transaction_time_ms

        last_book_time_ms = state.transaction_time_ms

    def observe_first_pass_trade(
        event: BinanceUsdMAggTradeEvent,
    ) -> None:
        nonlocal first_trade_time_ms

        if first_trade_time_ms is None:
            first_trade_time_ms = event.trade_time_ms

    first_processor = BinanceUsdMCaptureProcessor(
        book_state_sink=(observe_first_pass_book),
        aggregate_trade_sink=(observe_first_pass_trade),
        retain_records=False,
        retain_book_states=False,
        retain_aggregate_trades=False,
    )

    for record in _iter_merged_raw_capture(root):
        _accept_streaming_replay_record(
            first_processor,
            record,
        )

    if first_book_time_ms is None:
        raise FinanceArtifactVerificationError(
            "replay contains no synchronized book-state timeline"
        )

    if first_trade_time_ms is None:
        raise FinanceArtifactVerificationError(
            "replay contains no aggregate trade from which "
            "trade-stream readiness can be established"
        )

    if last_book_time_ms is None:
        raise FinanceArtifactVerificationError(
            "replay contains no synchronized book-state timeline"
        )

    readiness_time_ms = max(
        first_book_time_ms,
        first_trade_time_ms,
    )

    start_timestamp_ms = ((readiness_time_ms + 999) // 1_000) * 1_000

    stop_timestamp_ms = (last_book_time_ms // 1_000) * 1_000

    if stop_timestamp_ms <= start_timestamp_ms:
        raise FinanceArtifactVerificationError(
            "capture does not span one complete empirical second after market-data readiness"
        )

    interval_count = (stop_timestamp_ms - start_timestamp_ms) // 1_000

    zero = Decimal("0")

    buy_quantity = [zero for _ in range(interval_count)]

    sell_quantity = [zero for _ in range(interval_count)]

    book_metrics: list[tuple[float, float] | None] = [None for _ in range(interval_count)]

    seed_metrics: tuple[int, int, float, float] | None = None

    previous_selected_state_time: int | None = None

    previous_selected_update_id: int | None = None

    previous_trade_time = -1
    previous_trade_id = -1

    def observe_second_pass_book(
        state: BinanceUsdMLocalBookState,
    ) -> None:
        nonlocal seed_metrics
        nonlocal previous_selected_state_time
        nonlocal previous_selected_update_id

        transaction_time = state.transaction_time_ms

        metrics = (
            transaction_time,
            state.last_update_id,
            float(state.midpoint),
            float(state.thin_side_depth),
        )

        if transaction_time < start_timestamp_ms:
            seed_metrics = metrics
            return

        if transaction_time >= stop_timestamp_ms:
            return

        if previous_selected_state_time is None and seed_metrics is not None:
            previous_selected_state_time = seed_metrics[0]
            previous_selected_update_id = seed_metrics[1]

        if (
            previous_selected_state_time is not None
            and transaction_time < previous_selected_state_time
        ):
            raise BinanceUsdMIntervalAggregationError(
                "book states must be ordered by transaction time"
            )

        if (
            previous_selected_update_id is not None
            and state.last_update_id <= previous_selected_update_id
        ):
            raise BinanceUsdMIntervalAggregationError(
                "book-state update ids must increase strictly"
            )

        index = (transaction_time - start_timestamp_ms) // 1_000

        book_metrics[index] = (
            metrics[2],
            metrics[3],
        )

        previous_selected_state_time = transaction_time

        previous_selected_update_id = state.last_update_id

    def observe_second_pass_trade(
        event: BinanceUsdMAggTradeEvent,
    ) -> None:
        nonlocal previous_trade_time
        nonlocal previous_trade_id

        trade_time = event.trade_time_ms

        if trade_time < start_timestamp_ms or trade_time >= stop_timestamp_ms:
            return

        if trade_time < previous_trade_time:
            raise BinanceUsdMIntervalAggregationError(
                "aggregate trades must be ordered by trade time"
            )

        if event.aggregate_trade_id <= previous_trade_id:
            raise BinanceUsdMIntervalAggregationError("aggregate-trade ids must increase strictly")

        index = (trade_time - start_timestamp_ms) // 1_000

        if event.buyer_is_maker:
            sell_quantity[index] += event.normal_quantity
        else:
            buy_quantity[index] += event.normal_quantity

        previous_trade_time = trade_time
        previous_trade_id = event.aggregate_trade_id

    second_processor = BinanceUsdMCaptureProcessor(
        book_state_sink=(observe_second_pass_book),
        aggregate_trade_sink=(observe_second_pass_trade),
        retain_records=False,
        retain_book_states=False,
        retain_aggregate_trades=False,
    )

    for record in _iter_merged_raw_capture(root):
        _accept_streaming_replay_record(
            second_processor,
            record,
        )

    if seed_metrics is None:
        raise FinanceArtifactVerificationError(
            "no synchronized book state exists before the first complete empirical interval"
        )

    active_contract = binance_usdm_empirical_contract()

    output: list[EmpiricalMarketInterval] = []

    latest_metrics = (
        seed_metrics[2],
        seed_metrics[3],
    )

    for index in range(interval_count):
        observed = book_metrics[index]

        if observed is not None:
            latest_metrics = observed

        total_quantity = buy_quantity[index] + sell_quantity[index]

        if total_quantity == zero:
            flow = active_contract.no_trade_flow_value
        else:
            flow = float((buy_quantity[index] - sell_quantity[index]) / total_quantity)

        interval_start_ms = start_timestamp_ms + index * 1_000

        interval_end_ms = interval_start_ms + 1_000

        output.append(
            EmpiricalMarketInterval(
                start_timestamp_ns=(interval_start_ms * 1_000_000),
                end_timestamp_ns=(interval_end_ms * 1_000_000),
                mid_price=(latest_metrics[0]),
                aggressor_flow=flow,
                thin_side_depth=(latest_metrics[1]),
            )
        )

    return tuple(output)
