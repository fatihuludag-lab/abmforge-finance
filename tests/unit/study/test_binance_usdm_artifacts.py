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


def test_raw_record_validation_edges_v2() -> None:
    from typing import cast

    from abmforge_finance.exceptions import InvalidFinanceArtifactError
    from abmforge_finance.study.binance_usdm_artifacts import (
        BinanceUsdMRawChannel,
        BinanceUsdMRawRecord,
    )

    with pytest.raises(
        InvalidFinanceArtifactError,
        match="sequence_number",
    ):
        BinanceUsdMRawRecord(
            sequence_number=-1,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=1,
            raw_json="{}",
        )

    with pytest.raises(
        TypeError,
        match="channel",
    ):
        BinanceUsdMRawRecord(
            sequence_number=0,
            channel=cast(
                BinanceUsdMRawChannel,
                "depth_update",
            ),
            received_at_ns=1,
            raw_json="{}",
        )

    with pytest.raises(
        InvalidFinanceArtifactError,
        match="received_at_ns",
    ):
        BinanceUsdMRawRecord(
            sequence_number=0,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=-1,
            raw_json="{}",
        )

    with pytest.raises(
        InvalidFinanceArtifactError,
        match="raw_json",
    ):
        BinanceUsdMRawRecord(
            sequence_number=0,
            channel=BinanceUsdMRawChannel.DEPTH_UPDATE,
            received_at_ns=1,
            raw_json="",
        )


def test_capture_provenance_validation_edges_v2() -> None:
    from typing import Any, cast

    from abmforge_finance.exceptions import InvalidFinanceArtifactError
    from abmforge_finance.study.binance_usdm_artifacts import (
        BinanceUsdMCaptureProvenance,
    )

    provenance_factory = cast(
        Any,
        BinanceUsdMCaptureProvenance,
    )

    base = {
        "capture_id": "capture",
        "candidate_id": "candidate",
        "repository_commit_sha": "a" * 40,
        "started_at_ns": 1,
        "ended_at_ns": 2,
    }

    for field in (
        "capture_id",
        "candidate_id",
    ):
        values = dict(base)
        values[field] = ""

        with pytest.raises(
            InvalidFinanceArtifactError,
            match=field,
        ):
            provenance_factory(
                **values,
            )

    for field in (
        "started_at_ns",
        "ended_at_ns",
    ):
        values = dict(base)
        values[field] = -1

        with pytest.raises(
            InvalidFinanceArtifactError,
            match=field,
        ):
            provenance_factory(
                **values,
            )

    with pytest.raises(
        InvalidFinanceArtifactError,
        match="greater than",
    ):
        BinanceUsdMCaptureProvenance(
            capture_id="capture",
            candidate_id="candidate",
            repository_commit_sha="a" * 40,
            started_at_ns=10,
            ended_at_ns=10,
        )


def test_writer_input_validation_edges_v2(
    tmp_path: Path,
) -> None:
    from typing import cast

    from abmforge_finance.exceptions import InvalidFinanceArtifactError
    from abmforge_finance.study.binance_usdm_artifacts import (
        BinanceUsdMCaptureProvenance,
        BinanceUsdMRawRecord,
        write_binance_usdm_raw_capture,
    )

    provenance = BinanceUsdMCaptureProvenance(
        capture_id="capture",
        candidate_id="candidate",
        repository_commit_sha="a" * 40,
        started_at_ns=1,
        ended_at_ns=2,
    )

    with pytest.raises(
        TypeError,
        match="records must be a tuple",
    ):
        write_binance_usdm_raw_capture(
            cast(
                tuple[BinanceUsdMRawRecord, ...],
                [],
            ),
            tmp_path / "bad-list",
            provenance=provenance,
        )

    with pytest.raises(
        InvalidFinanceArtifactError,
        match="at least one record",
    ):
        write_binance_usdm_raw_capture(
            (),
            tmp_path / "empty",
            provenance=provenance,
        )

    with pytest.raises(
        TypeError,
        match=r"records\[0\]",
    ):
        write_binance_usdm_raw_capture(
            (
                cast(
                    BinanceUsdMRawRecord,
                    object(),
                ),
            ),
            tmp_path / "bad-record",
            provenance=provenance,
        )

    with pytest.raises(
        TypeError,
        match="provenance",
    ):
        write_binance_usdm_raw_capture(
            _records(),
            tmp_path / "bad-provenance",
            provenance=cast(
                BinanceUsdMCaptureProvenance,
                object(),
            ),
        )


