"""Immutable raw-data artifacts for Binance USD-M empirical capture."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from itertools import pairwise
from pathlib import Path

from abmforge_finance.exceptions import (
    FinanceArtifactExistsError,
    FinanceArtifactVerificationError,
    InvalidFinanceArtifactError,
)
from abmforge_finance.study.binance_usdm_contract import (
    BINANCE_USDM_EMPIRICAL_CONTRACT_ID,
    BinanceUsdMEmpiricalContract,
    binance_usdm_empirical_contract,
)

BINANCE_USDM_RAW_CAPTURE_SCHEMA_VERSION = "binance-usdm-raw-capture-v1"

_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

try:
    _PACKAGE_VERSION = version("abmforge-finance")
except PackageNotFoundError:  # pragma: no cover
    _PACKAGE_VERSION = "0.1.0a0"


class BinanceUsdMRawChannel(str, Enum):
    """Raw source channel preserved in one empirical capture."""

    DEPTH_SNAPSHOT = "depth-snapshot"
    DEPTH_UPDATE = "depth-update"
    AGGREGATE_TRADE = "aggregate-trade"


@dataclass(frozen=True, slots=True)
class BinanceUsdMRawRecord:
    """One exact raw Binance JSON message with local receipt metadata."""

    sequence_number: int
    channel: BinanceUsdMRawChannel
    received_at_ns: int
    raw_json: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence_number, bool)
            or not isinstance(self.sequence_number, int)
            or self.sequence_number < 0
        ):
            raise InvalidFinanceArtifactError("sequence_number must be a non-negative integer")

        if not isinstance(self.channel, BinanceUsdMRawChannel):
            raise TypeError("channel must be a BinanceUsdMRawChannel")

        if (
            isinstance(self.received_at_ns, bool)
            or not isinstance(self.received_at_ns, int)
            or self.received_at_ns < 0
        ):
            raise InvalidFinanceArtifactError("received_at_ns must be a non-negative integer")

        if not isinstance(self.raw_json, str) or not self.raw_json:
            raise InvalidFinanceArtifactError("raw_json must be a non-empty string")

        try:
            value = json.loads(self.raw_json)
        except json.JSONDecodeError as exc:
            raise InvalidFinanceArtifactError("raw_json must contain valid JSON") from exc

        if not isinstance(value, dict):
            raise InvalidFinanceArtifactError("raw_json must contain a JSON object")


@dataclass(frozen=True, slots=True)
class BinanceUsdMCaptureProvenance:
    """Frozen capture identity independent of scientific estimates."""

    capture_id: str
    candidate_id: str
    repository_commit_sha: str
    started_at_ns: int
    ended_at_ns: int

    def __post_init__(self) -> None:
        for label, text_value in (
            ("capture_id", self.capture_id),
            ("candidate_id", self.candidate_id),
        ):
            if not isinstance(text_value, str) or not text_value.strip():
                raise InvalidFinanceArtifactError(f"{label} must be a non-empty string")

        if (
            not isinstance(self.repository_commit_sha, str)
            or _GIT_SHA_PATTERN.fullmatch(self.repository_commit_sha) is None
        ):
            raise InvalidFinanceArtifactError(
                "repository_commit_sha must be a 40-character lowercase Git SHA"
            )

        for label, timestamp_value in (
            ("started_at_ns", self.started_at_ns),
            ("ended_at_ns", self.ended_at_ns),
        ):
            if (
                isinstance(timestamp_value, bool)
                or not isinstance(timestamp_value, int)
                or timestamp_value < 0
            ):
                raise InvalidFinanceArtifactError(f"{label} must be a non-negative integer")

        if self.ended_at_ns <= self.started_at_ns:
            raise InvalidFinanceArtifactError("ended_at_ns must be greater than started_at_ns")

    def to_mapping(self) -> dict[str, object]:
        """Return deterministic provenance metadata."""

        return {
            "candidate_id": self.candidate_id,
            "capture_id": self.capture_id,
            "ended_at_ns": self.ended_at_ns,
            "repository_commit_sha": self.repository_commit_sha,
            "started_at_ns": self.started_at_ns,
        }


_FILE_BY_CHANNEL = {
    BinanceUsdMRawChannel.DEPTH_SNAPSHOT: "depth_snapshot.jsonl",
    BinanceUsdMRawChannel.DEPTH_UPDATE: "depth_updates.jsonl",
    BinanceUsdMRawChannel.AGGREGATE_TRADE: "aggregate_trades.jsonl",
}

_JSONL_COLUMNS = (
    "sequence_number",
    "received_at_ns",
    "raw_json",
)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest_bytes(
    manifest: dict[str, object],
) -> bytes:
    text = json.dumps(
        manifest,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{text}\n".encode()


def _jsonl(
    records: tuple[BinanceUsdMRawRecord, ...],
) -> bytes:
    lines: list[str] = []

    for record in records:
        value = {
            "sequence_number": record.sequence_number,
            "received_at_ns": record.received_at_ns,
            "raw_json": record.raw_json,
        }

        lines.append(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
        )

    if not lines:
        return b""

    return ("\n".join(lines) + "\n").encode("utf-8")


def _validate_capture_records(
    records: tuple[BinanceUsdMRawRecord, ...],
) -> None:
    if not isinstance(records, tuple):
        raise TypeError("records must be a tuple of BinanceUsdMRawRecord")

    if not records:
        raise InvalidFinanceArtifactError("raw capture must contain at least one record")

    previous_sequence = -1
    previous_received_at = -1
    snapshot_count = 0

    for index, record in enumerate(records):
        if not isinstance(record, BinanceUsdMRawRecord):
            raise TypeError(f"records[{index}] must be a BinanceUsdMRawRecord")

        if record.sequence_number <= previous_sequence:
            raise InvalidFinanceArtifactError("raw capture sequence numbers must increase strictly")

        if record.received_at_ns < previous_received_at:
            raise InvalidFinanceArtifactError(
                "raw capture receipt timestamps must be non-decreasing"
            )

        if record.channel is BinanceUsdMRawChannel.DEPTH_SNAPSHOT:
            snapshot_count += 1

        previous_sequence = record.sequence_number
        previous_received_at = record.received_at_ns

    if snapshot_count != 1:
        raise InvalidFinanceArtifactError(
            "one continuous candidate capture must contain exactly one depth snapshot"
        )


def write_binance_usdm_raw_capture(
    records: tuple[BinanceUsdMRawRecord, ...],
    directory: str | Path,
    *,
    provenance: BinanceUsdMCaptureProvenance,
    contract: BinanceUsdMEmpiricalContract | None = None,
) -> Path:
    """Atomically create one immutable canonical raw-capture artifact."""

    _validate_capture_records(records)

    if not isinstance(
        provenance,
        BinanceUsdMCaptureProvenance,
    ):
        raise TypeError("provenance must be a BinanceUsdMCaptureProvenance")

    active_contract = binance_usdm_empirical_contract() if contract is None else contract

    if active_contract.contract_id != BINANCE_USDM_EMPIRICAL_CONTRACT_ID:
        raise InvalidFinanceArtifactError("unexpected empirical contract id")

    target = Path(directory)

    if target.exists():
        raise FinanceArtifactExistsError(f"artifact directory already exists: {target}")

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temp = Path(
        tempfile.mkdtemp(
            prefix=f".{target.name}.tmp-",
            dir=target.parent,
        )
    )

    try:
        files: dict[str, object] = {}

        for channel in BinanceUsdMRawChannel:
            selected = tuple(record for record in records if record.channel is channel)

            payload = _jsonl(selected)
            filename = _FILE_BY_CHANNEL[channel]

            (temp / filename).write_bytes(payload)

            files[channel.value] = {
                "path": filename,
                "records": len(selected),
                "sha256": _digest(payload),
            }

        manifest: dict[str, object] = {
            "artifact_schema_version": (BINANCE_USDM_RAW_CAPTURE_SCHEMA_VERSION),
            "contract": active_contract.to_mapping(),
            "files": files,
            "producer": {
                "name": "abmforge-finance",
                "version": _PACKAGE_VERSION,
            },
            "provenance": provenance.to_mapping(),
            "record_count": len(records),
        }

        (temp / "manifest.json").write_bytes(_manifest_bytes(manifest))

        os.replace(temp, target)

    except Exception:
        shutil.rmtree(
            temp,
            ignore_errors=True,
        )
        raise

    return target


def _verify_jsonl(
    path: Path,
    *,
    expected_records: int,
) -> tuple[tuple[int, int, str], ...]:
    payload = path.read_bytes()

    if b"\r\n" in payload:
        raise FinanceArtifactVerificationError(f"{path.name} must use LF line endings")

    lines = payload.splitlines()

    if len(lines) != expected_records:
        raise FinanceArtifactVerificationError(f"{path.name} record count mismatch")

    output: list[tuple[int, int, str]] = []

    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FinanceArtifactVerificationError(f"{path.name} contains invalid JSON") from exc

        if not isinstance(value, dict) or tuple(value) != _JSONL_COLUMNS:
            raise FinanceArtifactVerificationError(f"{path.name} columns are invalid")

        canonical = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")

        if canonical != line:
            raise FinanceArtifactVerificationError(f"{path.name} is not canonical JSONL")

        sequence = value["sequence_number"]
        received_at = value["received_at_ns"]
        raw_json = value["raw_json"]

        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 0
            or isinstance(received_at, bool)
            or not isinstance(received_at, int)
            or received_at < 0
            or not isinstance(raw_json, str)
        ):
            raise FinanceArtifactVerificationError(f"{path.name} contains invalid record metadata")

        try:
            raw_value = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise FinanceArtifactVerificationError(
                f"{path.name} contains invalid raw_json"
            ) from exc

        if not isinstance(raw_value, dict):
            raise FinanceArtifactVerificationError(f"{path.name} raw_json must contain an object")

        output.append(
            (
                sequence,
                received_at,
                raw_json,
            )
        )

    return tuple(output)


def verify_binance_usdm_raw_capture(
    directory: str | Path,
) -> None:
    """Verify canonical encoding, membership, hashes, and capture ordering."""

    root = Path(directory)
    manifest_path = root / "manifest.json"

    if not root.is_dir() or not manifest_path.is_file():
        raise FinanceArtifactVerificationError("raw capture artifact is missing manifest.json")

    manifest_payload = manifest_path.read_bytes()

    try:
        value = json.loads(manifest_payload)
    except json.JSONDecodeError as exc:
        raise FinanceArtifactVerificationError("manifest.json is invalid JSON") from exc

    if not isinstance(value, dict):
        raise FinanceArtifactVerificationError("manifest.json must contain an object")

    manifest = value

    if _manifest_bytes(manifest) != manifest_payload:
        raise FinanceArtifactVerificationError("manifest.json is not canonical")

    if manifest.get("artifact_schema_version") != (BINANCE_USDM_RAW_CAPTURE_SCHEMA_VERSION):
        raise FinanceArtifactVerificationError("unsupported raw capture artifact schema")

    contract = manifest.get("contract")
    expected_contract = binance_usdm_empirical_contract().to_mapping()

    if contract != expected_contract:
        raise FinanceArtifactVerificationError(
            "raw capture contract does not match frozen contract"
        )

    producer = manifest.get("producer")
    provenance = manifest.get("provenance")
    files = manifest.get("files")
    record_count = manifest.get("record_count")

    if (
        not isinstance(producer, dict)
        or producer.get("name") != "abmforge-finance"
        or not isinstance(producer.get("version"), str)
    ):
        raise FinanceArtifactVerificationError("invalid raw capture producer metadata")

    if not isinstance(provenance, dict):
        raise FinanceArtifactVerificationError("invalid raw capture provenance")

    try:
        BinanceUsdMCaptureProvenance(
            capture_id=provenance["capture_id"],
            candidate_id=provenance["candidate_id"],
            repository_commit_sha=(provenance["repository_commit_sha"]),
            started_at_ns=provenance["started_at_ns"],
            ended_at_ns=provenance["ended_at_ns"],
        )
    except (
        KeyError,
        TypeError,
        InvalidFinanceArtifactError,
    ) as exc:
        raise FinanceArtifactVerificationError("invalid raw capture provenance") from exc

    if isinstance(record_count, bool) or not isinstance(record_count, int) or record_count < 1:
        raise FinanceArtifactVerificationError("invalid raw capture record count")

    if not isinstance(files, dict) or set(files) != {
        channel.value for channel in BinanceUsdMRawChannel
    }:
        raise FinanceArtifactVerificationError("invalid raw capture file membership")

    expected_names = {
        "manifest.json",
        *_FILE_BY_CHANNEL.values(),
    }

    actual_names = {path.name for path in root.iterdir()}

    if actual_names != expected_names or any(path.is_dir() for path in root.iterdir()):
        raise FinanceArtifactVerificationError("raw capture directory membership is invalid")

    observed: list[tuple[int, int, str]] = []
    snapshot_records = 0

    for channel in BinanceUsdMRawChannel:
        metadata = files[channel.value]

        if not isinstance(metadata, dict):
            raise FinanceArtifactVerificationError(f"invalid file metadata for {channel.value}")

        filename = metadata.get("path")
        count = metadata.get("records")
        digest = metadata.get("sha256")

        expected_name = _FILE_BY_CHANNEL[channel]

        if (
            filename != expected_name
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or not isinstance(digest, str)
        ):
            raise FinanceArtifactVerificationError(f"invalid file metadata for {channel.value}")

        path = root / expected_name

        if not path.is_file() or _digest(path.read_bytes()) != digest:
            raise FinanceArtifactVerificationError(f"integrity failure for {expected_name}")

        rows = _verify_jsonl(
            path,
            expected_records=count,
        )

        observed.extend(rows)

        if channel is BinanceUsdMRawChannel.DEPTH_SNAPSHOT:
            snapshot_records = count

    if len(observed) != record_count:
        raise FinanceArtifactVerificationError("manifest total record count mismatch")

    if snapshot_records != 1:
        raise FinanceArtifactVerificationError(
            "raw capture must contain exactly one depth snapshot"
        )

    observed.sort(key=lambda row: row[0])

    sequences = tuple(row[0] for row in observed)

    if len(set(sequences)) != len(sequences):
        raise FinanceArtifactVerificationError("raw capture sequence numbers are not unique")

    if any(right <= left for left, right in pairwise(sequences)):
        raise FinanceArtifactVerificationError(
            "raw capture sequence numbers do not increase strictly"
        )

    receipt_times = tuple(row[1] for row in observed)

    if any(right < left for left, right in pairwise(receipt_times)):
        raise FinanceArtifactVerificationError("raw capture receipt timestamps decrease")
