"""Immutable raw-data artifacts for Binance USD-M empirical capture."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from heapq import merge
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import BinaryIO

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


def _digest_file(path: Path) -> str:
    hasher = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)

            if not chunk:
                break

            hasher.update(chunk)

    return hasher.hexdigest()


class BinanceUsdMRawCaptureStreamWriter:
    """Bounded-memory canonical raw-capture writer."""

    __slots__ = (
        "_closed",
        "_contract",
        "_counts",
        "_handles",
        "_previous_received_at",
        "_previous_sequence",
        "_record_count",
        "_snapshot_count",
        "_target",
        "_temp",
    )

    def __init__(
        self,
        directory: str | Path,
        *,
        contract: BinanceUsdMEmpiricalContract | None = None,
    ) -> None:
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

        handles: dict[
            BinanceUsdMRawChannel,
            BinaryIO,
        ] = {}

        try:
            for channel in BinanceUsdMRawChannel:
                handles[channel] = (temp / _FILE_BY_CHANNEL[channel]).open("wb")

        except Exception:
            for handle in handles.values():
                handle.close()

            shutil.rmtree(
                temp,
                ignore_errors=True,
            )
            raise

        self._target = target
        self._temp = temp
        self._contract = active_contract
        self._handles = handles
        self._counts = {channel: 0 for channel in BinanceUsdMRawChannel}
        self._record_count = 0
        self._snapshot_count = 0
        self._previous_sequence = -1
        self._previous_received_at = -1
        self._closed = False

    @property
    def record_count(self) -> int:
        return self._record_count

    def append(
        self,
        record: BinanceUsdMRawRecord,
    ) -> None:
        if self._closed:
            raise InvalidFinanceArtifactError("raw capture stream writer is closed")

        if not isinstance(
            record,
            BinanceUsdMRawRecord,
        ):
            raise TypeError("record must be a BinanceUsdMRawRecord")

        if record.sequence_number <= self._previous_sequence:
            raise InvalidFinanceArtifactError("raw capture sequence numbers must increase strictly")

        if record.received_at_ns < self._previous_received_at:
            raise InvalidFinanceArtifactError(
                "raw capture receipt timestamps must be non-decreasing"
            )

        value = {
            "sequence_number": (record.sequence_number),
            "received_at_ns": (record.received_at_ns),
            "raw_json": record.raw_json,
        }

        payload = (
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

        self._handles[record.channel].write(payload)

        self._counts[record.channel] += 1

        if record.channel is BinanceUsdMRawChannel.DEPTH_SNAPSHOT:
            self._snapshot_count += 1

        self._record_count += 1
        self._previous_sequence = record.sequence_number
        self._previous_received_at = record.received_at_ns

    def _close_handles(self) -> None:
        for handle in self._handles.values():
            if not handle.closed:
                handle.flush()
                handle.close()

    def finalize(
        self,
        *,
        provenance: BinanceUsdMCaptureProvenance,
    ) -> Path:
        if self._closed:
            raise InvalidFinanceArtifactError("raw capture stream writer is closed")

        if not isinstance(
            provenance,
            BinanceUsdMCaptureProvenance,
        ):
            raise TypeError("provenance must be a BinanceUsdMCaptureProvenance")

        if self._record_count < 1:
            raise InvalidFinanceArtifactError("raw capture must contain at least one record")

        if self._snapshot_count != 1:
            raise InvalidFinanceArtifactError(
                "one continuous candidate capture must contain exactly one depth snapshot"
            )

        try:
            self._close_handles()

            files: dict[str, object] = {}

            for channel in BinanceUsdMRawChannel:
                filename = _FILE_BY_CHANNEL[channel]

                file_path = self._temp / filename

                files[channel.value] = {
                    "path": filename,
                    "records": (self._counts[channel]),
                    "sha256": (_digest_file(file_path)),
                }

            manifest: dict[str, object] = {
                "artifact_schema_version": (BINANCE_USDM_RAW_CAPTURE_SCHEMA_VERSION),
                "contract": (self._contract.to_mapping()),
                "files": files,
                "producer": {
                    "name": "abmforge-finance",
                    "version": _PACKAGE_VERSION,
                },
                "provenance": (provenance.to_mapping()),
                "record_count": (self._record_count),
            }

            (self._temp / "manifest.json").write_bytes(_manifest_bytes(manifest))

            os.replace(
                self._temp,
                self._target,
            )

        except Exception:
            self._close_handles()

            shutil.rmtree(
                self._temp,
                ignore_errors=True,
            )
            self._closed = True
            raise

        self._closed = True

        return self._target

    def abort(self) -> None:
        if self._closed:
            return

        self._close_handles()

        shutil.rmtree(
            self._temp,
            ignore_errors=True,
        )

        self._closed = True


def _iter_jsonl_metadata(
    path: Path,
) -> Iterator[tuple[int, int]]:
    """Yield verified sequence/receipt metadata one JSONL row at a time."""

    previous_sequence = -1

    with path.open("rb") as handle:
        for raw_line in handle:
            if b"\r\n" in raw_line:
                raise FinanceArtifactVerificationError(f"{path.name} must use LF line endings")

            line = raw_line[:-1] if raw_line.endswith(b"\n") else raw_line

            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise FinanceArtifactVerificationError(
                    f"{path.name} contains invalid JSON"
                ) from exc

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
                raise FinanceArtifactVerificationError(
                    f"{path.name} contains invalid record metadata"
                )

            try:
                raw_value = json.loads(raw_json)
            except json.JSONDecodeError as exc:
                raise FinanceArtifactVerificationError(
                    f"{path.name} contains invalid raw_json"
                ) from exc

            if not isinstance(raw_value, dict):
                raise FinanceArtifactVerificationError(
                    f"{path.name} raw_json must contain an object"
                )

            if sequence == previous_sequence:
                raise FinanceArtifactVerificationError(
                    "raw capture sequence numbers are not unique"
                )

            if sequence < previous_sequence:
                raise FinanceArtifactVerificationError(
                    "raw capture sequence numbers do not increase strictly"
                )

            previous_sequence = sequence

            yield (
                sequence,
                received_at,
            )


def _verify_jsonl_stream(
    path: Path,
    *,
    expected_records: int,
) -> None:
    """Verify one canonical JSONL channel with bounded memory."""

    observed_records = 0

    for _ in _iter_jsonl_metadata(path):
        observed_records += 1

    if observed_records != expected_records:
        raise FinanceArtifactVerificationError(f"{path.name} record count mismatch")


def verify_binance_usdm_raw_capture(
    directory: str | Path,
) -> None:
    """Verify canonical encoding, membership, hashes, and capture ordering."""

    root = Path(directory)
    manifest_path = root / "manifest.json"

    if not root.is_dir() or not manifest_path.is_file():
        raise FinanceArtifactVerificationError("raw capture artifact is missing manifest.json")

    # manifest.json is intentionally tiny and may be loaded atomically.
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

    if manifest.get("artifact_schema_version") != BINANCE_USDM_RAW_CAPTURE_SCHEMA_VERSION:
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
        or not isinstance(
            producer.get("version"),
            str,
        )
    ):
        raise FinanceArtifactVerificationError("invalid raw capture producer metadata")

    if not isinstance(provenance, dict):
        raise FinanceArtifactVerificationError("invalid raw capture provenance")

    try:
        BinanceUsdMCaptureProvenance(
            capture_id=provenance["capture_id"],
            candidate_id=provenance["candidate_id"],
            repository_commit_sha=provenance["repository_commit_sha"],
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

    actual_names = {item.name for item in root.iterdir()}

    if actual_names != expected_names or any(item.is_dir() for item in root.iterdir()):
        raise FinanceArtifactVerificationError("raw capture directory membership is invalid")

    channel_paths: list[Path] = []
    total_records = 0
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

        raw_path = root / expected_name

        # Critical change: hash in chunks; never read the whole
        # raw channel into one bytes object.
        if not raw_path.is_file() or _digest_file(raw_path) != digest:
            raise FinanceArtifactVerificationError(f"integrity failure for {expected_name}")

        _verify_jsonl_stream(
            raw_path,
            expected_records=count,
        )

        channel_paths.append(raw_path)
        total_records += count

        if channel is BinanceUsdMRawChannel.DEPTH_SNAPSHOT:
            snapshot_records = count

    if total_records != record_count:
        raise FinanceArtifactVerificationError("manifest total record count mismatch")

    if snapshot_records != 1:
        raise FinanceArtifactVerificationError(
            "raw capture must contain exactly one depth snapshot"
        )

    # Three already-validated channel subsequences are merged lazily.
    # Memory use remains O(number of channels), not O(number of records).
    merged_rows = merge(
        *(_iter_jsonl_metadata(raw_path) for raw_path in channel_paths),
        key=lambda row: row[0],
    )

    previous_sequence = -1
    previous_received_at = -1
    merged_count = 0

    for sequence, received_at in merged_rows:
        if sequence == previous_sequence:
            raise FinanceArtifactVerificationError("raw capture sequence numbers are not unique")

        if sequence < previous_sequence:
            raise FinanceArtifactVerificationError(
                "raw capture sequence numbers do not increase strictly"
            )

        if received_at < previous_received_at:
            raise FinanceArtifactVerificationError("raw capture receipt timestamps decrease")

        previous_sequence = sequence
        previous_received_at = received_at
        merged_count += 1

    if merged_count != record_count:
        raise FinanceArtifactVerificationError("manifest total record count mismatch")
