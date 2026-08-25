"""Tests for immutable Binance USD-M raw capture artifacts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from abmforge_finance.exceptions import (
    FinanceArtifactExistsError,
    FinanceArtifactVerificationError,
    InvalidFinanceArtifactError,
)
from abmforge_finance.study.binance_usdm_artifacts import (
    BINANCE_USDM_RAW_CAPTURE_SCHEMA_VERSION,
    BinanceUsdMCaptureProvenance,
    BinanceUsdMRawChannel,
    BinanceUsdMRawRecord,
    verify_binance_usdm_raw_capture,
    write_binance_usdm_raw_capture,
)

_GIT_SHA = "a" * 40


def _provenance() -> BinanceUsdMCaptureProvenance:
    return BinanceUsdMCaptureProvenance(
        capture_id="capture-000",
        candidate_id="candidate-000",
        repository_commit_sha=_GIT_SHA,
        started_at_ns=1_000,
        ended_at_ns=10_000,
    )


def _records() -> tuple[BinanceUsdMRawRecord, ...]:
    return (
        BinanceUsdMRawRecord(
            sequence_number=0,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=2_000,
            raw_json='{"e":"depthUpdate","u":100}',
        ),
        BinanceUsdMRawRecord(
            sequence_number=1,
            channel=BinanceUsdMRawChannel.DEPTH_SNAPSHOT,
            received_at_ns=3_000,
            raw_json=' { "lastUpdateId" : 100 } ',
        ),
        BinanceUsdMRawRecord(
            sequence_number=2,
            channel=BinanceUsdMRawChannel.AGGREGATE_TRADE,
            received_at_ns=4_000,
            raw_json='{"e":"aggTrade","a":1}',
        ),
        BinanceUsdMRawRecord(
            sequence_number=3,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=5_000,
            raw_json='{"e":"depthUpdate","u":101}',
        ),
    )


def test_raw_record_preserves_exact_json_text() -> None:
    record = _records()[1]

    assert record.raw_json == (' { "lastUpdateId" : 100 } ')


def test_raw_record_rejects_invalid_json() -> None:
    with pytest.raises(
        InvalidFinanceArtifactError,
        match="valid JSON",
    ):
        BinanceUsdMRawRecord(
            sequence_number=0,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=1,
            raw_json="{bad",
        )


def test_raw_record_requires_json_object() -> None:
    with pytest.raises(
        InvalidFinanceArtifactError,
        match="JSON object",
    ):
        BinanceUsdMRawRecord(
            sequence_number=0,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=1,
            raw_json="[1,2,3]",
        )


def test_capture_provenance_requires_full_git_sha() -> None:
    with pytest.raises(
        InvalidFinanceArtifactError,
        match="40-character",
    ):
        BinanceUsdMCaptureProvenance(
            capture_id="capture",
            candidate_id="candidate",
            repository_commit_sha="abc123",
            started_at_ns=1,
            ended_at_ns=2,
        )


def test_writer_creates_canonical_hashed_capture(
    tmp_path: Path,
) -> None:
    target = tmp_path / "capture"

    result = write_binance_usdm_raw_capture(
        _records(),
        target,
        provenance=_provenance(),
    )

    assert result == target

    assert {path.name for path in target.iterdir()} == {
        "manifest.json",
        "depth_snapshot.jsonl",
        "depth_updates.jsonl",
        "aggregate_trades.jsonl",
    }

    verify_binance_usdm_raw_capture(target)

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["artifact_schema_version"] == (BINANCE_USDM_RAW_CAPTURE_SCHEMA_VERSION)
    assert manifest["record_count"] == 4

    assert manifest["contract"]["symbol"] == "BTCUSDT"

    assert manifest["provenance"]["repository_commit_sha"] == _GIT_SHA


def test_writer_preserves_exact_raw_payload(
    tmp_path: Path,
) -> None:
    target = write_binance_usdm_raw_capture(
        _records(),
        tmp_path / "capture",
        provenance=_provenance(),
    )

    lines = (target / "depth_snapshot.jsonl").read_text(encoding="utf-8").splitlines()

    assert len(lines) == 1

    value = json.loads(lines[0])

    assert value["raw_json"] == (' { "lastUpdateId" : 100 } ')


def test_same_capture_inputs_are_byte_deterministic(
    tmp_path: Path,
) -> None:
    first = write_binance_usdm_raw_capture(
        _records(),
        tmp_path / "first",
        provenance=_provenance(),
    )

    second = write_binance_usdm_raw_capture(
        _records(),
        tmp_path / "second",
        provenance=_provenance(),
    )

    names = (
        "manifest.json",
        "depth_snapshot.jsonl",
        "depth_updates.jsonl",
        "aggregate_trades.jsonl",
    )

    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_writer_refuses_existing_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "capture"

    write_binance_usdm_raw_capture(
        _records(),
        target,
        provenance=_provenance(),
    )

    with pytest.raises(
        FinanceArtifactExistsError,
        match="already exists",
    ):
        write_binance_usdm_raw_capture(
            _records(),
            target,
            provenance=_provenance(),
        )


def test_writer_requires_exactly_one_snapshot(
    tmp_path: Path,
) -> None:
    records = tuple(
        record
        for record in _records()
        if record.channel is not BinanceUsdMRawChannel.DEPTH_SNAPSHOT
    )

    with pytest.raises(
        InvalidFinanceArtifactError,
        match="exactly one depth snapshot",
    ):
        write_binance_usdm_raw_capture(
            records,
            tmp_path / "capture",
            provenance=_provenance(),
        )


def test_writer_rejects_duplicate_or_reversed_sequence() -> None:
    records = list(_records())

    records[2] = BinanceUsdMRawRecord(
        sequence_number=1,
        channel=BinanceUsdMRawChannel.AGGREGATE_TRADE,
        received_at_ns=4_000,
        raw_json='{"e":"aggTrade","a":1}',
    )

    with pytest.raises(
        InvalidFinanceArtifactError,
        match="sequence numbers must increase strictly",
    ):
        write_binance_usdm_raw_capture(
            tuple(records),
            "unused",
            provenance=_provenance(),
        )


def test_writer_rejects_decreasing_receipt_time() -> None:
    records = list(_records())

    records[2] = BinanceUsdMRawRecord(
        sequence_number=2,
        channel=BinanceUsdMRawChannel.AGGREGATE_TRADE,
        received_at_ns=1_000,
        raw_json='{"e":"aggTrade","a":1}',
    )

    with pytest.raises(
        InvalidFinanceArtifactError,
        match="receipt timestamps must be non-decreasing",
    ):
        write_binance_usdm_raw_capture(
            tuple(records),
            "unused",
            provenance=_provenance(),
        )


def test_verifier_detects_raw_file_tampering(
    tmp_path: Path,
) -> None:
    target = write_binance_usdm_raw_capture(
        _records(),
        tmp_path / "capture",
        provenance=_provenance(),
    )

    path = target / "depth_updates.jsonl"

    path.write_bytes(path.read_bytes() + b"tampered\n")

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="integrity failure",
    ):
        verify_binance_usdm_raw_capture(target)


def test_verifier_rejects_extra_file(
    tmp_path: Path,
) -> None:
    target = write_binance_usdm_raw_capture(
        _records(),
        tmp_path / "capture",
        provenance=_provenance(),
    )

    (target / "extra.txt").write_text(
        "unexpected",
        encoding="utf-8",
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="membership",
    ):
        verify_binance_usdm_raw_capture(target)
