"""Integration tests for robustness audits over real benchmark sweeps."""

from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    ConstantFundamentalBenchmarkConfig,
    RobustnessClassification,
    audit_parameter_sweep,
    build_baseline_ecology_audit,
    run_passive_depth_sweep,
    run_quote_width_sweep,
)


def test_quote_width_robustness_recovers_unit_elasticity() -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=4,
        passive_quantity=Decimal("2"),
        noise_activity_bps=0,
    )
    sweep = run_quote_width_sweep(
        config,
        quote_offset_ticks=(1, 2, 4),
        seeds=(101, 202, 303, 404),
    )

    audit = audit_parameter_sweep(
        sweep,
        control_index=0,
        family_name="quote-width",
        parameter_name="quote_offset_ticks",
        metric_name="mean_relative_spread",
    )

    assert audit.classification is RobustnessClassification.ROBUST_POSITIVE
    assert audit.region.intervals_excluding_zero_count == 2
    assert tuple(item.elasticity for item in audit.sensitivities) == pytest.approx((1.0, 1.0))


def test_passive_depth_and_quote_width_form_complete_baseline_audit() -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=4,
        passive_quantity=Decimal("2"),
        noise_quantity=Decimal("1"),
        noise_activity_bps=10_000,
    )
    seeds = (17, 23, 31, 47)

    depth = audit_parameter_sweep(
        run_passive_depth_sweep(
            config,
            passive_quantities=(Decimal("2"), Decimal("4"), Decimal("8")),
            seeds=seeds,
        ),
        control_index=0,
        family_name="passive-depth",
        parameter_name="passive_quantity",
        metric_name="mean_total_depth",
    )
    width = audit_parameter_sweep(
        run_quote_width_sweep(
            config,
            quote_offset_ticks=(1, 2, 4),
            seeds=seeds,
        ),
        control_index=0,
        family_name="quote-width",
        parameter_name="quote_offset_ticks",
        metric_name="mean_relative_spread",
    )

    baseline = build_baseline_ecology_audit(
        (depth, width),
        required_families=("passive-depth", "quote-width"),
    )

    assert depth.classification is RobustnessClassification.ROBUST_POSITIVE
    assert width.classification is RobustnessClassification.ROBUST_POSITIVE
    assert baseline.complete
    assert baseline.shared_seed_tuple == seeds
    assert baseline.mixed_families == ()
    assert baseline.warnings == ()
