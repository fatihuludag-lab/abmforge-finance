"""Integration test for the nested-prefix precision decision."""

from dataclasses import replace
from decimal import Decimal

from abmforge_finance.calibration import run_narrative_stability_homogeneity_sweep
from abmforge_finance.study import (
    PrecisionPilotPlan,
    PrecisionTarget,
    evaluate_precision_pilot,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)


def test_precision_pilot_selects_smallest_candidate_meeting_all_targets() -> None:
    protocol = flagship_narrative_stability_protocol()
    protocol = replace(
        protocol,
        precision_plan=PrecisionPilotPlan(
            candidate_seed_counts=(2, 3, 4),
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

    report = evaluate_precision_pilot(protocol, experiments)

    assert tuple(item.seed_count for item in report.checkpoints) == (2, 3, 4)
    assert report.selected_seed_count == 2
    assert report.ready_for_confirmatory_run
