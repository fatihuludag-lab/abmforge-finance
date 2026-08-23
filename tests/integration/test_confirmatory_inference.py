"""Integration tests for role-aware confirmatory inference."""

from dataclasses import replace
from decimal import Decimal

from abmforge_finance.calibration import (
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.study import (
    FlagshipStudyProtocol,
    OutcomeRole,
    PrecisionPilotPlan,
    PrecisionTarget,
    confirmatory_seed_tuple,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)
from abmforge_finance.study.confirmatory import (
    PrecisionPilotDecision,
    build_confirmatory_artifact,
    verify_confirmatory_artifact,
)


def _small_protocol() -> FlagshipStudyProtocol:
    base = flagship_narrative_stability_protocol()
    return replace(
        base,
        protocol_id="confirmatory-test",
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


def test_confirmatory_artifact_separates_roles() -> None:
    protocol = _small_protocol()
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
    confirmatory_seeds = confirmatory_seed_tuple(
        protocol,
        2,
    )
    experiments = run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=confirmatory_seeds,
    )

    artifact = build_confirmatory_artifact(
        protocol,
        decision,
        experiments,
        source_git_commit="d" * 40,
    )
    verify_confirmatory_artifact(
        artifact,
        protocol,
        decision,
    )

    assert artifact.confirmatory_seed_count == 2
    assert artifact.pilot_seed_overlap_count == 0
    assert artifact.primary_hypothesis_count == 8

    primary = tuple(outcome for outcome in artifact.outcomes if outcome.role is OutcomeRole.PRIMARY)
    assert len(primary) == 2
    assert sum(len(outcome.contrasts) for outcome in primary) == 8
    assert all(
        contrast.raw_p_value is not None
        and contrast.holm_adjusted_p_value is not None
        and contrast.holm_reject is not None
        for outcome in primary
        for contrast in outcome.contrasts
    )

    nonprimary = tuple(
        outcome for outcome in artifact.outcomes if outcome.role is not OutcomeRole.PRIMARY
    )
    assert nonprimary
    assert all(
        contrast.raw_p_value is None
        and contrast.holm_adjusted_p_value is None
        and contrast.holm_reject is None
        and contrast.hypothesis_id is None
        for outcome in nonprimary
        for contrast in outcome.contrasts
    )
