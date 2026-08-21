"""Public API tests for deterministic finance artifacts."""

from abmforge_finance.recording import (
    FINANCE_ARTIFACT_SCHEMA_VERSION,
    FinanceArtifactConfig,
    verify_finance_artifacts,
    write_finance_artifacts,
)


def test_artifact_public_api() -> None:
    assert FINANCE_ARTIFACT_SCHEMA_VERSION == "1.0"
    assert FinanceArtifactConfig is not None
    assert write_finance_artifacts is not None
    assert verify_finance_artifacts is not None