def test_verifier_manifest_integrity_edges_v3(
    tmp_path: Path,
) -> None:
    import json
    import shutil

    import abmforge_finance.study.binance_usdm_artifacts as artifacts
    from abmforge_finance.exceptions import (
        FinanceArtifactVerificationError,
    )

    def make(name: str) -> Path:
        return write_binance_usdm_raw_capture(
            _records(),
            tmp_path / name,
            provenance=_provenance(),
        )

    def manifest(target: Path) -> dict[str, object]:
        value = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        return value

    def rewrite(
        target: Path,
        value: dict[str, object],
    ) -> None:
        (target / "manifest.json").write_bytes(artifacts._manifest_bytes(value))

    target = make("missing-manifest")
    (target / "manifest.json").unlink()

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="missing manifest",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("invalid-json")
    (target / "manifest.json").write_text(
        "{",
        encoding="utf-8",
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="invalid JSON",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("manifest-not-object")
    (target / "manifest.json").write_text(
        "[]",
        encoding="utf-8",
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="must contain an object",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("noncanonical-manifest")
    value = manifest(target)
    (target / "manifest.json").write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="not canonical",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("bad-schema")
    value = manifest(target)
    value["artifact_schema_version"] = "wrong"
    rewrite(target, value)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="unsupported",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("bad-contract")
    value = manifest(target)
    contract = value["contract"]
    assert isinstance(contract, dict)
    contract["symbol"] = "ETHUSDT"
    rewrite(target, value)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="frozen contract",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("bad-producer")
    value = manifest(target)
    value["producer"] = {}
    rewrite(target, value)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="producer metadata",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("bad-provenance")
    value = manifest(target)
    value["provenance"] = {}
    rewrite(target, value)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="provenance",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("bad-record-count")
    value = manifest(target)
    value["record_count"] = 0
    rewrite(target, value)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="record count",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("bad-membership")
    value = manifest(target)
    value["files"] = {}
    rewrite(target, value)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="file membership",
    ):
        verify_binance_usdm_raw_capture(target)

    # Keep shutil referenced for Ruff/static tooling in environments
    # where temporary artifact cleanup instrumentation is enabled.
    assert shutil is not None


def test_verifier_file_metadata_integrity_edges_v3(
    tmp_path: Path,
) -> None:
    import json

    import abmforge_finance.study.binance_usdm_artifacts as artifacts
    from abmforge_finance.exceptions import (
        FinanceArtifactVerificationError,
    )

    def make(name: str) -> Path:
        return write_binance_usdm_raw_capture(
            _records(),
            tmp_path / name,
            provenance=_provenance(),
        )

    def load(target: Path) -> dict[str, object]:
        value = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        return value

    def rewrite(
        target: Path,
        value: dict[str, object],
    ) -> None:
        (target / "manifest.json").write_bytes(artifacts._manifest_bytes(value))

    channel = BinanceUsdMRawChannel.DEPTH_UPDATE.value

    target = make("metadata-not-object")
    value = load(target)
    files = value["files"]
    assert isinstance(files, dict)
    files[channel] = "bad"
    rewrite(target, value)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="invalid file metadata",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("metadata-invalid-records")
    value = load(target)
    files = value["files"]
    assert isinstance(files, dict)
    metadata = files[channel]
    assert isinstance(metadata, dict)
    metadata["records"] = -1
    rewrite(target, value)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="invalid file metadata",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("metadata-count-mismatch")
    value = load(target)
    files = value["files"]
    assert isinstance(files, dict)
    metadata = files[channel]
    assert isinstance(metadata, dict)
    count = metadata["records"]
    assert isinstance(count, int)
    metadata["records"] = count + 1
    rewrite(target, value)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="record count mismatch",
    ):
        verify_binance_usdm_raw_capture(target)


