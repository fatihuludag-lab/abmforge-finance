"""Live Binance USD-M collector for Phase 11 empirical validation."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.binance_usdm_artifacts import (
    BinanceUsdMCaptureProvenance,
    BinanceUsdMRawCaptureStreamWriter,
    BinanceUsdMRawChannel,
    BinanceUsdMRawRecord,
    write_binance_usdm_raw_capture,
)
from abmforge_finance.study.binance_usdm_book import (
    BinanceUsdMBookSynchronizationError,
    BinanceUsdMLocalBook,
    BinanceUsdMLocalBookState,
)
from abmforge_finance.study.binance_usdm_contract import (
    BinanceUsdMEmpiricalContract,
    binance_usdm_empirical_contract,
)
from abmforge_finance.study.binance_usdm_events import (
    BinanceUsdMAggTradeEvent,
    BinanceUsdMDepthSnapshot,
    BinanceUsdMDepthUpdateEvent,
)
from abmforge_finance.study.binance_usdm_network import (
    BinanceUsdMNetworkError,
    fetch_binance_usdm_depth_snapshot,
    fetch_binance_usdm_exchange_info,
    load_websocket_connect,
)


class BinanceUsdMCaptureError(InvalidMetricInputError):
    """Raised when a live candidate capture cannot remain scientifically valid."""


@dataclass(frozen=True, slots=True)
class BinanceUsdMCaptureProcessorResult:
    """Validated result of processing one continuous raw source session."""

    records: tuple[BinanceUsdMRawRecord, ...]
    final_book_state: BinanceUsdMLocalBookState
    book_states: tuple[BinanceUsdMLocalBookState, ...]
    aggregate_trades: tuple[BinanceUsdMAggTradeEvent, ...]
    depth_update_count: int
    aggregate_trade_count: int


@dataclass(frozen=True, slots=True)
class BinanceUsdMCaptureProcessorSummary:
    """Bounded-memory final capture state."""

    raw_record_count: int
    final_book_state: BinanceUsdMLocalBookState
    initial_snapshot_update_id: int
    depth_update_count: int
    aggregate_trade_count: int


@dataclass(frozen=True, slots=True)
class BinanceUsdMSmokeCaptureResult:
    """Result of one bounded non-official live smoke capture."""

    artifact_directory: Path
    capture_id: str
    candidate_id: str
    raw_record_count: int
    depth_update_count: int
    aggregate_trade_count: int
    initial_snapshot_update_id: int
    final_book_update_id: int
    final_best_bid: str
    final_best_ask: str
    started_at_ns: int
    ended_at_ns: int


class BinanceUsdMCaptureProcessor:
    """Deterministic raw-message processor independent of network transport."""

    __slots__ = (
        "_aggregate_trade_count",
        "_aggregate_trade_sink",
        "_aggregate_trades",
        "_book",
        "_book_state_sink",
        "_book_states",
        "_contract",
        "_depth_buffer",
        "_depth_update_count",
        "_last_received_at_ns",
        "_record_count",
        "_record_sink",
        "_records",
        "_retain_aggregate_trades",
        "_retain_book_states",
        "_retain_records",
        "_snapshot",
    )

    def __init__(
        self,
        *,
        contract: BinanceUsdMEmpiricalContract | None = None,
        record_sink: (Callable[[BinanceUsdMRawRecord], None] | None) = None,
        book_state_sink: (Callable[[BinanceUsdMLocalBookState], None] | None) = None,
        aggregate_trade_sink: (Callable[[BinanceUsdMAggTradeEvent], None] | None) = None,
        retain_records: bool = True,
        retain_book_states: bool = True,
        retain_aggregate_trades: bool = True,
    ) -> None:
        self._contract = binance_usdm_empirical_contract() if contract is None else contract
        self._records: list[BinanceUsdMRawRecord] = []
        self._depth_buffer: list[BinanceUsdMDepthUpdateEvent] = []
        self._snapshot: BinanceUsdMDepthSnapshot | None = None
        self._book: BinanceUsdMLocalBook | None = None
        self._book_states: list[BinanceUsdMLocalBookState] = []
        self._aggregate_trades: list[BinanceUsdMAggTradeEvent] = []
        self._depth_update_count = 0
        self._aggregate_trade_count = 0
        self._record_count = 0
        self._last_received_at_ns = -1
        self._record_sink = record_sink
        self._book_state_sink = book_state_sink
        self._aggregate_trade_sink = aggregate_trade_sink
        self._retain_records = retain_records
        self._retain_book_states = retain_book_states
        self._retain_aggregate_trades = retain_aggregate_trades

    @property
    def is_synchronized(self) -> bool:
        """Return whether the local depth book is synchronized."""

        return self._book is not None

    def _record(
        self,
        *,
        channel: BinanceUsdMRawChannel,
        received_at_ns: int,
        raw_json: str,
    ) -> None:
        if (
            isinstance(received_at_ns, bool)
            or not isinstance(received_at_ns, int)
            or received_at_ns < 0
        ):
            raise BinanceUsdMCaptureError("received_at_ns must be a non-negative integer")

        if received_at_ns < self._last_received_at_ns:
            raise BinanceUsdMCaptureError("raw receipt timestamps must be non-decreasing")

        record = BinanceUsdMRawRecord(
            sequence_number=self._record_count,
            channel=channel,
            received_at_ns=received_at_ns,
            raw_json=raw_json,
        )

        if self._record_sink is not None:
            self._record_sink(record)

        if self._retain_records:
            self._records.append(record)

        self._record_count += 1
        self._last_received_at_ns = received_at_ns

    def _emit_book_state(self) -> None:
        if self._book is None:
            return

        if self._book_state_sink is None and not self._retain_book_states:
            return

        state = self._book.state()

        if self._book_state_sink is not None:
            self._book_state_sink(state)

        if self._retain_book_states:
            self._book_states.append(state)

    def accept_depth_update(
        self,
        raw_json: str,
        *,
        received_at_ns: int,
    ) -> None:
        """Accept one exact raw diff-depth WebSocket message."""

        self._record(
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=received_at_ns,
            raw_json=raw_json,
        )

        try:
            value = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise BinanceUsdMCaptureError("depth update contains invalid JSON") from exc

        if not isinstance(value, dict):
            raise BinanceUsdMCaptureError("depth update must contain a JSON object")

        event = BinanceUsdMDepthUpdateEvent.from_mapping(
            value,
            contract=self._contract,
        )

        self._depth_update_count += 1

        if self._book is not None:
            try:
                self._book.apply(event)
            except BinanceUsdMBookSynchronizationError as exc:
                raise BinanceUsdMCaptureError("depth update continuity failure") from exc

            self._emit_book_state()
            return

        self._depth_buffer.append(event)
        self._attempt_synchronization()

    def accept_aggregate_trade(
        self,
        raw_json: str,
        *,
        received_at_ns: int,
    ) -> None:
        """Accept one exact raw aggregate-trade WebSocket message."""

        self._record(
            channel=BinanceUsdMRawChannel.AGGREGATE_TRADE,
            received_at_ns=received_at_ns,
            raw_json=raw_json,
        )

        try:
            value = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise BinanceUsdMCaptureError("aggregate trade contains invalid JSON") from exc

        if not isinstance(value, dict):
            raise BinanceUsdMCaptureError("aggregate trade must contain a JSON object")

        event = BinanceUsdMAggTradeEvent.from_mapping(
            value,
            contract=self._contract,
        )

        if self._aggregate_trade_sink is not None:
            self._aggregate_trade_sink(event)

        if self._retain_aggregate_trades:
            self._aggregate_trades.append(event)

        self._aggregate_trade_count += 1

    def accept_depth_snapshot(
        self,
        raw_json: str,
        snapshot: BinanceUsdMDepthSnapshot,
        *,
        received_at_ns: int,
    ) -> None:
        """Accept the single REST snapshot for this continuous candidate."""

        if self._snapshot is not None:
            raise BinanceUsdMCaptureError(
                "candidate capture cannot contain more than one depth snapshot"
            )

        if not isinstance(
            snapshot,
            BinanceUsdMDepthSnapshot,
        ):
            raise TypeError("snapshot must be a BinanceUsdMDepthSnapshot")

        self._record(
            channel=BinanceUsdMRawChannel.DEPTH_SNAPSHOT,
            received_at_ns=received_at_ns,
            raw_json=raw_json,
        )

        self._snapshot = snapshot
        self._attempt_synchronization()

    def _attempt_synchronization(self) -> None:
        if self._snapshot is None or self._book is not None:
            return

        snapshot_id = self._snapshot.last_update_id

        retained = tuple(
            event for event in self._depth_buffer if event.final_update_id >= snapshot_id
        )

        if not retained:
            return

        first = retained[0]

        if first.first_update_id > snapshot_id:
            raise BinanceUsdMCaptureError("buffer skipped the required snapshot bridge event")

        if not (first.first_update_id <= snapshot_id <= first.final_update_id):
            return

        try:
            # Synchronize with the bridge event first so every
            # subsequent local-book state can be retained individually.
            self._book = BinanceUsdMLocalBook.synchronize(
                self._snapshot,
                (first,),
                contract=self._contract,
            )

            self._emit_book_state()

            for event in retained[1:]:
                self._book.apply(event)
                self._emit_book_state()

        except BinanceUsdMBookSynchronizationError as exc:
            raise BinanceUsdMCaptureError("depth snapshot synchronization failed") from exc

        self._depth_buffer.clear()

    def finalize(self) -> BinanceUsdMCaptureProcessorResult:
        """Finalize a continuous session after both streams are closed."""

        if self._snapshot is None:
            raise BinanceUsdMCaptureError("capture did not obtain a depth snapshot")

        if self._book is None:
            raise BinanceUsdMCaptureError("capture never synchronized the local depth book")

        if not self._records:
            raise BinanceUsdMCaptureError("capture contains no raw records")

        if not self._book_states:
            raise BinanceUsdMCaptureError("capture contains no synchronized book-state timeline")

        return BinanceUsdMCaptureProcessorResult(
            records=tuple(self._records),
            final_book_state=self._book.state(),
            book_states=tuple(self._book_states),
            aggregate_trades=tuple(self._aggregate_trades),
            depth_update_count=self._depth_update_count,
            aggregate_trade_count=(self._aggregate_trade_count),
        )

    def finalize_summary(
        self,
    ) -> BinanceUsdMCaptureProcessorSummary:
        """Finalize without materializing retained timelines."""

        if self._snapshot is None:
            raise BinanceUsdMCaptureError("capture did not obtain a depth snapshot")

        if self._book is None:
            raise BinanceUsdMCaptureError("capture never synchronized the local depth book")

        if self._record_count < 1:
            raise BinanceUsdMCaptureError("capture contains no raw records")

        return BinanceUsdMCaptureProcessorSummary(
            raw_record_count=(self._record_count),
            final_book_state=(self._book.state()),
            initial_snapshot_update_id=(self._snapshot.last_update_id),
            depth_update_count=(self._depth_update_count),
            aggregate_trade_count=(self._aggregate_trade_count),
        )


async def _read_depth_stream(
    websocket: Any,
    processor: BinanceUsdMCaptureProcessor,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            message = await asyncio.wait_for(
                websocket.recv(),
                timeout=0.25,
            )
        except asyncio.TimeoutError:
            continue

        if not isinstance(message, str):
            raise BinanceUsdMNetworkError("Binance depth WebSocket must deliver text frames")

        processor.accept_depth_update(
            message,
            received_at_ns=time.time_ns(),
        )


async def _read_trade_stream(
    websocket: Any,
    processor: BinanceUsdMCaptureProcessor,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            message = await asyncio.wait_for(
                websocket.recv(),
                timeout=0.25,
            )
        except asyncio.TimeoutError:
            continue

        if not isinstance(message, str):
            raise BinanceUsdMNetworkError(
                "Binance aggregate-trade WebSocket must deliver text frames"
            )

        processor.accept_aggregate_trade(
            message,
            received_at_ns=time.time_ns(),
        )


BINANCE_USDM_REFERENCE_CANDIDATE_CAPTURE_SECONDS = 4_200.0


@dataclass(frozen=True, slots=True)
class BinanceUsdMCandidateCaptureResult:
    """Result of one official ADR-033 empirical candidate capture."""

    artifact_directory: Path
    capture_id: str
    candidate_id: str
    raw_record_count: int
    depth_update_count: int
    aggregate_trade_count: int
    initial_snapshot_update_id: int
    final_book_update_id: int
    final_best_bid: str
    final_best_ask: str
    started_at_ns: int
    ended_at_ns: int


@dataclass(frozen=True, slots=True)
class _BinanceUsdMLiveCaptureSessionResult:
    artifact_directory: Path
    processed: BinanceUsdMCaptureProcessorResult
    initial_snapshot_update_id: int
    started_at_ns: int
    ended_at_ns: int


def _smoke_duration(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("duration_seconds must be a real number")

    duration = float(value)

    if duration <= 0.0 or duration > 60.0:
        raise BinanceUsdMCaptureError("SMOKE_ONLY duration_seconds must be in (0, 60]")

    return duration


async def _capture_binance_usdm_session(
    directory: str | Path,
    *,
    repository_commit_sha: str,
    capture_id: str,
    candidate_id: str,
    duration_seconds: float,
    contract: BinanceUsdMEmpiricalContract | None,
) -> _BinanceUsdMLiveCaptureSessionResult:
    active_contract = binance_usdm_empirical_contract() if contract is None else contract

    await asyncio.to_thread(
        fetch_binance_usdm_exchange_info,
        contract=active_contract,
    )

    connect = load_websocket_connect()

    processor = BinanceUsdMCaptureProcessor(
        contract=active_contract,
    )

    stop = asyncio.Event()
    started_at_ns = time.time_ns()

    connection_options = {
        "open_timeout": 10.0,
        "ping_interval": None,
        "ping_timeout": None,
        "close_timeout": 5.0,
        "max_size": 8 * 1024 * 1024,
        "max_queue": 256,
    }

    async with connect(
        active_contract.depth_websocket_url,
        **connection_options,
    ) as depth_websocket:
        depth_task = asyncio.create_task(
            _read_depth_stream(
                depth_websocket,
                processor,
                stop,
            )
        )

        try:
            async with connect(
                active_contract.aggregate_trade_websocket_url,
                **connection_options,
            ) as trade_websocket:
                trade_task = asyncio.create_task(
                    _read_trade_stream(
                        trade_websocket,
                        processor,
                        stop,
                    )
                )

                try:
                    (
                        snapshot_raw,
                        snapshot,
                    ) = await asyncio.to_thread(
                        fetch_binance_usdm_depth_snapshot,
                        contract=active_contract,
                    )

                    processor.accept_depth_snapshot(
                        snapshot_raw,
                        snapshot,
                        received_at_ns=time.time_ns(),
                    )

                    await asyncio.sleep(duration_seconds)

                finally:
                    stop.set()

                    await asyncio.gather(
                        depth_task,
                        trade_task,
                    )

        finally:
            stop.set()

            if not depth_task.done():
                await depth_task

    processed = processor.finalize()

    ended_at_ns = time.time_ns()

    if ended_at_ns <= started_at_ns:
        ended_at_ns = started_at_ns + 1

    provenance = BinanceUsdMCaptureProvenance(
        capture_id=capture_id,
        candidate_id=candidate_id,
        repository_commit_sha=repository_commit_sha,
        started_at_ns=started_at_ns,
        ended_at_ns=ended_at_ns,
    )

    artifact_directory = write_binance_usdm_raw_capture(
        processed.records,
        directory,
        provenance=provenance,
        contract=active_contract,
    )

    snapshot_records = tuple(
        record
        for record in processed.records
        if record.channel is BinanceUsdMRawChannel.DEPTH_SNAPSHOT
    )

    if len(snapshot_records) != 1:
        raise BinanceUsdMCaptureError("successful capture must contain exactly one snapshot")

    snapshot_value = json.loads(snapshot_records[0].raw_json)

    if (
        not isinstance(snapshot_value, dict)
        or isinstance(
            snapshot_value.get("lastUpdateId"),
            bool,
        )
        or not isinstance(
            snapshot_value.get("lastUpdateId"),
            int,
        )
    ):
        raise BinanceUsdMCaptureError("captured depth snapshot has invalid lastUpdateId")

    return _BinanceUsdMLiveCaptureSessionResult(
        artifact_directory=artifact_directory,
        processed=processed,
        initial_snapshot_update_id=(snapshot_value["lastUpdateId"]),
        started_at_ns=started_at_ns,
        ended_at_ns=ended_at_ns,
    )


async def capture_binance_usdm_smoke(
    directory: str | Path,
    *,
    repository_commit_sha: str,
    capture_id: str = "smoke-btcusdt",
    candidate_id: str = "SMOKE_ONLY",
    duration_seconds: float = 5.0,
    contract: BinanceUsdMEmpiricalContract | None = None,
) -> BinanceUsdMSmokeCaptureResult:
    """Run one bounded non-official BTCUSDT live capture."""

    duration = _smoke_duration(duration_seconds)

    session = await _capture_binance_usdm_session(
        directory,
        repository_commit_sha=repository_commit_sha,
        capture_id=capture_id,
        candidate_id=candidate_id,
        duration_seconds=duration,
        contract=contract,
    )

    processed = session.processed

    return BinanceUsdMSmokeCaptureResult(
        artifact_directory=(session.artifact_directory),
        capture_id=capture_id,
        candidate_id=candidate_id,
        raw_record_count=len(processed.records),
        depth_update_count=(processed.depth_update_count),
        aggregate_trade_count=(processed.aggregate_trade_count),
        initial_snapshot_update_id=(session.initial_snapshot_update_id),
        final_book_update_id=(processed.final_book_state.last_update_id),
        final_best_bid=str(processed.final_book_state.best_bid),
        final_best_ask=str(processed.final_book_state.best_ask),
        started_at_ns=session.started_at_ns,
        ended_at_ns=session.ended_at_ns,
    )


async def _capture_binance_usdm_candidate_streaming(
    directory: str | Path,
    *,
    repository_commit_sha: str,
    capture_id: str,
    candidate_id: str,
    duration_seconds: float,
    contract: BinanceUsdMEmpiricalContract | None = None,
) -> BinanceUsdMCandidateCaptureResult:
    """Capture one official ADR-033 reference-set candidate."""

    active_contract = binance_usdm_empirical_contract() if contract is None else contract

    await asyncio.to_thread(
        fetch_binance_usdm_exchange_info,
        contract=active_contract,
    )

    connect = load_websocket_connect()

    writer = BinanceUsdMRawCaptureStreamWriter(
        directory,
        contract=active_contract,
    )

    processor = BinanceUsdMCaptureProcessor(
        contract=active_contract,
        record_sink=writer.append,
        retain_records=False,
        retain_book_states=False,
        retain_aggregate_trades=False,
    )

    stop = asyncio.Event()
    started_at_ns = time.time_ns()

    connection_options = {
        "open_timeout": 10.0,
        "ping_interval": None,
        "ping_timeout": None,
        "close_timeout": 5.0,
        "max_size": 8 * 1024 * 1024,
        "max_queue": 256,
    }

    try:
        async with connect(
            active_contract.depth_websocket_url,
            **connection_options,
        ) as depth_websocket:
            depth_task = asyncio.create_task(
                _read_depth_stream(
                    depth_websocket,
                    processor,
                    stop,
                )
            )

            try:
                async with connect(
                    active_contract.aggregate_trade_websocket_url,
                    **connection_options,
                ) as trade_websocket:
                    trade_task = asyncio.create_task(
                        _read_trade_stream(
                            trade_websocket,
                            processor,
                            stop,
                        )
                    )

                    try:
                        (
                            snapshot_raw,
                            snapshot,
                        ) = await asyncio.to_thread(
                            fetch_binance_usdm_depth_snapshot,
                            contract=active_contract,
                        )

                        processor.accept_depth_snapshot(
                            snapshot_raw,
                            snapshot,
                            received_at_ns=time.time_ns(),
                        )

                        await asyncio.sleep(duration_seconds)

                    finally:
                        stop.set()

                        await asyncio.gather(
                            depth_task,
                            trade_task,
                        )

            finally:
                stop.set()

                if not depth_task.done():
                    await depth_task

        summary = processor.finalize_summary()

        ended_at_ns = time.time_ns()

        if ended_at_ns <= started_at_ns:
            ended_at_ns = started_at_ns + 1

        provenance = BinanceUsdMCaptureProvenance(
            capture_id=capture_id,
            candidate_id=candidate_id,
            repository_commit_sha=(repository_commit_sha),
            started_at_ns=(started_at_ns),
            ended_at_ns=ended_at_ns,
        )

        artifact_directory = writer.finalize(provenance=provenance)

    except BaseException:
        writer.abort()
        raise

    final_state = summary.final_book_state

    return BinanceUsdMCandidateCaptureResult(
        artifact_directory=(artifact_directory),
        capture_id=capture_id,
        candidate_id=candidate_id,
        raw_record_count=(summary.raw_record_count),
        depth_update_count=(summary.depth_update_count),
        aggregate_trade_count=(summary.aggregate_trade_count),
        initial_snapshot_update_id=(summary.initial_snapshot_update_id),
        final_book_update_id=(final_state.last_update_id),
        final_best_bid=str(final_state.best_bid),
        final_best_ask=str(final_state.best_ask),
        started_at_ns=started_at_ns,
        ended_at_ns=ended_at_ns,
    )


async def capture_binance_usdm_candidate(
    directory: str | Path,
    *,
    repository_commit_sha: str,
    capture_id: str,
    candidate_id: str,
    contract: BinanceUsdMEmpiricalContract | None = None,
) -> BinanceUsdMCandidateCaptureResult:
    """Capture one official ADR-033 reference-set candidate."""

    return await _capture_binance_usdm_candidate_streaming(
        directory,
        repository_commit_sha=repository_commit_sha,
        capture_id=capture_id,
        candidate_id=candidate_id,
        duration_seconds=(BINANCE_USDM_REFERENCE_CANDIDATE_CAPTURE_SECONDS),
        contract=contract,
    )
