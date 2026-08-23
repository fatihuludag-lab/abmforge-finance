"""Canonical serialization tests for precision pilot artifacts."""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from abmforge_finance.calibration import run_narrative_stability_homogeneity_sweep
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    PrecisionPilotPlan,
    PrecisionTarget,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)
from abmforge_finance.study.precision import (
    PrecisionPilotArtifact,
    build_precision_pilot_artifact,
    write_precision_pilot_artifact,
)


def _artifact() -> PrecisionPilotArtifact:
    base = flagship_narrative_stability_protocol()
    protocol = replace(
        base,
        protocol_id="artifact-test",
        precision_plan=PrecisionPilotPlan(
            candidate_seed_counts=(2,),
            targets=(
                PrecisionTarget("mean_thin_side_depletion", Decimal("10")),
                PrecisionTarget(
                    "mean_absolute_relative_dislocation",
                    Decimal("10"),
                ),
            ),
        ),
    )
    experiments = run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=precision_pilot_seed_tuple(protocol),
    )
    return build_precision_pilot_artifact(
        protocol,
        experiments,
        source_git_commit="c" * 40,
    )


def test_canonical_artifact_write_is_deterministic_and_no_overwrite(
    tmp_path: Path,
) -> None:
    artifact = _artifact()
    target = tmp_path / "precision-pilot.json"

    digest = write_precision_pilot_artifact(artifact, target)

    assert digest == artifact.sha256
    assert target.read_bytes() == artifact.canonical_bytes
    assert json.loads(target.read_text(encoding="utf-8")) == artifact.to_mapping()

    with pytest.raises(StudyProtocolError, match="already exists"):
        write_precision_pilot_artifact(artifact, target)


def test_artifact_rejects_invalid_source_git_commit() -> None:
    artifact = _artifact()

    with pytest.raises(StudyProtocolError, match="Git SHA"):
        replace(artifact, source_git_commit="not-a-git-sha")
