"""Deterministic finance research artifact serialization and verification."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TypeAlias, cast

from abmforge_finance.exceptions import (
    FinanceArtifactExistsError,
    FinanceArtifactVerificationError,
    InvalidFinanceArtifactError,
)
from abmforge_finance.recording.dataset import FinanceResearchDataset
from abmforge_finance.recording.schema import (
    FINANCE_DATASET_SCHEMA_VERSION,
    AccountRecord,
    CancellationRecord,
    DecisionRecord,
    MarketStateRecord,
    OrderRecord,
    ParticipantRecord,
    PositionRecord,
    TradeRecord,
)

FINANCE_ARTIFACT_SCHEMA_VERSION = "1.1"

try:
    _PACKAGE_VERSION = version("abmforge-finance")
except PackageNotFoundError:  # pragma: no cover
    _PACKAGE_VERSION = "0.1.0a0"

FinanceRecord: TypeAlias = (
    ParticipantRecord
    | DecisionRecord
    | CancellationRecord
    | OrderRecord
    | TradeRecord
    | MarketStateRecord
    | AccountRecord
    | PositionRecord
)

_TABLE_ORDER = (
    "participants",
    "decisions",
    "cancellations",
    "orders",
    "trades",
    "market_states",
    "accounts",
    "positions",
)
_TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "participants": (
        "agent_id",
        "policy_type",
        "instrument_id",
        "initial_cash",
        "initial_inventory",
    ),
    "decisions": (
        "period",
        "agent_id",
        "kind",
        "side",
        "order_type",
        "quantity",
        "price",
        "time_in_force",
    ),
    "cancellations": (
        "period",
        "sequence_number",
        "agent_id",
        "order_id",
        "order_sequence_number",
        "instrument_id",
        "side",
        "limit_price",
        "cancelled_quantity",
    ),
    "orders": (
        "period",
        "order_id",
        "sequence_number",
        "agent_id",
        "instrument_id",
        "side",
        "order_type",
        "quantity",
        "limit_price",
        "submitted_at",
        "time_in_force",
        "accepted",
        "executed_quantity",
        "remaining_quantity",
        "cancelled_quantity",
        "rested",
        "rejection_type",
        "rejection_message",
    ),
    "trades": (
        "period",
        "trade_id",
        "sequence_number",
        "instrument_id",
        "buy_order_id",
        "sell_order_id",
        "buyer_id",
        "seller_id",
        "maker_order_id",
        "taker_order_id",
        "price",
        "quantity",
        "executed_at",
        "buyer_fee",
        "seller_fee",
    ),
    "market_states": (
        "period",
        "instrument_id",
        "fundamental_value",
        "best_bid",
        "best_ask",
        "mid_price",
        "spread",
        "bid_depth",
        "ask_depth",
        "imbalance",
        "order_count",
        "last_trade_price",
        "price_change",
        "fee_balance",
    ),
    "accounts": ("period", "phase", "agent_id", "cash"),
    "positions": ("period", "phase", "agent_id", "instrument_id", "quantity"),
}
_PHASE_RANK = {"initial": 0, "post": 1}


@dataclass(frozen=True, slots=True)
class FinanceArtifactConfig:
    """Select deterministic text artifact formats."""

    write_jsonl: bool = True
    write_csv: bool = True

    def __post_init__(self) -> None:
        if not self.write_jsonl and not self.write_csv:
            raise InvalidFinanceArtifactError("at least one artifact format must be enabled")


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidFinanceArtifactError("non-finite float values cannot be serialized")
        return value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise InvalidFinanceArtifactError(f"unsupported artifact scalar: {type(value).__name__}")


def _csv_value(value: object) -> str:
    value = _json_value(value)
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    return str(value)


def _rows(dataset: FinanceResearchDataset, table: str) -> tuple[FinanceRecord, ...]:
    if table == "participants":
        return tuple(sorted(dataset.participants, key=lambda row: row.agent_id))
    if table == "decisions":
        return tuple(sorted(dataset.decisions, key=lambda row: (row.period, row.agent_id)))
    if table == "cancellations":
        return tuple(
            sorted(
                dataset.cancellations,
                key=lambda row: (row.period, row.sequence_number, row.order_id),
            )
        )
    if table == "orders":
        return tuple(
            sorted(dataset.orders, key=lambda row: (row.period, row.sequence_number, row.order_id))
        )
    if table == "trades":
        return tuple(
            sorted(dataset.trades, key=lambda row: (row.period, row.sequence_number, row.trade_id))
        )
    if table == "market_states":
        return tuple(sorted(dataset.market_states, key=lambda row: row.period))
    if table == "accounts":
        return tuple(
            sorted(
                dataset.accounts, key=lambda row: (row.period, _PHASE_RANK[row.phase], row.agent_id)
            )
        )
    if table == "positions":
        return tuple(
            sorted(
                dataset.positions,
                key=lambda row: (
                    row.period,
                    _PHASE_RANK[row.phase],
                    row.agent_id,
                    row.instrument_id,
                ),
            )
        )
    raise InvalidFinanceArtifactError(f"unknown artifact table: {table!r}")


def _jsonl(rows: tuple[FinanceRecord, ...], columns: tuple[str, ...]) -> bytes:
    lines = []
    for row in rows:
        values = {column: _json_value(getattr(row, column)) for column in columns}
        lines.append(json.dumps(values, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return (("\n".join(lines) + "\n") if lines else "").encode()


def _csv(rows: tuple[FinanceRecord, ...], columns: tuple[str, ...]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(_csv_value(getattr(row, column)) for column in columns)
    return stream.getvalue().encode()


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest_bytes(manifest: dict[str, object]) -> bytes:
    text = json.dumps(
        manifest, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )
    return f"{text}\n".encode()


def write_finance_artifacts(
    dataset: FinanceResearchDataset,
    directory: str | Path,
    *,
    provenance: Mapping[str, str] | None = None,
    config: FinanceArtifactConfig | None = None,
) -> Path:
    """Atomically create a new canonical research-artifact directory."""

    if not isinstance(dataset, FinanceResearchDataset):
        raise TypeError("dataset must be a FinanceResearchDataset")
    dataset.validate()
    selected = FinanceArtifactConfig() if config is None else config
    if not isinstance(selected, FinanceArtifactConfig):
        raise TypeError("config must be a FinanceArtifactConfig")

    metadata = {} if provenance is None else dict(provenance)
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()):
        raise InvalidFinanceArtifactError("provenance must map strings to strings")

    target = Path(directory)
    if target.exists():
        raise FinanceArtifactExistsError(f"artifact directory already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{target.name}.tmp-", dir=target.parent))

    try:
        tables: dict[str, object] = {}
        for table in _TABLE_ORDER:
            rows = _rows(dataset, table)
            columns = _TABLE_COLUMNS[table]
            files: dict[str, object] = {}
            for file_format, enabled, serializer in (
                ("jsonl", selected.write_jsonl, _jsonl),
                ("csv", selected.write_csv, _csv),
            ):
                if not enabled:
                    continue
                payload = serializer(rows, columns)
                filename = f"{table}.{file_format}"
                (temp / filename).write_bytes(payload)
                files[file_format] = {"path": filename, "sha256": _digest(payload)}
            tables[table] = {"columns": list(columns), "rows": len(rows), "files": files}

        manifest: dict[str, object] = {
            "artifact_schema_version": FINANCE_ARTIFACT_SCHEMA_VERSION,
            "finance_dataset_schema_version": dataset.schema_version,
            "producer": {"name": "abmforge-finance", "version": _PACKAGE_VERSION},
            "provenance": dict(sorted(metadata.items())),
            "tables": tables,
        }
        (temp / "manifest.json").write_bytes(_manifest_bytes(manifest))
        os.replace(temp, target)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
    return target


def _verify_jsonl(path: Path, columns: tuple[str, ...], rows: int) -> None:
    payload = path.read_bytes()
    if b"\r\n" in payload:
        raise FinanceArtifactVerificationError(f"{path.name} must use LF line endings")
    lines = payload.splitlines()
    if len(lines) != rows:
        raise FinanceArtifactVerificationError(f"{path.name} row count mismatch")
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FinanceArtifactVerificationError(f"{path.name} contains invalid JSON") from exc
        if not isinstance(value, dict) or tuple(value) != columns:
            raise FinanceArtifactVerificationError(f"{path.name} columns are invalid")
        canonical = json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode()
        if canonical != line:
            raise FinanceArtifactVerificationError(f"{path.name} is not canonical JSONL")


def _verify_csv(path: Path, columns: tuple[str, ...], rows: int) -> None:
    payload = path.read_bytes()
    try:
        parsed = list(csv.reader(io.StringIO(payload.decode("utf-8"), newline="")))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise FinanceArtifactVerificationError(f"{path.name} is invalid CSV") from exc
    if not parsed or tuple(parsed[0]) != columns or len(parsed) - 1 != rows:
        raise FinanceArtifactVerificationError(f"{path.name} header or row count is invalid")
    if any(len(row) != len(columns) for row in parsed[1:]):
        raise FinanceArtifactVerificationError(f"{path.name} has an invalid row width")
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(parsed)
    if stream.getvalue().encode() != payload:
        raise FinanceArtifactVerificationError(f"{path.name} is not canonical CSV")


def verify_finance_artifacts(directory: str | Path) -> None:
    """Verify manifest contract, file membership, hashes, and canonical encodings."""

    root = Path(directory)
    manifest_path = root / "manifest.json"
    if not root.is_dir() or not manifest_path.is_file():
        raise FinanceArtifactVerificationError("artifact directory is missing manifest.json")

    payload = manifest_path.read_bytes()
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise FinanceArtifactVerificationError("manifest.json is invalid JSON") from exc
    if not isinstance(value, dict):
        raise FinanceArtifactVerificationError("manifest.json must contain an object")
    manifest = cast(dict[str, object], value)
    if _manifest_bytes(manifest) != payload:
        raise FinanceArtifactVerificationError("manifest.json is not canonical")
    if manifest.get("artifact_schema_version") != FINANCE_ARTIFACT_SCHEMA_VERSION:
        raise FinanceArtifactVerificationError("unsupported artifact schema")
    if manifest.get("finance_dataset_schema_version") != FINANCE_DATASET_SCHEMA_VERSION:
        raise FinanceArtifactVerificationError("unsupported finance dataset schema")

    producer = manifest.get("producer")
    provenance = manifest.get("provenance")
    tables = manifest.get("tables")
    if (
        not isinstance(producer, dict)
        or producer.get("name") != "abmforge-finance"
        or not isinstance(producer.get("version"), str)
    ):
        raise FinanceArtifactVerificationError("invalid producer metadata")
    if not isinstance(provenance, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in provenance.items()
    ):
        raise FinanceArtifactVerificationError("invalid provenance metadata")
    if not isinstance(tables, dict) or set(tables) != set(_TABLE_ORDER):
        raise FinanceArtifactVerificationError("invalid table membership")

    expected = {"manifest.json"}
    for table in _TABLE_ORDER:
        table_value = tables[table]
        if not isinstance(table_value, dict):
            raise FinanceArtifactVerificationError(f"invalid manifest entry for {table}")
        columns_value = table_value.get("columns")
        rows_value = table_value.get("rows")
        files_value = table_value.get("files")
        if (
            not isinstance(columns_value, list)
            or not all(isinstance(column, str) for column in columns_value)
            or tuple(columns_value) != _TABLE_COLUMNS[table]
            or isinstance(rows_value, bool)
            or not isinstance(rows_value, int)
            or rows_value < 0
            or not isinstance(files_value, dict)
            or not files_value
            or not set(files_value).issubset({"jsonl", "csv"})
        ):
            raise FinanceArtifactVerificationError(f"invalid manifest schema for {table}")

        columns = tuple(columns_value)
        for file_format, verifier in (("jsonl", _verify_jsonl), ("csv", _verify_csv)):
            if file_format not in files_value:
                continue
            file_value = files_value[file_format]
            if not isinstance(file_value, dict):
                raise FinanceArtifactVerificationError(f"invalid file metadata for {table}")
            filename = file_value.get("path")
            digest = file_value.get("sha256")
            expected_name = f"{table}.{file_format}"
            if filename != expected_name or not isinstance(digest, str):
                raise FinanceArtifactVerificationError(f"invalid file metadata for {table}")
            path = root / expected_name
            if not path.is_file() or _digest(path.read_bytes()) != digest:
                raise FinanceArtifactVerificationError(f"integrity failure for {expected_name}")
            verifier(path, columns, rows_value)
            expected.add(expected_name)

    actual = {path.name for path in root.iterdir()}
    if actual != expected or any(path.is_dir() for path in root.iterdir()):
        raise FinanceArtifactVerificationError("artifact directory membership is invalid")
