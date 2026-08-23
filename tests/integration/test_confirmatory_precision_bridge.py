"""Archived precision-pilot bridge tests."""

from pathlib import Path

import pytest

from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    flagship_narrative_stability_protocol,
)
from abmforge_finance.study.confirmatory import (
    OFFICIAL_FLAGSHIP_PRECISION_ARTIFACT_SHA256,
    load_precision_pilot_decision,
)


def test_archived_precision_decision_is_locked_and_eligible() -> None:
    protocol = flagship_narrative_stability_protocol()
    decision = load_precision_pilot_decision(
        Path("artifacts/flagship/precision-pilot.json"),
        protocol,
    )

    assert decision.artifact_sha256 == OFFICIAL_FLAGSHIP_PRECISION_ARTIFACT_SHA256
    assert decision.protocol_fingerprint == protocol.fingerprint
    assert decision.precision_source_git_commit == ("78bf0e1d784ae921625117048749185c248a1987")
    assert decision.selected_seed_count == 10
    assert decision.pilot_seed_count == 160


def test_precision_loader_rejects_hash_mismatch(
    tmp_path: Path,
) -> None:
    source = Path("artifacts/flagship/precision-pilot.json")
    target = tmp_path / "precision-pilot.json"
    target.write_bytes(source.read_bytes() + b" ")

    with pytest.raises(
        StudyProtocolError,
        match="SHA-256",
    ):
        load_precision_pilot_decision(
            target,
            flagship_narrative_stability_protocol(),
        )


def test_precision_loader_rejects_missing_file(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        StudyProtocolError,
        match="unable to read",
    ):
        load_precision_pilot_decision(
            tmp_path / "missing.json",
            flagship_narrative_stability_protocol(),
        )
