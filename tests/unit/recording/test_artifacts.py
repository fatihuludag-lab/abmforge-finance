"""Unit tests for canonical finance research artifacts."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from abmforge_finance.exceptions import (
    FinanceArtifactExistsError,
    FinanceArtifactVerificationError,
    InvalidFinanceArtifactError,
)
from abmforge_finance.recording import (
    AccountRecord,
    DecisionRecord,
    FinanceArtifactConfig,
    FinanceResearchDataset,
    MarketStateRecord,
    OrderRecord,
    ParticipantRecord,
    PositionRecord,
    TradeRecord,
    verify_finance_artifacts,
    write_finance_artifacts,
)


def _dataset(*, submitted_at: int | float = 0) -> FinanceResearchDataset:
    return FinanceResearchDataset(
        participants=(
            ParticipantRecord("b", "PolicyB", "ACME", Decimal("200.00"), Decimal("2")),
            ParticipantRecord("a", "PolicyA", "ACME", Decimal("100.00"), Decimal("0")),
        ),
        decisions=(
            DecisionRecord(0, "b", "hold", None, None, None, None, None),
            DecisionRecord(
                0,
                "a",
                "submit_order",
                "buy",
                "limit",
                Decimal("1"),
                Decimal("99.00"),
                "gtc",
            ),
        ),
        orders=(
            OrderRecord(
                0,
                "order-1",
                1,
                "a",
                "ACME",
                "buy",
                "limit",
                Decimal("1"),
                Decimal("99.00"),
                submitted_at,
                "gtc",
                True,
                Decimal("0"),
                Decimal("1"),
                Decimal("0"),
                True,
                None,
                None,
            ),
        ),
        trades=(
            TradeRecord(
                1,
                "trade-1",
                2,
                "ACME",
                "order-1",
                "order-2",
                "a",
                "b",
                "order-1",
                "order-2",
                Decimal("99.00"),
                Decimal("1"),
                1,
                Decimal("0.10"),
                Decimal("-0.05"),
            ),
        ),
        market_states=(
            MarketStateRecord(
                0,
                "ACME",
                Decimal("100.00"),
                Decimal("99.00"),
                Decimal("101.00"),
                Decimal("100.00"),
                Decimal("2.00"),
                Decimal("1"),
                Decimal("2"),
                Decimal("-0.333333333333333333"),
                2,
                None,
                None,
                Decimal("0"),
            ),
        ),
        accounts=(
            AccountRecord(0, "post", "b", Decimal("200.00")),
            AccountRecord(0, "initial", "a", Decimal("100.00")),
            AccountRecord(0, "initial", "b", Decimal("200.00")),
            AccountRecord(0, "post", "a", Decimal("100.00")),
        ),
        positions=(
            PositionRecord(0, "post", "b", "ACME", Decimal("2")),
            PositionRecord(0, "initial", "a", "ACME", Decimal("0")),
            PositionRecord(0, "initial", "b", "ACME", Decimal("2")),
            PositionRecord(0, "post", "a", "ACME", Decimal("0")),
        ),
    )


def _canonical_manifest(path: Path, manifest: dict[str, object]) -> None:
    payload = (
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    path.write_bytes(payload)


def test_default_bundle_is_canonical_and_verifiable(tmp_path: Path) -> None:
    target = write_finance_artifacts(
        _dataset(),
        tmp_path / "run",
        provenance={"git_commit": "abc123", "model_seed": "42"},
    )
    verify_finance_artifacts(target)

    assert len(list(target.iterdir())) == 17
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["artifact_schema_version"] == "1.1"
    assert manifest["finance_dataset_schema_version"] == "1.1"
    assert manifest["provenance"] == {"git_commit": "abc123", "model_seed": "42"}

    participants = [
        json.loads(line)
        for line in (target / "participants.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["agent_id"] for row in participants] == ["a", "b"]
    assert participants[0]["initial_cash"] == "100.00"
    assert b"\r\n" not in (target / "participants.csv").read_bytes()


def test_jsonl_only_bundle_is_supported(tmp_path: Path) -> None:
    target = write_finance_artifacts(
        _dataset(),
        tmp_path / "run",
        config=FinanceArtifactConfig(write_csv=False),
    )
    verify_finance_artifacts(target)
    assert len(list(target.iterdir())) == 9
    assert not (target / "orders.csv").exists()


def test_config_requires_at_least_one_format() -> None:
    with pytest.raises(InvalidFinanceArtifactError, match="at least one"):
        FinanceArtifactConfig(write_jsonl=False, write_csv=False)


def test_writer_rejects_existing_directory(tmp_path: Path) -> None:
    target = tmp_path / "run"
    target.mkdir()
    with pytest.raises(FinanceArtifactExistsError):
        write_finance_artifacts(_dataset(), target)


def test_writer_rejects_invalid_provenance_and_argument_types(tmp_path: Path) -> None:
    with pytest.raises(InvalidFinanceArtifactError, match="provenance"):
        write_finance_artifacts(
            _dataset(),
            tmp_path / "bad-provenance",
            provenance={"seed": 42},  # type: ignore[dict-item]
        )
    with pytest.raises(TypeError, match="dataset"):
        write_finance_artifacts(object(), tmp_path / "bad-dataset")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="config"):
        write_finance_artifacts(
            _dataset(),
            tmp_path / "bad-config",
            config=object(),  # type: ignore[arg-type]
        )


def test_non_finite_time_is_not_serialized(tmp_path: Path) -> None:
    with pytest.raises(InvalidFinanceArtifactError, match="non-finite"):
        write_finance_artifacts(_dataset(submitted_at=float("nan")), tmp_path / "run")
    assert not (tmp_path / "run").exists()


def test_verifier_detects_payload_tampering(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    with (target / "orders.jsonl").open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(FinanceArtifactVerificationError, match="integrity"):
        verify_finance_artifacts(target)


def test_verifier_detects_noncanonical_manifest(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with pytest.raises(FinanceArtifactVerificationError, match="canonical"):
        verify_finance_artifacts(target)


def test_verifier_detects_unsupported_schema_with_canonical_manifest(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_schema_version"] = "9.9"
    _canonical_manifest(manifest_path, manifest)
    with pytest.raises(FinanceArtifactVerificationError, match="unsupported artifact"):
        verify_finance_artifacts(target)


def test_verifier_detects_unexpected_files_and_missing_manifest(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    (target / "unexpected.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FinanceArtifactVerificationError, match="membership"):
        verify_finance_artifacts(target)

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FinanceArtifactVerificationError, match="manifest"):
        verify_finance_artifacts(empty)


def test_verifier_checks_row_count_even_when_manifest_hash_is_updated(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    data_path = target / "orders.jsonl"
    data_path.write_bytes(b"")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["orders"]["files"]["jsonl"]["sha256"] = hashlib.sha256(b"").hexdigest()
    _canonical_manifest(manifest_path, manifest)
    with pytest.raises(FinanceArtifactVerificationError, match="row count"):
        verify_finance_artifacts(target)


def test_finite_float_time_serializes_and_verifies(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(submitted_at=0.5), tmp_path / "run")
    verify_finance_artifacts(target)
    order = json.loads((target / "orders.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert order["submitted_at"] == 0.5


def test_verifier_checks_jsonl_canonical_encoding_after_hash_update(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    data_path = target / "orders.jsonl"
    parsed = json.loads(data_path.read_text(encoding="utf-8"))
    payload = (json.dumps(parsed, indent=2) + "\n").encode("utf-8")
    data_path.write_bytes(payload)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["orders"]["files"]["jsonl"]["sha256"] = hashlib.sha256(payload).hexdigest()
    _canonical_manifest(manifest_path, manifest)
    with pytest.raises(FinanceArtifactVerificationError):
        verify_finance_artifacts(target)


def test_verifier_checks_csv_canonical_encoding_after_hash_update(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    data_path = target / "orders.csv"
    payload = data_path.read_bytes().replace(b"\n", b"\r\n")
    data_path.write_bytes(payload)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["orders"]["files"]["csv"]["sha256"] = hashlib.sha256(payload).hexdigest()
    _canonical_manifest(manifest_path, manifest)
    with pytest.raises(FinanceArtifactVerificationError, match="canonical CSV"):
        verify_finance_artifacts(target)


def test_verifier_rejects_invalid_producer_metadata(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["producer"] = {"name": "wrong-producer", "version": "1.0"}
    _canonical_manifest(manifest_path, manifest)

    with pytest.raises(FinanceArtifactVerificationError, match="producer"):
        verify_finance_artifacts(target)


def test_verifier_rejects_invalid_provenance_metadata(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["provenance"] = {"model_seed": 42}
    _canonical_manifest(manifest_path, manifest)

    with pytest.raises(FinanceArtifactVerificationError, match="provenance"):
        verify_finance_artifacts(target)


def test_verifier_rejects_invalid_table_membership(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    del manifest["tables"]["positions"]
    _canonical_manifest(manifest_path, manifest)

    with pytest.raises(FinanceArtifactVerificationError, match="table membership"):
        verify_finance_artifacts(target)


def test_verifier_rejects_non_object_table_entry(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["orders"] = []
    _canonical_manifest(manifest_path, manifest)

    with pytest.raises(FinanceArtifactVerificationError, match="manifest entry"):
        verify_finance_artifacts(target)


def test_verifier_rejects_negative_manifest_row_count(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["orders"]["rows"] = -1
    _canonical_manifest(manifest_path, manifest)

    with pytest.raises(FinanceArtifactVerificationError, match="manifest schema"):
        verify_finance_artifacts(target)


def test_verifier_rejects_non_object_file_metadata(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["orders"]["files"]["jsonl"] = []
    _canonical_manifest(manifest_path, manifest)

    with pytest.raises(FinanceArtifactVerificationError, match="file metadata"):
        verify_finance_artifacts(target)


def test_verifier_rejects_wrong_manifest_file_path(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["orders"]["files"]["jsonl"]["path"] = "wrong.jsonl"
    _canonical_manifest(manifest_path, manifest)

    with pytest.raises(FinanceArtifactVerificationError, match="file metadata"):
        verify_finance_artifacts(target)


def test_verifier_rejects_malformed_jsonl_after_hash_update(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    data_path = target / "orders.jsonl"
    payload = b"{not-json}\n"
    data_path.write_bytes(payload)

    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["orders"]["files"]["jsonl"]["sha256"] = hashlib.sha256(payload).hexdigest()
    _canonical_manifest(manifest_path, manifest)

    with pytest.raises(FinanceArtifactVerificationError, match="invalid JSON"):
        verify_finance_artifacts(target)


def test_verifier_rejects_wrong_jsonl_columns_after_hash_update(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    data_path = target / "orders.jsonl"
    payload = b'{"unexpected":"value"}\n'
    data_path.write_bytes(payload)

    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["orders"]["files"]["jsonl"]["sha256"] = hashlib.sha256(payload).hexdigest()
    _canonical_manifest(manifest_path, manifest)

    with pytest.raises(FinanceArtifactVerificationError, match="columns"):
        verify_finance_artifacts(target)


def test_verifier_rejects_invalid_csv_after_hash_update(tmp_path: Path) -> None:
    target = write_finance_artifacts(_dataset(), tmp_path / "run")
    data_path = target / "orders.csv"
    payload = b"\xff\n"
    data_path.write_bytes(payload)

    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tables"]["orders"]["files"]["csv"]["sha256"] = hashlib.sha256(payload).hexdigest()
    _canonical_manifest(manifest_path, manifest)

    with pytest.raises(FinanceArtifactVerificationError, match="invalid CSV"):
        verify_finance_artifacts(target)
