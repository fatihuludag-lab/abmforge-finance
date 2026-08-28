"""Tests for official Binance USD-M reference-set orchestration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest

import abmforge_finance.study.binance_usdm_reference as reference
from abmforge_finance.exceptions import InvalidMetricInputError
from abmforge_finance.study.binance_usdm_blocks import (
    BinanceUsdMEmpiricalBlockRejectionReason,
    BinanceUsdMEmpiricalBlockResult,
    BinanceUsdMEmpiricalBlockStatus,
)
from abmforge_finance.study.binance_usdm_collector import (
    BinanceUsdMCandidateCaptureResult,
)
from abmforge_finance.study.binance_usdm_contract import (
    binance_usdm_empirical_contract,
)
from abmforge_finance.study.stylized_empirical import (
    EmpiricalMarketInterval,
)


def _rejected_block(
    *,
    candidate_id: str = "candidate-1",
    source_id: str = "source-1",
) -> BinanceUsdMEmpiricalBlockResult:
    return BinanceUsdMEmpiricalBlockResult(
        candidate_id=candidate_id,
        source_id=source_id,
        status=(BinanceUsdMEmpiricalBlockStatus.REJECTED),
        rejection_reason=(BinanceUsdMEmpiricalBlockRejectionReason.WRONG_INTERVAL_COUNT),
        rejection_detail="wrong count",
        raw_interval_count=0,
        canonical_observation_count=0,
        raw_start_timestamp_ns=None,
        raw_end_timestamp_ns=None,
        analysis_start_timestamp_ns=None,
        analysis_end_timestamp_ns=None,
        prepared_sample=None,
    )


def test_reference_evaluator_selects_first_4097_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = binance_usdm_empirical_contract()

    fake_intervals = cast(
        tuple[
            EmpiricalMarketInterval,
            ...,
        ],
        tuple(object() for _ in range(contract.block_observation_count + 100)),
    )

    observed: dict[str, object] = {}

    monkeypatch.setattr(
        reference,
        "verify_binance_usdm_raw_capture",
        lambda directory: None,
    )

    monkeypatch.setattr(
        reference,
        "reconstruct_binance_usdm_empirical_intervals_streaming",
        lambda directory: fake_intervals,
    )

    def fake_evaluate(
        **kwargs: Any,
    ) -> BinanceUsdMEmpiricalBlockResult:
        rows = kwargs["intervals"]
        observed["rows"] = rows

        return _rejected_block(
            candidate_id=(kwargs["candidate_id"]),
            source_id=(kwargs["source_id"]),
        )

    monkeypatch.setattr(
        reference,
        "evaluate_binance_usdm_empirical_block",
        fake_evaluate,
    )

    evaluation = reference.evaluate_binance_usdm_reference_artifact(
        tmp_path,
        candidate_id="candidate-1",
        source_id="source-1",
        contract=contract,
    )

    expected = contract.block_observation_count + 1

    assert evaluation.reconstructed_interval_count == len(fake_intervals)

    assert evaluation.selected_interval_count == expected

    rows = observed["rows"]

    assert isinstance(
        rows,
        tuple,
    )

    assert len(rows) == expected

    assert rows == fake_intervals[:expected]


def test_reference_registry_rejects_duplicate_candidate(
    tmp_path: Path,
) -> None:
    record = reference.BinanceUsdMReferenceCandidateRecord(
        candidate_id="candidate-1",
        capture_id="capture-1",
        repository_commit_sha="a" * 40,
        source_id="source-1",
        outcome=(reference.BinanceUsdMReferenceCandidateOutcome.REJECTED),
        artifact_directory="raw",
        artifact_manifest_sha256="b" * 64,
        capture_started_at_ns=1,
        capture_ended_at_ns=2,
        reconstructed_interval_count=1,
        selected_interval_count=1,
        block_status=(BinanceUsdMEmpiricalBlockStatus.REJECTED),
        rejection_reason=(BinanceUsdMEmpiricalBlockRejectionReason.WRONG_INTERVAL_COUNT),
        rejection_detail="wrong count",
        raw_interval_count=1,
        canonical_observation_count=0,
        raw_start_timestamp_ns=0,
        raw_end_timestamp_ns=1,
        analysis_start_timestamp_ns=None,
        analysis_end_timestamp_ns=None,
        failure_type=None,
        failure_detail=None,
    )

    registry = tmp_path / "registry.jsonl"

    reference.append_binance_usdm_reference_registry(
        record,
        registry,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="candidate_id already exists",
    ):
        reference.append_binance_usdm_reference_registry(
            record,
            registry,
        )


def test_capture_failure_is_persisted_without_block_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_capture(
        *args: object,
        **kwargs: object,
    ) -> BinanceUsdMCandidateCaptureResult:
        raise RuntimeError("forced transport failure")

    monkeypatch.setattr(
        reference,
        "capture_binance_usdm_candidate",
        fail_capture,
    )

    candidate = tmp_path / "candidate-0001"

    registry = tmp_path / "registry.jsonl"

    record = asyncio.run(
        reference.run_binance_usdm_reference_candidate(
            candidate,
            repository_commit_sha="a" * 40,
            candidate_id="candidate-0001",
            capture_id="capture-0001",
            registry_path=registry,
        )
    )

    assert record.outcome is reference.BinanceUsdMReferenceCandidateOutcome.CAPTURE_FAILED

    assert record.block_status is None
    assert record.failure_type == "RuntimeError"

    result = json.loads((candidate / "candidate-result.json").read_text(encoding="utf-8"))

    assert result["outcome"] == "capture-failed"

    registry_rows = registry.read_text(encoding="utf-8").splitlines()

    assert len(registry_rows) == 1


def _registry_record(
    *,
    candidate_id: str,
    capture_id: str,
    capture_started_at_ns: int,
    outcome: reference.BinanceUsdMReferenceCandidateOutcome = (
        reference.BinanceUsdMReferenceCandidateOutcome.REJECTED
    ),
    analysis_start_timestamp_ns: int | None = None,
    analysis_end_timestamp_ns: int | None = None,
) -> reference.BinanceUsdMReferenceCandidateRecord:
    is_valid = outcome is reference.BinanceUsdMReferenceCandidateOutcome.VALID

    return reference.BinanceUsdMReferenceCandidateRecord(
        candidate_id=candidate_id,
        capture_id=capture_id,
        repository_commit_sha="a" * 40,
        source_id=f"source:{candidate_id}",
        outcome=outcome,
        artifact_directory="raw",
        artifact_manifest_sha256="b" * 64,
        capture_started_at_ns=capture_started_at_ns,
        capture_ended_at_ns=(capture_started_at_ns + 1),
        reconstructed_interval_count=4097,
        selected_interval_count=4097,
        block_status=(
            BinanceUsdMEmpiricalBlockStatus.VALID
            if is_valid
            else BinanceUsdMEmpiricalBlockStatus.REJECTED
        ),
        rejection_reason=(
            None if is_valid else BinanceUsdMEmpiricalBlockRejectionReason.WRONG_INTERVAL_COUNT
        ),
        rejection_detail=(None if is_valid else "wrong count"),
        raw_interval_count=(4097 if is_valid else 1),
        canonical_observation_count=(4096 if is_valid else 0),
        raw_start_timestamp_ns=(analysis_start_timestamp_ns),
        raw_end_timestamp_ns=(analysis_end_timestamp_ns),
        analysis_start_timestamp_ns=(analysis_start_timestamp_ns),
        analysis_end_timestamp_ns=(analysis_end_timestamp_ns),
        failure_type=None,
        failure_detail=None,
    )


def test_registry_rejects_duplicate_capture_id(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-0001",
        capture_id="capture-0001",
        capture_started_at_ns=1,
    )

    reference.append_binance_usdm_reference_registry(
        first,
        registry,
    )

    second = replace(
        first,
        candidate_id="candidate-0002",
        source_id="source:candidate-0002",
        capture_started_at_ns=2,
        capture_ended_at_ns=3,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="capture_id already exists",
    ):
        reference.append_binance_usdm_reference_registry(
            second,
            registry,
        )


def test_registry_requires_strict_capture_order(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-0001",
        capture_id="capture-0001",
        capture_started_at_ns=100,
    )

    reference.append_binance_usdm_reference_registry(
        first,
        registry,
    )

    second = _registry_record(
        candidate_id="candidate-0002",
        capture_id="capture-0002",
        capture_started_at_ns=100,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="capture start must increase strictly",
    ):
        reference.append_binance_usdm_reference_registry(
            second,
            registry,
        )


def test_valid_reference_blocks_must_not_overlap(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-0001",
        capture_id="capture-0001",
        capture_started_at_ns=1,
        outcome=(reference.BinanceUsdMReferenceCandidateOutcome.VALID),
        analysis_start_timestamp_ns=100,
        analysis_end_timestamp_ns=200,
    )

    reference.append_binance_usdm_reference_registry(
        first,
        registry,
    )

    overlapping = _registry_record(
        candidate_id="candidate-0002",
        capture_id="capture-0002",
        capture_started_at_ns=2,
        outcome=(reference.BinanceUsdMReferenceCandidateOutcome.VALID),
        analysis_start_timestamp_ns=199,
        analysis_end_timestamp_ns=299,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="must not overlap",
    ):
        reference.append_binance_usdm_reference_registry(
            overlapping,
            registry,
        )

    adjacent = _registry_record(
        candidate_id="candidate-0003",
        capture_id="capture-0003",
        capture_started_at_ns=2,
        outcome=(reference.BinanceUsdMReferenceCandidateOutcome.VALID),
        analysis_start_timestamp_ns=200,
        analysis_end_timestamp_ns=300,
    )

    reference.append_binance_usdm_reference_registry(
        adjacent,
        registry,
    )

    assert len(registry.read_text(encoding="utf-8").splitlines()) == 2


def test_registry_rejects_noncanonical_jsonl(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-0001",
        capture_id="capture-0001",
        capture_started_at_ns=1,
    )

    registry.write_text(
        json.dumps(
            first.to_mapping(),
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    second = _registry_record(
        candidate_id="candidate-0002",
        capture_id="capture-0002",
        capture_started_at_ns=2,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="not canonical JSONL",
    ):
        reference.append_binance_usdm_reference_registry(
            second,
            registry,
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        (
            b"{not-json}\n",
            "contains invalid JSON",
        ),
        (
            b"[]\n",
            "rows must be objects",
        ),
    ),
)
def test_registry_rejects_structurally_invalid_rows(
    tmp_path: Path,
    payload: bytes,
    message: str,
) -> None:
    registry = tmp_path / "registry.jsonl"
    registry.write_bytes(payload)

    record = _registry_record(
        candidate_id="candidate-0002",
        capture_id="capture-0002",
        capture_started_at_ns=2,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match=message,
    ):
        reference.append_binance_usdm_reference_registry(
            record,
            registry,
        )


def test_registry_rejects_schema_drift(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-0001",
        capture_id="capture-0001",
        capture_started_at_ns=1,
    )

    mapping = first.to_mapping()
    mapping["schema_version"] = "future-schema"

    registry.write_bytes(reference._canonical_json_bytes(mapping))

    second = _registry_record(
        candidate_id="candidate-0002",
        capture_id="capture-0002",
        capture_started_at_ns=2,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="schema mismatch",
    ):
        reference.append_binance_usdm_reference_registry(
            second,
            registry,
        )


def test_candidate_result_is_immutable_once_written(
    tmp_path: Path,
) -> None:
    record = _registry_record(
        candidate_id="candidate-0001",
        capture_id="capture-0001",
        capture_started_at_ns=1,
    )

    target = tmp_path / "candidate-result.json"

    reference.write_binance_usdm_reference_candidate_result(
        record,
        target,
    )

    original = target.read_bytes()

    with pytest.raises(
        InvalidMetricInputError,
        match="already exists",
    ):
        reference.write_binance_usdm_reference_candidate_result(
            record,
            target,
        )

    assert target.read_bytes() == original


def test_registry_append_produces_canonical_jsonl(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-0001",
        capture_id="capture-0001",
        capture_started_at_ns=1,
    )

    second = _registry_record(
        candidate_id="candidate-0002",
        capture_id="capture-0002",
        capture_started_at_ns=2,
    )

    reference.append_binance_usdm_reference_registry(
        first,
        registry,
    )

    reference.append_binance_usdm_reference_registry(
        second,
        registry,
    )

    raw = registry.read_bytes()

    assert raw.endswith(b"\n")

    rows = raw.splitlines()

    assert len(rows) == 2

    for row in rows:
        value = json.loads(row)
        assert isinstance(value, dict)

        assert reference._canonical_json_bytes(value).rstrip(b"\n") == row


def test_manifest_sha256_hashes_exact_bytes_v5(
    tmp_path: Path,
) -> None:
    import hashlib

    artifact = tmp_path / "artifact"
    artifact.mkdir()

    payload = b'{"schema":"test"}\n'

    (artifact / "manifest.json").write_bytes(payload)

    assert reference._manifest_sha256(artifact) == hashlib.sha256(payload).hexdigest()


def test_reference_evaluator_converts_integrity_failure_v5(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from abmforge_finance.exceptions import (
        FinanceArtifactVerificationError,
    )

    artifact = tmp_path / "artifact"
    artifact.mkdir()

    (artifact / "manifest.json").write_bytes(b'{"manifest":"present"}\n')

    observed: dict[str, object] = {}

    def fail_verify(
        directory: object,
    ) -> None:
        raise FinanceArtifactVerificationError("forced corruption")

    def fake_evaluate(
        **kwargs: Any,
    ) -> BinanceUsdMEmpiricalBlockResult:
        observed.update(kwargs)

        return _rejected_block(
            candidate_id=(kwargs["candidate_id"]),
            source_id=(kwargs["source_id"]),
        )

    monkeypatch.setattr(
        reference,
        "verify_binance_usdm_raw_capture",
        fail_verify,
    )

    monkeypatch.setattr(
        reference,
        "evaluate_binance_usdm_empirical_block",
        fake_evaluate,
    )

    result = reference.evaluate_binance_usdm_reference_artifact(
        artifact,
        candidate_id="candidate-1",
        source_id="source-1",
    )

    assert result.reconstructed_interval_count == 0

    assert result.selected_interval_count == 0

    assert observed["intervals"] == ()

    failure = observed["source_integrity_failure"]

    assert isinstance(failure, str)

    assert "FinanceArtifactVerificationError" in failure

    assert "forced corruption" in failure


def test_record_from_evaluation_maps_both_outcomes_v5(
    tmp_path: Path,
) -> None:
    from types import SimpleNamespace

    capture = BinanceUsdMCandidateCaptureResult(
        artifact_directory=(tmp_path / "raw"),
        capture_id="capture-1",
        candidate_id="candidate-1",
        raw_record_count=10,
        depth_update_count=5,
        aggregate_trade_count=4,
        initial_snapshot_update_id=1,
        final_book_update_id=2,
        final_best_bid="100",
        final_best_ask="101",
        started_at_ns=10,
        ended_at_ns=20,
    )

    rejected_evaluation = reference.BinanceUsdMReferenceCandidateEvaluation(
        artifact_directory=(tmp_path / "raw"),
        artifact_manifest_sha256=("b" * 64),
        reconstructed_interval_count=1,
        selected_interval_count=1,
        block_result=_rejected_block(
            candidate_id="candidate-1",
            source_id="source-1",
        ),
    )

    rejected = reference._record_from_evaluation(
        capture=capture,
        evaluation=rejected_evaluation,
        repository_commit_sha=("a" * 40),
        source_id="source-1",
    )

    assert rejected.outcome is reference.BinanceUsdMReferenceCandidateOutcome.REJECTED

    valid_block = SimpleNamespace(
        is_valid=True,
        status=(BinanceUsdMEmpiricalBlockStatus.VALID),
        rejection_reason=None,
        rejection_detail=None,
        raw_interval_count=4097,
        canonical_observation_count=4096,
        raw_start_timestamp_ns=100,
        raw_end_timestamp_ns=200,
        analysis_start_timestamp_ns=101,
        analysis_end_timestamp_ns=200,
    )

    valid_evaluation = reference.BinanceUsdMReferenceCandidateEvaluation(
        artifact_directory=(tmp_path / "raw"),
        artifact_manifest_sha256=("b" * 64),
        reconstructed_interval_count=4097,
        selected_interval_count=4097,
        block_result=cast(
            BinanceUsdMEmpiricalBlockResult,
            valid_block,
        ),
    )

    valid = reference._record_from_evaluation(
        capture=capture,
        evaluation=valid_evaluation,
        repository_commit_sha="a" * 40,
        source_id="source-1",
    )

    assert valid.outcome is reference.BinanceUsdMReferenceCandidateOutcome.VALID

    assert valid.canonical_observation_count == 4096


def _write_registry_mapping_v5(
    path: Path,
    mapping: dict[str, object],
) -> None:
    path.write_bytes(reference._canonical_json_bytes(mapping))


def test_registry_rejects_missing_terminal_newline_v5(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-1",
        capture_id="capture-1",
        capture_started_at_ns=1,
    )

    registry.write_bytes(reference._canonical_json_bytes(first.to_mapping()).rstrip(b"\n"))

    second = _registry_record(
        candidate_id="candidate-2",
        capture_id="capture-2",
        capture_started_at_ns=2,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="not canonical JSONL",
    ):
        reference.append_binance_usdm_reference_registry(
            second,
            registry,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        (
            "candidate_id",
            123,
            "candidate_id is invalid",
        ),
        (
            "capture_id",
            123,
            "capture_id is invalid",
        ),
        (
            "capture",
            "bad",
            "capture metadata is invalid",
        ),
    ),
)
def test_registry_rejects_invalid_existing_metadata_v5(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-1",
        capture_id="capture-1",
        capture_started_at_ns=1,
    )

    mapping = first.to_mapping()
    mapping[field] = value

    _write_registry_mapping_v5(
        registry,
        mapping,
    )

    second = _registry_record(
        candidate_id="candidate-2",
        capture_id="capture-2",
        capture_started_at_ns=2,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match=message,
    ):
        reference.append_binance_usdm_reference_registry(
            second,
            registry,
        )


def test_registry_rejects_invalid_existing_capture_start_v5(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-1",
        capture_id="capture-1",
        capture_started_at_ns=1,
    )

    mapping = first.to_mapping()

    capture = mapping["capture"]
    assert isinstance(capture, dict)

    capture["started_at_ns"] = True

    _write_registry_mapping_v5(
        registry,
        mapping,
    )

    second = _registry_record(
        candidate_id="candidate-2",
        capture_id="capture-2",
        capture_started_at_ns=2,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="capture start is invalid",
    ):
        reference.append_binance_usdm_reference_registry(
            second,
            registry,
        )


def test_registry_detects_duplicate_ids_inside_existing_file_v5(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-1",
        capture_id="capture-1",
        capture_started_at_ns=1,
    )

    duplicate = _registry_record(
        candidate_id="candidate-1",
        capture_id="capture-2",
        capture_started_at_ns=2,
    )

    registry.write_bytes(
        reference._canonical_json_bytes(first.to_mapping())
        + reference._canonical_json_bytes(duplicate.to_mapping())
    )

    third = _registry_record(
        candidate_id="candidate-3",
        capture_id="capture-3",
        capture_started_at_ns=3,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="contains duplicate candidate_id",
    ):
        reference.append_binance_usdm_reference_registry(
            third,
            registry,
        )


def test_registry_detects_existing_capture_order_corruption_v5(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-1",
        capture_id="capture-1",
        capture_started_at_ns=2,
    )

    second = _registry_record(
        candidate_id="candidate-2",
        capture_id="capture-2",
        capture_started_at_ns=1,
    )

    registry.write_bytes(
        reference._canonical_json_bytes(first.to_mapping())
        + reference._canonical_json_bytes(second.to_mapping())
    )

    third = _registry_record(
        candidate_id="candidate-3",
        capture_id="capture-3",
        capture_started_at_ns=3,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="capture starts do not increase strictly",
    ):
        reference.append_binance_usdm_reference_registry(
            third,
            registry,
        )


def test_registry_detects_existing_valid_overlap_v5(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-1",
        capture_id="capture-1",
        capture_started_at_ns=1,
        outcome=(reference.BinanceUsdMReferenceCandidateOutcome.VALID),
        analysis_start_timestamp_ns=100,
        analysis_end_timestamp_ns=200,
    )

    second = _registry_record(
        candidate_id="candidate-2",
        capture_id="capture-2",
        capture_started_at_ns=2,
        outcome=(reference.BinanceUsdMReferenceCandidateOutcome.VALID),
        analysis_start_timestamp_ns=199,
        analysis_end_timestamp_ns=299,
    )

    registry.write_bytes(
        reference._canonical_json_bytes(first.to_mapping())
        + reference._canonical_json_bytes(second.to_mapping())
    )

    third = _registry_record(
        candidate_id="candidate-3",
        capture_id="capture-3",
        capture_started_at_ns=3,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="contains overlapping VALID blocks",
    ):
        reference.append_binance_usdm_reference_registry(
            third,
            registry,
        )


def test_registry_rejects_invalid_existing_valid_timestamp_v5(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"

    first = _registry_record(
        candidate_id="candidate-1",
        capture_id="capture-1",
        capture_started_at_ns=1,
        outcome=(reference.BinanceUsdMReferenceCandidateOutcome.VALID),
        analysis_start_timestamp_ns=100,
        analysis_end_timestamp_ns=200,
    )

    mapping = first.to_mapping()

    block = mapping["block"]
    assert isinstance(block, dict)

    block["analysis_end_timestamp_ns"] = "bad"

    _write_registry_mapping_v5(
        registry,
        mapping,
    )

    second = _registry_record(
        candidate_id="candidate-2",
        capture_id="capture-2",
        capture_started_at_ns=2,
    )

    with pytest.raises(
        InvalidMetricInputError,
        match="analysis_end_timestamp_ns is invalid",
    ):
        reference.append_binance_usdm_reference_registry(
            second,
            registry,
        )


def test_candidate_runner_rejects_existing_directory_v5(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    with pytest.raises(
        InvalidMetricInputError,
        match="must not already exist",
    ):
        asyncio.run(
            reference.run_binance_usdm_reference_candidate(
                candidate,
                repository_commit_sha="a" * 40,
                candidate_id="candidate-1",
                capture_id="capture-1",
            )
        )


def test_candidate_runner_success_path_v5(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_capture(
        directory: str | Path,
        **kwargs: Any,
    ) -> BinanceUsdMCandidateCaptureResult:
        return BinanceUsdMCandidateCaptureResult(
            artifact_directory=Path(directory),
            capture_id=(kwargs["capture_id"]),
            candidate_id=(kwargs["candidate_id"]),
            raw_record_count=10,
            depth_update_count=5,
            aggregate_trade_count=4,
            initial_snapshot_update_id=1,
            final_book_update_id=2,
            final_best_bid="100",
            final_best_ask="101",
            started_at_ns=10,
            ended_at_ns=20,
        )

    def fake_evaluation(
        artifact_directory: str | Path,
        **kwargs: Any,
    ) -> reference.BinanceUsdMReferenceCandidateEvaluation:
        return reference.BinanceUsdMReferenceCandidateEvaluation(
            artifact_directory=Path(artifact_directory),
            artifact_manifest_sha256=("b" * 64),
            reconstructed_interval_count=1,
            selected_interval_count=1,
            block_result=_rejected_block(
                candidate_id=(kwargs["candidate_id"]),
                source_id=(kwargs["source_id"]),
            ),
        )

    monkeypatch.setattr(
        reference,
        "capture_binance_usdm_candidate",
        fake_capture,
    )

    monkeypatch.setattr(
        reference,
        "evaluate_binance_usdm_reference_artifact",
        fake_evaluation,
    )

    candidate = tmp_path / "candidate-1"

    registry = tmp_path / "registry.jsonl"

    record = asyncio.run(
        reference.run_binance_usdm_reference_candidate(
            candidate,
            repository_commit_sha="a" * 40,
            candidate_id="candidate-1",
            capture_id="capture-1",
            registry_path=registry,
        )
    )

    assert record.outcome is reference.BinanceUsdMReferenceCandidateOutcome.REJECTED

    assert (candidate / "candidate-result.json").is_file()

    assert registry.is_file()


def test_capture_failure_monotonic_timestamp_guard_v5(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_capture(
        *args: object,
        **kwargs: object,
    ) -> BinanceUsdMCandidateCaptureResult:
        raise RuntimeError("forced")

    timestamps = iter(
        (
            100,
            100,
        )
    )

    monkeypatch.setattr(
        reference,
        "capture_binance_usdm_candidate",
        fail_capture,
    )

    monkeypatch.setattr(
        "abmforge_finance.study.binance_usdm_reference.time.time_ns",
        lambda: next(timestamps),
    )

    record = asyncio.run(
        reference.run_binance_usdm_reference_candidate(
            tmp_path / "candidate",
            repository_commit_sha="a" * 40,
            candidate_id="candidate-1",
            capture_id="capture-1",
            registry_path=(tmp_path / "registry.jsonl"),
        )
    )

    assert record.capture_started_at_ns == 100

    assert record.capture_ended_at_ns == 101
