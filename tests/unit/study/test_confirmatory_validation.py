"""Confirmatory provenance and tamper validation."""

from dataclasses import replace
from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    FlagshipStudyProtocol,
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
    verify_confirmatory_experiments,
)


def _protocol() -> FlagshipStudyProtocol:
    return replace(
        flagship_narrative_stability_protocol(),
        protocol_id="confirmatory-validation",
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


def _decision(
    protocol: FlagshipStudyProtocol,
) -> PrecisionPilotDecision:
    pilot_seeds = precision_pilot_seed_tuple(protocol)
    return PrecisionPilotDecision(
        artifact_sha256="1" * 64,
        protocol_id=protocol.protocol_id,
        protocol_version=protocol.protocol_version,
        protocol_fingerprint=protocol.fingerprint,
        precision_source_git_commit="2" * 40,
        pilot_seed_namespace=protocol.pilot_seed_namespace,
        pilot_seed_count=len(pilot_seeds),
        pilot_seed_fingerprint="3" * 64,
        selected_seed_count=2,
    )


def _experiments(
    protocol: FlagshipStudyProtocol,
) -> tuple[CalibrationExperimentResult, ...]:
    return run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=confirmatory_seed_tuple(protocol, 2),
    )


def test_verifier_rejects_treatment_order() -> None:
    protocol = _protocol()
    experiments = _experiments(protocol)

    with pytest.raises(
        StudyProtocolError,
        match="protocol order",
    ):
        verify_confirmatory_experiments(
            protocol,
            _decision(protocol),
            tuple(reversed(experiments)),
        )


def test_verifier_rejects_wrong_seed_tuple() -> None:
    protocol = _protocol()
    experiments = _experiments(protocol)
    first = experiments[0]
    first_run = first.runs[0]
    tampered = replace(
        first,
        runs=(
            replace(
                first_run,
                spec=replace(
                    first_run.spec,
                    seed=first_run.spec.seed + 1,
                ),
            ),
            *first.runs[1:],
        ),
    )

    with pytest.raises(
        StudyProtocolError,
        match="exact confirmatory seed tuple",
    ):
        verify_confirmatory_experiments(
            protocol,
            _decision(protocol),
            (tampered, *experiments[1:]),
        )


def test_artifact_verifier_rejects_holm_tampering() -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    artifact = build_confirmatory_artifact(
        protocol,
        decision,
        _experiments(protocol),
        source_git_commit="4" * 40,
    )
    primary_index = next(
        index for index, outcome in enumerate(artifact.outcomes) if outcome.role.value == "primary"
    )
    primary = artifact.outcomes[primary_index]
    contrast = primary.contrasts[0]
    assert contrast.holm_adjusted_p_value is not None

    tampered_contrast = replace(
        contrast,
        holm_adjusted_p_value=min(
            1.0,
            contrast.holm_adjusted_p_value + 0.123,
        ),
    )
    tampered_primary = replace(
        primary,
        contrasts=(
            tampered_contrast,
            *primary.contrasts[1:],
        ),
    )
    outcomes = list(artifact.outcomes)
    outcomes[primary_index] = tampered_primary

    with pytest.raises(
        StudyProtocolError,
        match="Holm adjusted",
    ):
        verify_confirmatory_artifact(
            replace(
                artifact,
                outcomes=tuple(outcomes),
            ),
            protocol,
            decision,
        )


def test_nonprimary_cannot_gain_significance_fields() -> None:
    protocol = _protocol()
    decision = _decision(protocol)
    artifact = build_confirmatory_artifact(
        protocol,
        decision,
        _experiments(protocol),
        source_git_commit="5" * 40,
    )
    index = next(
        index for index, outcome in enumerate(artifact.outcomes) if outcome.role.value != "primary"
    )
    outcome = artifact.outcomes[index]
    contrast = outcome.contrasts[0]
    tampered_outcome = replace(
        outcome,
        contrasts=(
            replace(
                contrast,
                hypothesis_id="exploratory",
                raw_p_value=0.01,
                holm_adjusted_p_value=0.01,
                holm_reject=True,
            ),
            *outcome.contrasts[1:],
        ),
    )
    outcomes = list(artifact.outcomes)
    outcomes[index] = tampered_outcome

    with pytest.raises(
        StudyProtocolError,
        match="non-primary",
    ):
        verify_confirmatory_artifact(
            replace(
                artifact,
                outcomes=tuple(outcomes),
            ),
            protocol,
            decision,
        )
