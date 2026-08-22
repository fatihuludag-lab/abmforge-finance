"""Public API tests for finance recording."""

from abmforge_finance.recording import (
    FINANCE_DATASET_SCHEMA_VERSION,
    CancellationRecord,
    FinanceRecordingConfig,
    FinanceResearchDataset,
    FinanceResearchRecorder,
)


def test_recording_public_api() -> None:
    assert FINANCE_DATASET_SCHEMA_VERSION == "1.1"
    assert CancellationRecord.__name__ == "CancellationRecord"
    assert FinanceRecordingConfig is not None
    assert FinanceResearchDataset is not None
    assert FinanceResearchRecorder is not None
