"""Canonical confirmatory artifact serialization."""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from abmforge_finance.calibration import (
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    PrecisionPilotPlan,
    PrecisionTarget,
    confirmatory_seed_tuple,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)
from abmforge_finance.study.confirmatory import (
    ConfirmatoryArtifact,
    PrecisionPilotDecision,
    build_confirmatory_artifact,
    write_confirmatory_artifact,
)


def _artifact() -> ConfirmatoryArtifact:
    protocol = replace(
        flagship_narrative_stability_protocol(),
        protocol_id="confirmatory-serialization",
        precision_plan=PrecisionPilotPlan(
            candidate_seed_counts=(2,),
            targets=(
                PrecisionTarget(
                    "mean_thin_side_depletion",
                    Decimal("10"),
                ),
                PrecisionTarget(
                    "mean_absolute_relative_dislocation",
                    Decimal("10"),
                ),
            ),
        ),
    )
    pilot_seeds = precision_pilot_seed_tuple(protocol)
    decision = PrecisionPilotDecision(
        artifact_sha256="a" * 64,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        protocol_fingerprint=protocol.fingerprint,
        precision_source_git_commit="b" * 40,
        pilot_seed_namespace=protocol.pilot_seed_namespace,
        pilot_seed_count=len(pilot_seeds),
        pilot_seed_fingerprint="c" * 64,
        selected_seed_count=2,
    )
    experiments = run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=confirmatory_seed_tuple(protocol, 2),
    )
    return build_confirmatory_artifact(
        protocol,
        decision,
        experiments,
        source_git_commit="d" * 40,
    )


def test_write_is_canonical_and_no_overwrite(
    tmp_path: Path,
) -> None:
    artifact = _artifact()
    target = tmp_path / "confirmatory.json"

    digest = write_confirmatory_artifact(
        artifact,
        target,
    )

    assert digest == artifact.sha256
    assert target.read_bytes() == artifact.canonical_bytes

    with pytest.raises(
        StudyProtocolError,
        match="already exists",
    ):
        write_confirmatory_artifact(
            artifact,
            target,
        )
