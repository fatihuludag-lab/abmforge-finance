"""Tests for the Binance USD-M live-capture processor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from abmforge_finance.study.binance_usdm_collector import (
    BinanceUsdMCaptureError,
    BinanceUsdMCaptureProcessor,
)
from abmforge_finance.study.binance_usdm_events import (
    BinanceUsdMDepthSnapshot,
)
from abmforge_finance.study.binance_usdm_network import (
    BinanceUsdMNetworkError,
)


def _depth(
    *,
    first: int,
    final: int,
    previous: int,
    bid_quantity: str = "2",
) -> str:
    return json.dumps(
        {
            "e": "depthUpdate",
            "E": 1_000 + final,
            "T": 900 + final,
            "s": "BTCUSDT",
            "U": first,
            "u": final,
            "pu": previous,
            "b": [["100", bid_quantity]],
            "a": [["101", "3"]],
            "ps": "BTCUSDT",
            "st": 1,
        },
        separators=(",", ":"),
    )


def _trade(
    *,
    trade_id: int,
    maker: bool,
) -> str:
    return json.dumps(
        {
            "e": "aggTrade",
            "E": 2_000 + trade_id,
            "s": "BTCUSDT",
            "a": trade_id,
            "p": "100.5",
            "q": "2",
            "nq": "2",
            "f": trade_id,
            "l": trade_id,
            "T": 1_900 + trade_id,
            "m": maker,
            "st": 1,
        },
        separators=(",", ":"),
    )


def _snapshot_raw() -> str:
    return json.dumps(
        {
            "lastUpdateId": 100,
            "E": 1_500,
            "T": 1_499,
            "bids": [
                ["100", "5"],
                ["99", "4"],
            ],
            "asks": [
                ["101", "6"],
                ["102", "7"],
            ],
        },
        separators=(",", ":"),
    )


def _snapshot() -> BinanceUsdMDepthSnapshot:
    return BinanceUsdMDepthSnapshot.from_mapping(json.loads(_snapshot_raw()))


def test_processor_buffers_depth_before_snapshot_and_bridges() -> None:
    processor = BinanceUsdMCaptureProcessor()

    processor.accept_depth_update(
        _depth(
            first=99,
            final=102,
            previous=98,
        ),
        received_at_ns=1,
    )

    before_sync = processor.is_synchronized
    assert before_sync is False

    processor.accept_depth_snapshot(
        _snapshot_raw(),
        _snapshot(),
        received_at_ns=2,
    )

    after_sync = processor.is_synchronized
    assert after_sync is True

    result = processor.finalize()

    assert result.final_book_state.last_update_id == 102
    assert result.depth_update_count == 1
    assert result.aggregate_trade_count == 0
    assert len(result.records) == 2


def test_processor_applies_contiguous_post_sync_depth() -> None:
    processor = BinanceUsdMCaptureProcessor()

    processor.accept_depth_update(
        _depth(
            first=99,
            final=102,
            previous=98,
        ),
        received_at_ns=1,
    )
    processor.accept_depth_snapshot(
        _snapshot_raw(),
        _snapshot(),
        received_at_ns=2,
    )

    processor.accept_depth_update(
        _depth(
            first=103,
            final=105,
            previous=102,
            bid_quantity="8",
        ),
        received_at_ns=3,
    )

    result = processor.finalize()

    assert result.final_book_state.last_update_id == 105
    assert result.depth_update_count == 2


def test_processor_rejects_post_sync_sequence_gap() -> None:
    processor = BinanceUsdMCaptureProcessor()

    processor.accept_depth_update(
        _depth(
            first=99,
            final=102,
            previous=98,
        ),
        received_at_ns=1,
    )
    processor.accept_depth_snapshot(
        _snapshot_raw(),
        _snapshot(),
        received_at_ns=2,
    )

    with pytest.raises(
        BinanceUsdMCaptureError,
        match="continuity failure",
    ):
        processor.accept_depth_update(
            _depth(
                first=103,
                final=105,
                previous=101,
            ),
            received_at_ns=3,
        )


def test_processor_rejects_missing_bridge() -> None:
    processor = BinanceUsdMCaptureProcessor()

    processor.accept_depth_snapshot(
        _snapshot_raw(),
        _snapshot(),
        received_at_ns=1,
    )

    with pytest.raises(
        BinanceUsdMCaptureError,
        match="skipped the required snapshot bridge",
    ):
        processor.accept_depth_update(
            _depth(
                first=101,
                final=105,
                previous=100,
            ),
            received_at_ns=2,
        )


def test_processor_validates_and_records_aggregate_trade() -> None:
    processor = BinanceUsdMCaptureProcessor()

    processor.accept_aggregate_trade(
        _trade(
            trade_id=1,
            maker=False,
        ),
        received_at_ns=1,
    )

    processor.accept_depth_update(
        _depth(
            first=99,
            final=102,
            previous=98,
        ),
        received_at_ns=2,
    )
    processor.accept_depth_snapshot(
        _snapshot_raw(),
        _snapshot(),
        received_at_ns=3,
    )

    result = processor.finalize()

    assert result.aggregate_trade_count == 1
    assert len(result.records) == 3
    assert tuple(record.sequence_number for record in result.records) == (0, 1, 2)


def test_processor_rejects_decreasing_receipt_timestamp() -> None:
    processor = BinanceUsdMCaptureProcessor()

    processor.accept_aggregate_trade(
        _trade(
            trade_id=1,
            maker=False,
        ),
        received_at_ns=10,
    )

    with pytest.raises(
        BinanceUsdMCaptureError,
        match="non-decreasing",
    ):
        processor.accept_aggregate_trade(
            _trade(
                trade_id=2,
                maker=True,
            ),
            received_at_ns=9,
        )


def test_processor_rejects_second_snapshot() -> None:
    processor = BinanceUsdMCaptureProcessor()

    processor.accept_depth_snapshot(
        _snapshot_raw(),
        _snapshot(),
        received_at_ns=1,
    )

    with pytest.raises(
        BinanceUsdMCaptureError,
        match="more than one depth snapshot",
    ):
        processor.accept_depth_snapshot(
            _snapshot_raw(),
            _snapshot(),
            received_at_ns=2,
        )


def test_finalize_requires_synchronized_book() -> None:
    processor = BinanceUsdMCaptureProcessor()

    processor.accept_aggregate_trade(
        _trade(
            trade_id=1,
            maker=False,
        ),
        received_at_ns=1,
    )

    with pytest.raises(
        BinanceUsdMCaptureError,
        match="did not obtain a depth snapshot",
    ):
        processor.finalize()


def test_processor_exposes_replayable_market_timelines() -> None:
    processor = BinanceUsdMCaptureProcessor()

    processor.accept_aggregate_trade(
        _trade(
            trade_id=1,
            maker=False,
        ),
        received_at_ns=1,
    )

    processor.accept_depth_update(
        _depth(
            first=99,
            final=102,
            previous=98,
        ),
        received_at_ns=2,
    )

    processor.accept_depth_snapshot(
        _snapshot_raw(),
        _snapshot(),
        received_at_ns=3,
    )

    processor.accept_depth_update(
        _depth(
            first=103,
            final=105,
            previous=102,
        ),
        received_at_ns=4,
    )

    result = processor.finalize()

    assert tuple(state.last_update_id for state in result.book_states) == (102, 105)

    assert len(result.aggregate_trades) == 1
    assert result.aggregate_trades[0].aggregate_trade_id == 1

    assert result.final_book_state == result.book_states[-1]


def test_smoke_duration_validation_paths() -> None:
    import abmforge_finance.study.binance_usdm_collector as collector

    with pytest.raises(
        TypeError,
        match="real number",
    ):
        collector._smoke_duration(True)

    with pytest.raises(
        collector.BinanceUsdMCaptureError,
        match=r"\(0, 60\]",
    ):
        collector._smoke_duration(0.0)

    with pytest.raises(
        collector.BinanceUsdMCaptureError,
        match=r"\(0, 60\]",
    ):
        collector._smoke_duration(60.1)

    assert collector._smoke_duration(5) == 5.0


def test_depth_reader_rejects_binary_frame() -> None:
    import asyncio

    import abmforge_finance.study.binance_usdm_collector as collector

    class BinaryWebSocket:
        async def recv(self) -> bytes:
            return b"not-text"

    processor = collector.BinanceUsdMCaptureProcessor()
    stop = asyncio.Event()

    with pytest.raises(
        BinanceUsdMNetworkError,
        match="depth WebSocket must deliver text frames",
    ):
        asyncio.run(
            collector._read_depth_stream(
                BinaryWebSocket(),
                processor,
                stop,
            )
        )


def test_trade_reader_rejects_binary_frame() -> None:
    import asyncio

    import abmforge_finance.study.binance_usdm_collector as collector

    class BinaryWebSocket:
        async def recv(self) -> bytes:
            return b"not-text"

    processor = collector.BinanceUsdMCaptureProcessor()
    stop = asyncio.Event()

    with pytest.raises(
        BinanceUsdMNetworkError,
        match="aggregate-trade WebSocket must deliver text frames",
    ):
        asyncio.run(
            collector._read_trade_stream(
                BinaryWebSocket(),
                processor,
                stop,
            )
        )


def test_live_smoke_orchestration_with_fake_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    import abmforge_finance.study.binance_usdm_collector as collector
    from abmforge_finance.study.binance_usdm_artifacts import (
        verify_binance_usdm_raw_capture,
    )
    from abmforge_finance.study.binance_usdm_contract import (
        binance_usdm_empirical_contract,
    )

    contract = binance_usdm_empirical_contract()

    class FakeWebSocket:
        def __init__(
            self,
            messages: list[str],
        ) -> None:
            self._messages = messages

        async def recv(self) -> str:
            if self._messages:
                return self._messages.pop(0)

            # The production reader wraps recv() in wait_for(0.25).
            # This await is therefore safely cancelled until stop is set.
            await asyncio.sleep(3600.0)
            return ""

    class FakeConnection:
        def __init__(
            self,
            websocket: FakeWebSocket,
        ) -> None:
            self._websocket = websocket

        async def __aenter__(
            self,
        ) -> FakeWebSocket:
            return self._websocket

        async def __aexit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> bool:
            return False

    depth_websocket = FakeWebSocket(
        [
            _depth(
                first=99,
                final=102,
                previous=98,
            ),
            _depth(
                first=103,
                final=105,
                previous=102,
                bid_quantity="8",
            ),
        ]
    )

    trade_websocket = FakeWebSocket(
        [
            _trade(
                trade_id=1,
                maker=False,
            )
        ]
    )

    def fake_connect(
        url: str,
        **options: object,
    ) -> FakeConnection:
        assert options["ping_interval"] is None
        assert options["ping_timeout"] is None

        if url == contract.depth_websocket_url:
            return FakeConnection(depth_websocket)

        if url == contract.aggregate_trade_websocket_url:
            return FakeConnection(trade_websocket)

        raise AssertionError(f"unexpected WebSocket URL: {url}")

    monkeypatch.setattr(
        collector,
        "load_websocket_connect",
        lambda: fake_connect,
    )

    monkeypatch.setattr(
        collector,
        "fetch_binance_usdm_exchange_info",
        lambda **kwargs: ("{}", object()),
    )

    monkeypatch.setattr(
        collector,
        "fetch_binance_usdm_depth_snapshot",
        lambda **kwargs: (
            _snapshot_raw(),
            _snapshot(),
        ),
    )

    tick = iter(
        range(
            1_000_000_000,
            1_000_001_000,
        )
    )

    monkeypatch.setattr(
        "abmforge_finance.study.binance_usdm_collector.time.time_ns",
        lambda: next(tick),
    )

    target = tmp_path / "fake-live-capture"

    result = asyncio.run(
        collector.capture_binance_usdm_smoke(
            target,
            repository_commit_sha="a" * 40,
            capture_id="fake-live-smoke",
            candidate_id="SMOKE_ONLY",
            duration_seconds=0.01,
            contract=contract,
        )
    )

    verify_binance_usdm_raw_capture(result.artifact_directory)

    assert result.artifact_directory == target
    assert result.depth_update_count == 2
    assert result.aggregate_trade_count == 1
    assert result.initial_snapshot_update_id == 100
    assert result.final_book_update_id == 105
    assert result.raw_record_count == 4


def test_collector_remaining_input_guards_v4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from typing import cast

    import abmforge_finance.study.binance_usdm_collector as collector
    from abmforge_finance.study.binance_usdm_artifacts import (
        BinanceUsdMRawChannel,
    )
    from abmforge_finance.study.binance_usdm_events import (
        BinanceUsdMDepthSnapshot,
    )

    processor = collector.BinanceUsdMCaptureProcessor()

    with pytest.raises(
        collector.BinanceUsdMCaptureError,
        match="received_at_ns",
    ):
        processor._record(
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=-1,
            raw_json="{}",
        )

    # RawRecord normally rejects malformed JSON first. Bypass only
    # persistence recording to exercise the collector's own
    # defense-in-depth parser.
    monkeypatch.setattr(
        collector.BinanceUsdMCaptureProcessor,
        "_record",
        lambda *args, **kwargs: None,
    )

    processor = collector.BinanceUsdMCaptureProcessor()

    with pytest.raises(
        collector.BinanceUsdMCaptureError,
        match="depth update contains invalid JSON",
    ):
        processor.accept_depth_update(
            "{",
            received_at_ns=1,
        )

    with pytest.raises(
        collector.BinanceUsdMCaptureError,
        match="depth update must contain a JSON object",
    ):
        processor.accept_depth_update(
            "[]",
            received_at_ns=1,
        )

    with pytest.raises(
        collector.BinanceUsdMCaptureError,
        match="aggregate trade contains invalid JSON",
    ):
        processor.accept_aggregate_trade(
            "{",
            received_at_ns=1,
        )

    with pytest.raises(
        collector.BinanceUsdMCaptureError,
        match="aggregate trade must contain a JSON object",
    ):
        processor.accept_aggregate_trade(
            "[]",
            received_at_ns=1,
        )

    with pytest.raises(
        TypeError,
        match="snapshot",
    ):
        processor.accept_depth_snapshot(
            "{}",
            cast(
                BinanceUsdMDepthSnapshot,
                object(),
            ),
            received_at_ns=1,
        )


def test_collector_snapshot_sync_failure_is_wrapped_v4() -> None:
    processor = BinanceUsdMCaptureProcessor()

    processor.accept_depth_update(
        _depth(
            first=99,
            final=102,
            previous=98,
        ),
        received_at_ns=1,
    )

    processor.accept_depth_update(
        _depth(
            first=103,
            final=105,
            previous=999,
        ),
        received_at_ns=2,
    )

    with pytest.raises(
        BinanceUsdMCaptureError,
        match="snapshot synchronization failed",
    ):
        processor.accept_depth_snapshot(
            _snapshot_raw(),
            _snapshot(),
            received_at_ns=3,
        )


def test_collector_finalize_requires_synchronized_book_v4() -> None:
    processor = BinanceUsdMCaptureProcessor()

    processor.accept_depth_snapshot(
        _snapshot_raw(),
        _snapshot(),
        received_at_ns=1,
    )

    with pytest.raises(
        BinanceUsdMCaptureError,
        match="never synchronized",
    ):
        processor.finalize()


def test_depth_reader_handles_asyncio_timeout_v5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    from typing import Any, cast

    import abmforge_finance.study.binance_usdm_collector as collector

    class IdleWebSocket:
        async def recv(self) -> str:
            return ""

    async def scenario() -> None:
        processor = collector.BinanceUsdMCaptureProcessor()
        stop = asyncio.Event()

        async def fake_wait_for(
            awaitable: object,
            *,
            timeout: float,
        ) -> object:
            assert timeout == 0.25

            coroutine = cast(Any, awaitable)
            coroutine.close()

            stop.set()
            raise asyncio.TimeoutError

        monkeypatch.setattr(
            asyncio,
            "wait_for",
            fake_wait_for,
        )

        await collector._read_depth_stream(
            IdleWebSocket(),
            processor,
            stop,
        )

    asyncio.run(scenario())


def test_trade_reader_handles_asyncio_timeout_v5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    from typing import Any, cast

    import abmforge_finance.study.binance_usdm_collector as collector

    class IdleWebSocket:
        async def recv(self) -> str:
            return ""

    async def scenario() -> None:
        processor = collector.BinanceUsdMCaptureProcessor()
        stop = asyncio.Event()

        async def fake_wait_for(
            awaitable: object,
            *,
            timeout: float,
        ) -> object:
            assert timeout == 0.25

            coroutine = cast(Any, awaitable)
            coroutine.close()

            stop.set()
            raise asyncio.TimeoutError

        monkeypatch.setattr(
            asyncio,
            "wait_for",
            fake_wait_for,
        )

        await collector._read_trade_stream(
            IdleWebSocket(),
            processor,
            stop,
        )

    asyncio.run(scenario())
