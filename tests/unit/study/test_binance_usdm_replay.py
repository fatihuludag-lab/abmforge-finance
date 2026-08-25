"""Tests for deterministic replay of Binance USD-M capture artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from abmforge_finance.exceptions import FinanceArtifactVerificationError
from abmforge_finance.study.binance_usdm_artifacts import (
    BinanceUsdMCaptureProvenance,
    BinanceUsdMRawChannel,
    BinanceUsdMRawRecord,
    write_binance_usdm_raw_capture,
)
from abmforge_finance.study.binance_usdm_replay import (
    read_binance_usdm_raw_capture,
    replay_binance_usdm_raw_capture,
)


def _records() -> tuple[BinanceUsdMRawRecord, ...]:
    depth_before_snapshot = json.dumps(
        {
            "e": "depthUpdate",
            "E": 1001,
            "T": 1000,
            "s": "BTCUSDT",
            "U": 99,
            "u": 102,
            "pu": 98,
            "b": [["100", "3"]],
            "a": [["101", "4"]],
            "ps": "BTCUSDT",
            "st": 1,
        },
        separators=(",", ":"),
    )

    snapshot = json.dumps(
        {
            "lastUpdateId": 100,
            "E": 1002,
            "T": 1001,
            "bids": [["100", "5"], ["99", "2"]],
            "asks": [["101", "6"], ["102", "3"]],
        },
        separators=(",", ":"),
    )

    trade = json.dumps(
        {
            "e": "aggTrade",
            "E": 1003,
            "s": "BTCUSDT",
            "a": 1,
            "p": "100.5",
            "q": "2",
            "nq": "2",
            "f": 10,
            "l": 10,
            "T": 1002,
            "m": False,
            "st": 1,
        },
        separators=(",", ":"),
    )

    depth_after_snapshot = json.dumps(
        {
            "e": "depthUpdate",
            "E": 1004,
            "T": 1003,
            "s": "BTCUSDT",
            "U": 103,
            "u": 105,
            "pu": 102,
            "b": [["100", "7"]],
            "a": [["101", "0"]],
            "ps": "BTCUSDT",
            "st": 1,
        },
        separators=(",", ":"),
    )

    return (
        BinanceUsdMRawRecord(
            sequence_number=0,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=1,
            raw_json=depth_before_snapshot,
        ),
        BinanceUsdMRawRecord(
            sequence_number=1,
            channel=BinanceUsdMRawChannel.DEPTH_SNAPSHOT,
            received_at_ns=2,
            raw_json=snapshot,
        ),
        BinanceUsdMRawRecord(
            sequence_number=2,
            channel=BinanceUsdMRawChannel.AGGREGATE_TRADE,
            received_at_ns=3,
            raw_json=trade,
        ),
        BinanceUsdMRawRecord(
            sequence_number=3,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=4,
            raw_json=depth_after_snapshot,
        ),
    )


def _write(tmp_path: Path) -> Path:
    return write_binance_usdm_raw_capture(
        _records(),
        tmp_path / "capture",
        provenance=BinanceUsdMCaptureProvenance(
            capture_id="replay-test",
            candidate_id="SMOKE_ONLY",
            repository_commit_sha="a" * 40,
            started_at_ns=1,
            ended_at_ns=10,
        ),
    )


def test_reader_restores_global_sequence_order(
    tmp_path: Path,
) -> None:
    target = _write(tmp_path)

    records = read_binance_usdm_raw_capture(target)

    assert tuple(record.sequence_number for record in records) == (0, 1, 2, 3)

    assert tuple(record.channel for record in records) == (
        BinanceUsdMRawChannel.DEPTH_UPDATE,
        BinanceUsdMRawChannel.DEPTH_SNAPSHOT,
        BinanceUsdMRawChannel.AGGREGATE_TRADE,
        BinanceUsdMRawChannel.DEPTH_UPDATE,
    )


def test_replay_reconstructs_final_book(
    tmp_path: Path,
) -> None:
    target = _write(tmp_path)

    result = replay_binance_usdm_raw_capture(target)

    assert result.depth_update_count == 2
    assert result.aggregate_trade_count == 1

    assert result.final_book_state.last_update_id == 105
    assert str(result.final_book_state.best_bid) == "100"
    assert str(result.final_book_state.best_ask) == "102"


def test_replay_is_deterministic(
    tmp_path: Path,
) -> None:
    target = _write(tmp_path)

    first = replay_binance_usdm_raw_capture(target)
    second = replay_binance_usdm_raw_capture(target)

    assert first == second


def test_interval_reconstruction_excludes_partial_opening_second(
    tmp_path: Path,
) -> None:
    target = _write(tmp_path)

    from abmforge_finance.study.binance_usdm_replay import (
        reconstruct_binance_usdm_empirical_intervals,
    )

    # The synthetic fixture is intentionally too short after readiness
    # to contain a complete accepted UTC second.
    with pytest.raises(
        FinanceArtifactVerificationError,
        match="complete empirical second",
    ):
        reconstruct_binance_usdm_empirical_intervals(target)
