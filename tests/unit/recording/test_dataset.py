"""Validation tests for finance research datasets."""

from decimal import Decimal

import pytest

from abmforge_finance.exceptions import InvalidFinanceDatasetError
from abmforge_finance.recording import (
    AccountRecord,
    DecisionRecord,
    FinanceResearchDataset,
    ParticipantRecord,
)


def test_empty_dataset_is_valid_and_counts_are_stable() -> None:
    dataset = FinanceResearchDataset()
    dataset.validate()
    assert dataset.row_counts == {
        "participants": 0,
        "decisions": 0,
        "cancellations": 0,
        "orders": 0,
        "trades": 0,
        "market_states": 0,
        "accounts": 0,
        "positions": 0,
    }


def test_dataset_rejects_wrong_schema_version() -> None:
    with pytest.raises(InvalidFinanceDatasetError):
        FinanceResearchDataset(schema_version="9.9").validate()


def test_dataset_rejects_duplicate_event_keys() -> None:
    participant = ParticipantRecord("a", "P", "ACME", Decimal("1"), Decimal("0"))
    decision = DecisionRecord(0, "a", "hold", None, None, None, None, None)
    dataset = FinanceResearchDataset(
        participants=(participant,),
        decisions=(decision, decision),
    )
    with pytest.raises(InvalidFinanceDatasetError, match="decision"):
        dataset.validate()


def test_dataset_rejects_duplicate_participant_and_negative_period() -> None:
    participant = ParticipantRecord("a", "P", "ACME", Decimal("1"), Decimal("0"))
    with pytest.raises(InvalidFinanceDatasetError, match="participant"):
        FinanceResearchDataset(participants=(participant, participant)).validate()

    account = AccountRecord(-1, "post", "a", Decimal("1"))
    with pytest.raises(InvalidFinanceDatasetError, match="non-negative"):
        FinanceResearchDataset(accounts=(account,)).validate()


def test_dataset_rejects_invalid_phase_even_if_constructed_dynamically() -> None:
    account = AccountRecord(0, "bad", "a", Decimal("1"))  # type: ignore[arg-type]
    with pytest.raises(InvalidFinanceDatasetError, match="phase"):
        FinanceResearchDataset(accounts=(account,)).validate()
