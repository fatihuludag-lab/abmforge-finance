"""Tests for the Binance USD-M live-capture processor."""

from __future__ import annotations

import json

import pytest

from abmforge_finance.study.binance_usdm_collector import (
    BinanceUsdMCaptureError,
    BinanceUsdMCaptureProcessor,
)
from abmforge_finance.study.binance_usdm_events import (
    BinanceUsdMDepthSnapshot,
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