def test_verifier_jsonl_integrity_edges_v3(
    tmp_path: Path,
) -> None:
    import hashlib
    import json

    import abmforge_finance.study.binance_usdm_artifacts as artifacts
    from abmforge_finance.exceptions import (
        FinanceArtifactVerificationError,
    )

    def make(name: str) -> Path:
        return write_binance_usdm_raw_capture(
            _records(),
            tmp_path / name,
            provenance=_provenance(),
        )

    def mutate_file(
        target: Path,
        *,
        payload: bytes,
    ) -> None:
        manifest_path = target / "manifest.json"

        value = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert isinstance(value, dict)

        files = value["files"]
        assert isinstance(files, dict)

        metadata = files[BinanceUsdMRawChannel.DEPTH_UPDATE.value]
        assert isinstance(metadata, dict)

        filename = metadata["path"]
        assert isinstance(filename, str)

        (target / filename).write_bytes(payload)

        metadata["sha256"] = hashlib.sha256(payload).hexdigest()

        manifest_path.write_bytes(artifacts._manifest_bytes(value))

    target = make("crlf-jsonl")
    source = target / "depth_updates.jsonl"
    payload = source.read_bytes().replace(
        b"\n",
        b"\r\n",
    )
    mutate_file(
        target,
        payload=payload,
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="LF line endings",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("invalid-jsonl")
    source = target / "depth_updates.jsonl"
    lines = source.read_bytes().splitlines(keepends=True)
    assert lines

    lines[0] = b"{\n"

    mutate_file(
        target,
        payload=b"".join(lines),
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="contains invalid JSON",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("invalid-columns")
    source = target / "depth_updates.jsonl"
    lines = source.read_bytes().splitlines(keepends=True)
    assert lines

    row = {
        "wrong": 1,
    }

    lines[0] = (
        json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()

    mutate_file(
        target,
        payload=b"".join(lines),
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="columns are invalid",
    ):
        verify_binance_usdm_raw_capture(target)


def test_artifact_writer_rollback_and_contract_guard_v4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from abmforge_finance.exceptions import (
        InvalidFinanceArtifactError,
    )
    from abmforge_finance.study.binance_usdm_contract import (
        binance_usdm_empirical_contract,
    )

    contract = binance_usdm_empirical_contract()

    object.__setattr__(
        contract,
        "contract_id",
        "wrong-contract",
    )

    with pytest.raises(
        InvalidFinanceArtifactError,
        match="unexpected empirical contract id",
    ):
        write_binance_usdm_raw_capture(
            _records(),
            tmp_path / "bad-contract",
            provenance=_provenance(),
            contract=contract,
        )

    target = tmp_path / "rollback"

    monkeypatch.setattr(
        "abmforge_finance.study.binance_usdm_artifacts.os.replace",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("forced replace failure")),
    )

    with pytest.raises(
        OSError,
        match="forced replace failure",
    ):
        write_binance_usdm_raw_capture(
            _records(),
            target,
            provenance=_provenance(),
        )

    assert not target.exists()


def test_artifact_remaining_integrity_edges_v4(
    tmp_path: Path,
) -> None:
    import hashlib
    import json

    import abmforge_finance.study.binance_usdm_artifacts as artifacts
    from abmforge_finance.exceptions import (
        FinanceArtifactVerificationError,
    )

    def make(name: str) -> Path:
        return write_binance_usdm_raw_capture(
            _records(),
            tmp_path / name,
            provenance=_provenance(),
        )

    def load_manifest(
        target: Path,
    ) -> dict[str, object]:
        value = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        assert isinstance(value, dict)
        return value

    def save_manifest(
        target: Path,
        value: dict[str, object],
    ) -> None:
        (target / "manifest.json").write_bytes(artifacts._manifest_bytes(value))

    def rewrite_channel_rows(
        target: Path,
        channel: BinanceUsdMRawChannel,
        rows: list[dict[str, object]],
    ) -> None:
        manifest = load_manifest(target)
        files = manifest["files"]
        assert isinstance(files, dict)

        metadata = files[channel.value]
        assert isinstance(metadata, dict)

        filename = metadata["path"]
        assert isinstance(filename, str)

        payload = (
            "".join(
                json.dumps(
                    row,
                    separators=(",", ":"),
                )
                + "\n"
                for row in rows
            )
        ).encode()

        (target / filename).write_bytes(payload)

        metadata["records"] = len(rows)
        metadata["sha256"] = hashlib.sha256(payload).hexdigest()

        save_manifest(
            target,
            manifest,
        )

    def channel_rows(
        target: Path,
        channel: BinanceUsdMRawChannel,
    ) -> list[dict[str, object]]:
        manifest = load_manifest(target)
        files = manifest["files"]
        assert isinstance(files, dict)

        metadata = files[channel.value]
        assert isinstance(metadata, dict)

        filename = metadata["path"]
        assert isinstance(filename, str)

        output = []

        for line in (target / filename).read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            assert isinstance(value, dict)
            output.append(value)

        return output

    target = make("noncanonical-jsonl")
    channel = BinanceUsdMRawChannel.DEPTH_UPDATE
    manifest = load_manifest(target)
    files = manifest["files"]
    assert isinstance(files, dict)
    metadata = files[channel.value]
    assert isinstance(metadata, dict)
    filename = metadata["path"]
    assert isinstance(filename, str)

    rows = channel_rows(
        target,
        channel,
    )

    payload = ("".join(json.dumps(row) + "\n" for row in rows)).encode()

    (target / filename).write_bytes(payload)
    metadata["sha256"] = hashlib.sha256(payload).hexdigest()
    save_manifest(target, manifest)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="not canonical JSONL",
    ):
        verify_binance_usdm_raw_capture(target)

    for name, field_value, message in (
        (
            "invalid-metadata",
            -1,
            "invalid record metadata",
        ),
        (
            "invalid-raw-json",
            "{",
            "invalid raw_json",
        ),
        (
            "nonobject-raw-json",
            "[]",
            "raw_json must contain an object",
        ),
    ):
        target = make(name)
        rows = channel_rows(
            target,
            channel,
        )

        if name == "invalid-metadata":
            rows[0]["sequence_number"] = field_value
        else:
            rows[0]["raw_json"] = field_value

        rewrite_channel_rows(
            target,
            channel,
            rows,
        )

        with pytest.raises(
            FinanceArtifactVerificationError,
            match=message,
        ):
            verify_binance_usdm_raw_capture(target)

    target = make("provenance-not-object")
    manifest = load_manifest(target)
    manifest["provenance"] = "bad"
    save_manifest(target, manifest)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="invalid raw capture provenance",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("total-count-mismatch")
    manifest = load_manifest(target)
    record_count = manifest["record_count"]
    assert isinstance(record_count, int)
    manifest["record_count"] = record_count + 1
    save_manifest(target, manifest)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="total record count mismatch",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("zero-snapshots")
    snapshot_channel = BinanceUsdMRawChannel.DEPTH_SNAPSHOT
    manifest = load_manifest(target)
    files = manifest["files"]
    assert isinstance(files, dict)
    metadata = files[snapshot_channel.value]
    assert isinstance(metadata, dict)
    filename = metadata["path"]
    assert isinstance(filename, str)

    (target / filename).write_bytes(b"")
    metadata["records"] = 0
    metadata["sha256"] = hashlib.sha256(b"").hexdigest()

    record_count = manifest["record_count"]
    assert isinstance(record_count, int)
    manifest["record_count"] = record_count - 1

    save_manifest(target, manifest)

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="exactly one depth snapshot",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("duplicate-sequence")

    snapshot_rows = channel_rows(
        target,
        snapshot_channel,
    )
    trade_channel = BinanceUsdMRawChannel.AGGREGATE_TRADE
    trade_rows = channel_rows(
        target,
        trade_channel,
    )

    assert snapshot_rows
    assert trade_rows

    trade_rows[0]["sequence_number"] = snapshot_rows[0]["sequence_number"]

    rewrite_channel_rows(
        target,
        trade_channel,
        trade_rows,
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="not unique",
    ):
        verify_binance_usdm_raw_capture(target)

    target = make("decreasing-receipt-time")

    channels = (
        BinanceUsdMRawChannel.DEPTH_UPDATE,
        BinanceUsdMRawChannel.AGGREGATE_TRADE,
        BinanceUsdMRawChannel.DEPTH_SNAPSHOT,
    )

    candidates = []

    for candidate_channel in channels:
        for row in channel_rows(
            target,
            candidate_channel,
        ):
            sequence_number = row["sequence_number"]
            assert isinstance(sequence_number, int)

            candidates.append(
                (
                    sequence_number,
                    candidate_channel,
                    row,
                )
            )

    candidates.sort(key=lambda item: item[0])

    assert len(candidates) >= 2

    _, last_channel, last_row = candidates[-1]

    rows = channel_rows(
        target,
        last_channel,
    )

    target_sequence = last_row["sequence_number"]

    for row in rows:
        if row["sequence_number"] == target_sequence:
            row["received_at_ns"] = 0

    rewrite_channel_rows(
        target,
        last_channel,
        rows,
    )

    with pytest.raises(
        FinanceArtifactVerificationError,
        match="receipt timestamps decrease",
    ):
        verify_binance_usdm_raw_capture(target)
