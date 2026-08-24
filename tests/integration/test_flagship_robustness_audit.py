from dataclasses import replace
from decimal import Decimal

from abmforge_finance.calibration import run_narrative_stability_homogeneity_sweep
from abmforge_finance.study import (
    FlagshipStudyProtocol,
    PrecisionPilotPlan,
    PrecisionTarget,
    apply_robustness_regime,
    flagship_narrative_stability_protocol,
)
from abmforge_finance.study.robustness import (
    ConfirmatoryRobustnessAnchor,
    RobustnessRegimeExperiments,
    build_robustness_audit_artifact,
    robustness_seed_tuple,
)


def _protocol() -> FlagshipStudyProtocol:
    base = flagship_narrative_stability_protocol()
    return replace(
        base,
        protocol_id="robustness-test",
        precision_plan=PrecisionPilotPlan(
            candidate_seed_counts=(2,),
            targets=(
                PrecisionTarget("mean_thin_side_depletion", Decimal("10")),
                PrecisionTarget("mean_absolute_relative_dislocation", Decimal("10")),
            ),
        ),
        robustness_regimes=base.robustness_regimes[:1],
    )


def test_small_robustness_artifact_is_estimation_only() -> None:
    protocol = _protocol()
    treatments = protocol.homogeneities[1:]
    anchor = ConfirmatoryRobustnessAnchor(
        artifact_sha256="a" * 64,
        source_git_commit="b" * 40,
        protocol_fingerprint=protocol.fingerprint,
        precision_artifact_sha256="c" * 64,
        selected_seed_count=2,
        confirmatory_seed_fingerprint="d" * 64,
        primary_effects=tuple(
            (
                metric,
                tuple((h, float(index + 1)) for index, h in enumerate(treatments)),
            )
            for metric in protocol.primary_metric_names
        ),
    )
    regime = protocol.robustness_regimes[0]
    experiments = run_narrative_stability_homogeneity_sweep(
        apply_robustness_regime(protocol, regime.regime_id),
        homogeneities=protocol.homogeneities,
        seeds=robustness_seed_tuple(protocol, 2),
    )
    artifact = build_robustness_audit_artifact(
        protocol,
        anchor,
        (RobustnessRegimeExperiments(regime.regime_id, experiments),),
        source_git_commit="e" * 40,
    )
    assert len(artifact.regimes) == 1
    assert "raw_p_value" not in artifact.canonical_json
    assert "holm_reject" not in artifact.canonical_json
    primary = tuple(
        outcome for outcome in artifact.regimes[0].outcomes if outcome.role.value == "primary"
    )
    assert len(primary) == 2
    assert all(item.direction_preserved_all_contrasts is not None for item in primary)
