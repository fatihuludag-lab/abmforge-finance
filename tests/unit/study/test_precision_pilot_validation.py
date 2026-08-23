"""Validation paths for Phase 10E precision execution."""

from dataclasses import replace
from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.exceptions import StudyProtocolError
from abmforge_finance.study import (
    PrecisionPilotPlan,
    PrecisionTarget,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)
from abmforge_finance.study.precision import (
    build_precision_pilot_artifact,
    verify_precision_pilot_artifact,
    verify_precision_pilot_experiments,
)
from abmforge_finance.study.protocol import FlagshipStudyProtocol


def _protocol() -> FlagshipStudyProtocol:
    return replace(
        flagship_narrative_stability_protocol(),
        protocol_id="validation-test",
        precision_plan=PrecisionPilotPlan(
            candidate_seed_counts=(2, 3),
            targets=(
                PrecisionTarget("mean_thin_side_depletion", Decimal("10")),
                PrecisionTarget(
                    "mean_absolute_relative_dislocation",
                    Decimal("10"),
                ),
            ),
        ),
    )


def _experiments(
    protocol: FlagshipStudyProtocol,
) -> tuple[CalibrationExperimentResult, ...]:
    return run_narrative_stability_homogeneity_sweep(
        protocol.benchmark_config,
        homogeneities=protocol.homogeneities,
        seeds=precision_pilot_seed_tuple(protocol),
    )


def test_verifier_rejects_wrong_protocol_type_and_experiment_shape() -> None:
    protocol = _protocol()

    with pytest.raises(TypeError, match="FlagshipStudyProtocol"):
        verify_precision_pilot_experiments(
            object(),  # type: ignore[arg-type]
            (),
        )

    with pytest.raises(StudyProtocolError, match="treatment grid"):
        verify_precision_pilot_experiments(protocol, ())


def test_verifier_rejects_scenario_parameter_tampering() -> None:
    protocol = _protocol()
    experiments = _experiments(protocol)

    first = experiments[0]
    tampered_scenario = replace(
        first.scenario,
        parameters=tuple(
            (
                key,
                "999" if key == "noise_activity_bps" else value,
            )
            for key, value in first.scenario.parameters
        ),
    )
    tampered = replace(first, scenario=tampered_scenario)

    with pytest.raises(StudyProtocolError, match="benchmark configuration"):
        verify_precision_pilot_experiments(
            protocol,
            (tampered, *experiments[1:]),
        )


def test_artifact_verifier_rejects_selected_n_tampering() -> None:
    protocol = _protocol()
    artifact = build_precision_pilot_artifact(
        protocol,
        _experiments(protocol),
        source_git_commit="d" * 40,
    )

    with pytest.raises(StudyProtocolError, match="smallest-n"):
        verify_precision_pilot_artifact(
            replace(artifact, selected_seed_count=3),
            protocol,
        )
