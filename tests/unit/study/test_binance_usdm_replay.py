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


def test_reconstruction_success_path_v2(
    tmp_path: Path,
) -> None:
    from abmforge_finance.study.binance_usdm_replay import (
        reconstruct_binance_usdm_empirical_intervals,
    )

    def depth(
        *,
        first: int,
        final: int,
        previous: int,
        transaction_time_ms: int,
        bid: str,
        ask: str,
        remove_bid: str | None = None,
        remove_ask: str | None = None,
    ) -> str:
        bid_updates: list[list[str]] = []
        ask_updates: list[list[str]] = []

        if remove_bid is not None:
            bid_updates.append([remove_bid, "0"])

        bid_updates.append([bid, "5"])

        if remove_ask is not None:
            ask_updates.append([remove_ask, "0"])

        ask_updates.append([ask, "6"])

        return json.dumps(
            {
                "e": "depthUpdate",
                "E": transaction_time_ms + 1,
                "T": transaction_time_ms,
                "s": "BTCUSDT",
                "U": first,
                "u": final,
                "pu": previous,
                "b": bid_updates,
                "a": ask_updates,
                "ps": "BTCUSDT",
                "st": 1,
            },
            separators=(",", ":"),
        )

    def trade(
        *,
        trade_id: int,
        trade_time_ms: int,
        maker: bool,
    ) -> str:
        return json.dumps(
            {
                "e": "aggTrade",
                "E": trade_time_ms + 1,
                "s": "BTCUSDT",
                "a": trade_id,
                "p": "100.5",
                "q": "2",
                "nq": "2",
                "f": trade_id,
                "l": trade_id,
                "T": trade_time_ms,
                "m": maker,
                "st": 1,
            },
            separators=(",", ":"),
        )

    snapshot = json.dumps(
        {
            "lastUpdateId": 100,
            "E": 10_050,
            "T": 10_049,
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

    records = (
        BinanceUsdMRawRecord(
            sequence_number=0,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=1,
            raw_json=depth(
                first=99,
                final=102,
                previous=98,
                transaction_time_ms=10_100,
                bid="100",
                ask="101",
            ),
        ),
        BinanceUsdMRawRecord(
            sequence_number=1,
            channel=BinanceUsdMRawChannel.AGGREGATE_TRADE,
            received_at_ns=2,
            raw_json=trade(
                trade_id=1,
                trade_time_ms=10_200,
                maker=False,
            ),
        ),
        BinanceUsdMRawRecord(
            sequence_number=2,
            channel=BinanceUsdMRawChannel.DEPTH_SNAPSHOT,
            received_at_ns=3,
            raw_json=snapshot,
        ),
        BinanceUsdMRawRecord(
            sequence_number=3,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=4,
            raw_json=depth(
                first=103,
                final=105,
                previous=102,
                transaction_time_ms=11_500,
                bid="101",
                ask="102",
                remove_bid="100",
                remove_ask="101",
            ),
        ),
        BinanceUsdMRawRecord(
            sequence_number=4,
            channel=BinanceUsdMRawChannel.AGGREGATE_TRADE,
            received_at_ns=5,
            raw_json=trade(
                trade_id=2,
                trade_time_ms=11_600,
                maker=True,
            ),
        ),
        BinanceUsdMRawRecord(
            sequence_number=5,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=6,
            raw_json=depth(
                first=106,
                final=108,
                previous=105,
                transaction_time_ms=13_100,
                bid="102",
                ask="103",
                remove_bid="101",
                remove_ask="102",
            ),
        ),
    )

    target = write_binance_usdm_raw_capture(
        records,
        tmp_path / "long-capture",
        provenance=BinanceUsdMCaptureProvenance(
            capture_id="reconstruction-success",
            candidate_id="PILOT_ONLY",
            repository_commit_sha="b" * 40,
            started_at_ns=1,
            ended_at_ns=100,
        ),
    )

    intervals = reconstruct_binance_usdm_empirical_intervals(target)

    assert len(intervals) == 2

    assert intervals[0].start_timestamp_ns == 11_000_000_000
    assert intervals[-1].end_timestamp_ns == 13_000_000_000

    assert intervals[0].mid_price == pytest.approx(101.5)
    assert intervals[0].aggressor_flow == pytest.approx(-1.0)

    # No depth event occurs in [12s, 13s), so the synchronized
    # 101/102 book state persists across that quiet interval.
    assert intervals[1].mid_price == pytest.approx(101.5)
    assert intervals[1].aggressor_flow == 0.0


def test_replay_channel_loader_validation_edges_v4(
    tmp_path: Path,
) -> None:
    import abmforge_finance.study.binance_usdm_replay as replay
    from abmforge_finance.exceptions import (
        FinanceArtifactVerificationError,
    )

    path = tmp_path / "depth_updates.jsonl"

    path.write_text(
        "[]\n",
        encoding="utf-8",
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="row must contain an object",
    ):
        replay._load_channel(
            tmp_path,
            BinanceUsdMRawChannel.DEPTH_UPDATE,
        )

    path.write_text(
        '{"sequence_number":0}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="missing required metadata",
    ):
        replay._load_channel(
            tmp_path,
            BinanceUsdMRawChannel.DEPTH_UPDATE,
        )


def test_replay_defense_in_depth_channel_guards_v4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import abmforge_finance.study.binance_usdm_replay as replay
    from abmforge_finance.exceptions import (
        FinanceArtifactVerificationError,
    )

    snapshot_record = BinanceUsdMRawRecord(
        sequence_number=0,
        channel=BinanceUsdMRawChannel.DEPTH_SNAPSHOT,
        received_at_ns=1,
        raw_json="{}",
    )

    object.__setattr__(
        snapshot_record,
        "raw_json",
        "[]",
    )

    monkeypatch.setattr(
        replay,
        "read_binance_usdm_raw_capture",
        lambda directory: (snapshot_record,),
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="snapshot raw payload",
    ):
        replay.replay_binance_usdm_raw_capture("unused")

    unsupported = BinanceUsdMRawRecord(
        sequence_number=0,
        channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
        received_at_ns=1,
        raw_json="{}",
    )

    object.__setattr__(
        unsupported,
        "channel",
        "unsupported",
    )

    monkeypatch.setattr(
        replay,
        "read_binance_usdm_raw_capture",
        lambda directory: (unsupported,),
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="unsupported raw channel",
    ):
        replay.replay_binance_usdm_raw_capture("unused")


def test_reconstruction_readiness_guards_v4(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import abmforge_finance.study.binance_usdm_replay as replay
    from abmforge_finance.exceptions import (
        FinanceArtifactVerificationError,
    )

    monkeypatch.setattr(
        replay,
        "replay_binance_usdm_raw_capture",
        lambda directory: SimpleNamespace(
            book_states=(),
            aggregate_trades=(object(),),
        ),
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="no synchronized book-state timeline",
    ):
        replay.reconstruct_binance_usdm_empirical_intervals("unused")

    monkeypatch.setattr(
        replay,
        "replay_binance_usdm_raw_capture",
        lambda directory: SimpleNamespace(
            book_states=(object(),),
            aggregate_trades=(),
        ),
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="no aggregate trade",
    ):
        replay.reconstruct_binance_usdm_empirical_intervals("unused")
