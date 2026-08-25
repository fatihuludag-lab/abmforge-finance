"""Official Binance USD-M empirical reference-set orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import cast

from abmforge_finance.exceptions import (
    FinanceArtifactVerificationError,
    InvalidMetricInputError,
)
from abmforge_finance.study.binance_usdm_artifacts import (
    verify_binance_usdm_raw_capture,
)
from abmforge_finance.study.binance_usdm_blocks import (
    BinanceUsdMEmpiricalBlockRejectionReason,
    BinanceUsdMEmpiricalBlockResult,
    BinanceUsdMEmpiricalBlockStatus,
    evaluate_binance_usdm_empirical_block,
)
from abmforge_finance.study.binance_usdm_collector import (
    BinanceUsdMCandidateCaptureResult,
    capture_binance_usdm_candidate,
)
from abmforge_finance.study.binance_usdm_contract import (
    BinanceUsdMEmpiricalContract,
    binance_usdm_empirical_contract,
)
from abmforge_finance.study.binance_usdm_replay import (
    reconstruct_binance_usdm_empirical_intervals,
)

BINANCE_USDM_REFERENCE_CANDIDATE_SCHEMA_VERSION = "binance-usdm-reference-candidate-v1"

BINANCE_USDM_REFERENCE_REGISTRY_SCHEMA_VERSION = "binance-usdm-reference-registry-v1"


class BinanceUsdMReferenceCandidateOutcome(
    str,
    Enum,
):
    """Outcome of one sequential ADR-033 capture attempt."""

    VALID = "valid"
    REJECTED = "rejected"
    CAPTURE_FAILED = "capture-failed"


@dataclass(frozen=True, slots=True)
class BinanceUsdMReferenceCandidateEvaluation:
    """Deterministic evaluation of one finalized raw artifact."""

    artifact_directory: Path
    artifact_manifest_sha256: str | None
    reconstructed_interval_count: int
    selected_interval_count: int
    block_result: BinanceUsdMEmpiricalBlockResult


@dataclass(frozen=True, slots=True)
class BinanceUsdMReferenceCandidateRecord:
    """Append-only registry representation of one candidate attempt."""

    candidate_id: str
    capture_id: str
    repository_commit_sha: str
    source_id: str
    outcome: BinanceUsdMReferenceCandidateOutcome

    artifact_directory: str | None
    artifact_manifest_sha256: str | None

    capture_started_at_ns: int
    capture_ended_at_ns: int

    reconstructed_interval_count: int
    selected_interval_count: int

    block_status: BinanceUsdMEmpiricalBlockStatus | None
    rejection_reason: BinanceUsdMEmpiricalBlockRejectionReason | None
    rejection_detail: str | None

    raw_interval_count: int
    canonical_observation_count: int

    raw_start_timestamp_ns: int | None
    raw_end_timestamp_ns: int | None
    analysis_start_timestamp_ns: int | None
    analysis_end_timestamp_ns: int | None

    failure_type: str | None
    failure_detail: str | None

    def to_mapping(self) -> dict[str, object]:
        return {
            "schema_version": (BINANCE_USDM_REFERENCE_CANDIDATE_SCHEMA_VERSION),
            "candidate_id": self.candidate_id,
            "capture_id": self.capture_id,
            "repository_commit_sha": (self.repository_commit_sha),
            "source_id": self.source_id,
            "outcome": self.outcome.value,
            "artifact": (
                None
                if self.artifact_directory is None
                else {
                    "directory": self.artifact_directory,
                    "manifest_sha256": (self.artifact_manifest_sha256),
                }
            ),
            "capture": {
                "started_at_ns": (self.capture_started_at_ns),
                "ended_at_ns": (self.capture_ended_at_ns),
            },
            "reconstruction": {
                "interval_count": (self.reconstructed_interval_count),
                "selected_interval_count": (self.selected_interval_count),
            },
            "block": (
                None
                if self.block_status is None
                else {
                    "status": (self.block_status.value),
                    "rejection_reason": (
                        None if self.rejection_reason is None else self.rejection_reason.value
                    ),
                    "rejection_detail": (self.rejection_detail),
                    "raw_interval_count": (self.raw_interval_count),
                    "canonical_observation_count": (self.canonical_observation_count),
                    "raw_start_timestamp_ns": (self.raw_start_timestamp_ns),
                    "raw_end_timestamp_ns": (self.raw_end_timestamp_ns),
                    "analysis_start_timestamp_ns": (self.analysis_start_timestamp_ns),
                    "analysis_end_timestamp_ns": (self.analysis_end_timestamp_ns),
                }
            ),
            "failure": (
                None
                if self.failure_type is None
                else {
                    "type": self.failure_type,
                    "detail": self.failure_detail,
                }
            ),
        }


def _manifest_sha256(
    artifact_directory: Path,
) -> str | None:
    manifest = artifact_directory / "manifest.json"

    if not manifest.is_file():
        return None

    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def _source_id(
    candidate_id: str,
    contract: BinanceUsdMEmpiricalContract,
) -> str:
    return f"{contract.contract_id}:{candidate_id}"


def evaluate_binance_usdm_reference_artifact(
    artifact_directory: str | Path,
    *,
    candidate_id: str,
    source_id: str,
    contract: BinanceUsdMEmpiricalContract | None = None,
) -> BinanceUsdMReferenceCandidateEvaluation:
    """Evaluate the first prespecified 4,097 complete intervals."""

    root = Path(artifact_directory)

    active_contract = binance_usdm_empirical_contract() if contract is None else contract

    manifest_sha256 = _manifest_sha256(root)

    try:
        verify_binance_usdm_raw_capture(root)

        reconstructed = reconstruct_binance_usdm_empirical_intervals(root)

    except (
        FinanceArtifactVerificationError,
        InvalidMetricInputError,
    ) as exc:
        block = evaluate_binance_usdm_empirical_block(
            candidate_id=candidate_id,
            source_id=source_id,
            intervals=(),
            source_integrity_failure=(f"{type(exc).__name__}: {exc}"),
            contract=active_contract,
        )

        return BinanceUsdMReferenceCandidateEvaluation(
            artifact_directory=root,
            artifact_manifest_sha256=(manifest_sha256),
            reconstructed_interval_count=0,
            selected_interval_count=0,
            block_result=block,
        )

    expected_interval_count = active_contract.block_observation_count + 1

    selected = reconstructed[:expected_interval_count]

    block = evaluate_binance_usdm_empirical_block(
        candidate_id=candidate_id,
        source_id=source_id,
        intervals=selected,
        contract=active_contract,
    )

    return BinanceUsdMReferenceCandidateEvaluation(
        artifact_directory=root,
        artifact_manifest_sha256=(manifest_sha256),
        reconstructed_interval_count=len(reconstructed),
        selected_interval_count=len(selected),
        block_result=block,
    )


def _record_from_evaluation(
    *,
    capture: BinanceUsdMCandidateCaptureResult,
    evaluation: BinanceUsdMReferenceCandidateEvaluation,
    repository_commit_sha: str,
    source_id: str,
) -> BinanceUsdMReferenceCandidateRecord:
    block = evaluation.block_result

    outcome = (
        BinanceUsdMReferenceCandidateOutcome.VALID
        if block.is_valid
        else BinanceUsdMReferenceCandidateOutcome.REJECTED
    )

    return BinanceUsdMReferenceCandidateRecord(
        candidate_id=capture.candidate_id,
        capture_id=capture.capture_id,
        repository_commit_sha=(repository_commit_sha),
        source_id=source_id,
        outcome=outcome,
        artifact_directory="raw",
        artifact_manifest_sha256=(evaluation.artifact_manifest_sha256),
        capture_started_at_ns=(capture.started_at_ns),
        capture_ended_at_ns=(capture.ended_at_ns),
        reconstructed_interval_count=(evaluation.reconstructed_interval_count),
        selected_interval_count=(evaluation.selected_interval_count),
        block_status=block.status,
        rejection_reason=(block.rejection_reason),
        rejection_detail=(block.rejection_detail),
        raw_interval_count=(block.raw_interval_count),
        canonical_observation_count=(block.canonical_observation_count),
        raw_start_timestamp_ns=(block.raw_start_timestamp_ns),
        raw_end_timestamp_ns=(block.raw_end_timestamp_ns),
        analysis_start_timestamp_ns=(block.analysis_start_timestamp_ns),
        analysis_end_timestamp_ns=(block.analysis_end_timestamp_ns),
        failure_type=None,
        failure_detail=None,
    )


def _capture_failure_record(
    *,
    candidate_id: str,
    capture_id: str,
    repository_commit_sha: str,
    source_id: str,
    started_at_ns: int,
    ended_at_ns: int,
    raw_directory: Path,
    exc: Exception,
) -> BinanceUsdMReferenceCandidateRecord:
    artifact_exists = (raw_directory / "manifest.json").is_file()

    return BinanceUsdMReferenceCandidateRecord(
        candidate_id=candidate_id,
        capture_id=capture_id,
        repository_commit_sha=(repository_commit_sha),
        source_id=source_id,
        outcome=(BinanceUsdMReferenceCandidateOutcome.CAPTURE_FAILED),
        artifact_directory=("raw" if artifact_exists else None),
        artifact_manifest_sha256=(_manifest_sha256(raw_directory) if artifact_exists else None),
        capture_started_at_ns=started_at_ns,
        capture_ended_at_ns=ended_at_ns,
        reconstructed_interval_count=0,
        selected_interval_count=0,
        block_status=None,
        rejection_reason=None,
        rejection_detail=None,
        raw_interval_count=0,
        canonical_observation_count=0,
        raw_start_timestamp_ns=None,
        raw_end_timestamp_ns=None,
        analysis_start_timestamp_ns=None,
        analysis_end_timestamp_ns=None,
        failure_type=type(exc).__name__,
        failure_detail=str(exc),
    )


def _canonical_json_bytes(
    mapping: dict[str, object],
) -> bytes:
    return (
        json.dumps(
            mapping,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def write_binance_usdm_reference_candidate_result(
    record: BinanceUsdMReferenceCandidateRecord,
    path: str | Path,
) -> Path:
    target = Path(path)

    if target.exists():
        raise InvalidMetricInputError("candidate-result artifact already exists")

    target.write_bytes(_canonical_json_bytes(record.to_mapping()))

    return target


def append_binance_usdm_reference_registry(
    record: BinanceUsdMReferenceCandidateRecord,
    path: str | Path,
) -> Path:
    """Atomically append one immutable logical registry entry."""

    target = Path(path)
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing = target.read_bytes() if target.exists() else b""

    if existing and not existing.endswith(b"\n"):
        raise InvalidMetricInputError("reference registry is not canonical JSONL")

    observed_candidate_ids: set[str] = set()
    observed_capture_ids: set[str] = set()

    previous_started_at_ns = -1
    previous_valid_analysis_end: int | None = None

    for raw_line in existing.splitlines():
        try:
            value = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise InvalidMetricInputError("reference registry contains invalid JSON") from exc

        if not isinstance(value, dict):
            raise InvalidMetricInputError("reference registry rows must be objects")

        if value.get("schema_version") != BINANCE_USDM_REFERENCE_CANDIDATE_SCHEMA_VERSION:
            raise InvalidMetricInputError("reference registry schema mismatch")

        canonical = _canonical_json_bytes(value).rstrip(b"\n")

        if canonical != raw_line:
            raise InvalidMetricInputError("reference registry is not canonical JSONL")

        candidate = value.get("candidate_id")
        capture = value.get("capture_id")

        if not isinstance(candidate, str):
            raise InvalidMetricInputError("registry candidate_id is invalid")

        if not isinstance(capture, str):
            raise InvalidMetricInputError("registry capture_id is invalid")

        if candidate in observed_candidate_ids:
            raise InvalidMetricInputError("reference registry contains duplicate candidate_id")

        if capture in observed_capture_ids:
            raise InvalidMetricInputError("reference registry contains duplicate capture_id")

        observed_candidate_ids.add(candidate)
        observed_capture_ids.add(capture)

        capture_metadata = value.get("capture")

        if not isinstance(
            capture_metadata,
            dict,
        ):
            raise InvalidMetricInputError("registry capture metadata is invalid")

        started = capture_metadata.get("started_at_ns")

        if isinstance(started, bool) or not isinstance(
            started,
            int,
        ):
            raise InvalidMetricInputError("registry capture start is invalid")

        if previous_started_at_ns >= 0 and started <= previous_started_at_ns:
            raise InvalidMetricInputError(
                "reference registry capture starts do not increase strictly"
            )

        previous_started_at_ns = started

        block = value.get("block")

        if isinstance(block, dict) and block.get("status") == "valid":
            analysis_start = block.get("analysis_start_timestamp_ns")
            analysis_end = block.get("analysis_end_timestamp_ns")

            for label, timestamp in (
                (
                    "analysis_start_timestamp_ns",
                    analysis_start,
                ),
                (
                    "analysis_end_timestamp_ns",
                    analysis_end,
                ),
            ):
                if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp < 0:
                    raise InvalidMetricInputError(
                        f"reference registry VALID block {label} is invalid"
                    )

            if cast(int, analysis_end) <= cast(int, analysis_start):
                raise InvalidMetricInputError(
                    "reference registry VALID block analysis interval is invalid"
                )

            if (
                previous_valid_analysis_end is not None
                and cast(int, analysis_start) < previous_valid_analysis_end
            ):
                raise InvalidMetricInputError(
                    "reference registry contains overlapping VALID blocks"
                )

            previous_valid_analysis_end = cast(int, analysis_end)

    if record.candidate_id in observed_candidate_ids:
        raise InvalidMetricInputError("candidate_id already exists in reference registry")

    if record.capture_id in observed_capture_ids:
        raise InvalidMetricInputError("capture_id already exists in reference registry")

    if previous_started_at_ns >= 0 and record.capture_started_at_ns <= previous_started_at_ns:
        raise InvalidMetricInputError("candidate capture start must increase strictly")

    if (
        record.outcome is BinanceUsdMReferenceCandidateOutcome.VALID
        and previous_valid_analysis_end is not None
        and record.analysis_start_timestamp_ns is not None
        and record.analysis_start_timestamp_ns < previous_valid_analysis_end
    ):
        raise InvalidMetricInputError("VALID reference blocks must not overlap")

    new_payload = existing + _canonical_json_bytes(record.to_mapping())

    temp = target.with_name(f".{target.name}.tmp")

    temp.write_bytes(new_payload)

    os.replace(
        temp,
        target,
    )

    return target


async def run_binance_usdm_reference_candidate(
    directory: str | Path,
    *,
    repository_commit_sha: str,
    candidate_id: str,
    capture_id: str,
    registry_path: str | Path | None = None,
    contract: BinanceUsdMEmpiricalContract | None = None,
) -> BinanceUsdMReferenceCandidateRecord:
    """Capture, verify, replay, evaluate and register one candidate."""

    candidate_root = Path(directory)

    if candidate_root.exists():
        raise InvalidMetricInputError("candidate directory must not already exist")

    candidate_root.mkdir(
        parents=True,
    )

    raw_directory = candidate_root / "raw"

    active_contract = binance_usdm_empirical_contract() if contract is None else contract

    source_id = _source_id(
        candidate_id,
        active_contract,
    )

    registry = (
        candidate_root.parent / "reference-set-registry.jsonl"
        if registry_path is None
        else Path(registry_path)
    )

    attempt_started_at_ns = time.time_ns()

    try:
        capture = await capture_binance_usdm_candidate(
            raw_directory,
            repository_commit_sha=(repository_commit_sha),
            capture_id=capture_id,
            candidate_id=candidate_id,
            contract=active_contract,
        )

    except Exception as exc:
        attempt_ended_at_ns = time.time_ns()

        if attempt_ended_at_ns <= attempt_started_at_ns:
            attempt_ended_at_ns = attempt_started_at_ns + 1

        record = _capture_failure_record(
            candidate_id=candidate_id,
            capture_id=capture_id,
            repository_commit_sha=(repository_commit_sha),
            source_id=source_id,
            started_at_ns=(attempt_started_at_ns),
            ended_at_ns=(attempt_ended_at_ns),
            raw_directory=(raw_directory),
            exc=exc,
        )

    else:
        evaluation = evaluate_binance_usdm_reference_artifact(
            raw_directory,
            candidate_id=candidate_id,
            source_id=source_id,
            contract=active_contract,
        )

        record = _record_from_evaluation(
            capture=capture,
            evaluation=evaluation,
            repository_commit_sha=(repository_commit_sha),
            source_id=source_id,
        )

    write_binance_usdm_reference_candidate_result(
        record,
        candidate_root / "candidate-result.json",
    )

    append_binance_usdm_reference_registry(
        record,
        registry,
    )

    return record
