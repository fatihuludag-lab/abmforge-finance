"""Property tests for canonical finance artifact replay."""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from abmforge_finance.recording import (
    FinanceResearchDataset,
    ParticipantRecord,
    write_finance_artifacts,
)


@settings(deadline=None)
@given(order=st.permutations(("a", "b", "c")))
def test_semantic_participant_order_does_not_change_artifact_bytes(order: list[str]) -> None:
    rows = {
        "a": ParticipantRecord("a", "P", "ACME", Decimal("100.00"), Decimal("0")),
        "b": ParticipantRecord("b", "P", "ACME", Decimal("200.00"), Decimal("1")),
        "c": ParticipantRecord("c", "P", "ACME", Decimal("300.00"), Decimal("2")),
    }
    first = FinanceResearchDataset(participants=tuple(rows[agent_id] for agent_id in order))
    second = FinanceResearchDataset(participants=(rows["c"], rows["a"], rows["b"]))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        left = write_finance_artifacts(first, root / "left", provenance={"seed": "42"})
        right = write_finance_artifacts(second, root / "right", provenance={"seed": "42"})
        left_payloads = {path.name: path.read_bytes() for path in left.iterdir()}
        right_payloads = {path.name: path.read_bytes() for path in right.iterdir()}

    assert left_payloads == right_payloads


@settings(deadline=None)
@given(
    value=st.decimals(
        min_value=Decimal("-1000000"),
        max_value=Decimal("1000000"),
        allow_nan=False,
        allow_infinity=False,
        places=4,
    )
)
def test_decimal_text_is_preserved_exactly(value: Decimal) -> None:
    dataset = FinanceResearchDataset(
        participants=(ParticipantRecord("a", "P", "ACME", value, Decimal("0")),)
    )
    with tempfile.TemporaryDirectory() as tmp:
        target = write_finance_artifacts(dataset, Path(tmp) / "run")
        payload = (target / "participants.jsonl").read_text(encoding="utf-8")
    assert f'"initial_cash":"{value}"' in payload
