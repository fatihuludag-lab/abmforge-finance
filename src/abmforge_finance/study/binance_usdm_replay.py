"""Offline deterministic replay of Binance USD-M raw capture artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from abmforge_finance.exceptions import FinanceArtifactVerificationError
from abmforge_finance.study.binance_usdm_artifacts import (
    BinanceUsdMRawChannel,
    BinanceUsdMRawRecord,
    verify_binance_usdm_raw_capture,
)
from abmforge_finance.study.binance_usdm_collector import (
    BinanceUsdMCaptureProcessor,
    BinanceUsdMCaptureProcessorResult,
)
from abmforge_finance.study.binance_usdm_events import (
    BinanceUsdMDepthSnapshot,
)
from abmforge_finance.study.binance_usdm_intervals import (
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
