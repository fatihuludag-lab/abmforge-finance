"""Integration tests for inference over common-seed benchmark families."""

from decimal import Decimal

from abmforge_finance.calibration import (
    ConstantFundamentalBenchmarkConfig,
    paired_treatment_contrast,
    run_noise_activity_sweep,
    run_quote_width_sweep,
    summarize_contrast_region,
)


def test_quote_width_contrast_recovers_exact_mechanical_effect() -> None:
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

    width_two = paired_treatment_contrast(
        sweep[0],
        sweep[1],
        metric_name="mean_relative_spread",
    )
    width_four = paired_treatment_contrast(
        sweep[0],
        sweep[2],
        metric_name="mean_relative_spread",
    )

    assert width_two.differences == (0.02, 0.02, 0.02, 0.02)
    assert width_two.mean_difference == 0.02
    assert width_two.standard_error == 0.0
    assert width_two.confidence_interval_lower == 0.02
    assert width_two.confidence_interval_upper == 0.02

    region = summarize_contrast_region((width_two, width_four))
    assert region.direction_consistency == "positive"
    assert region.intervals_excluding_zero_count == 2


def test_noise_activity_contrast_uses_common_seed_pairs() -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=10,
        passive_quantity=Decimal("2"),
        noise_trader_count=1,
        noise_quantity=Decimal("1"),
    )
    sweep = run_noise_activity_sweep(
        config,
        activity_bps=(0, 10_000),
        seeds=(17, 23, 31, 47),
    )

    contrast = paired_treatment_contrast(
        sweep[0],
        sweep[1],
        metric_name="trade_count",
    )

    assert contrast.seeds == (17, 23, 31, 47)
    assert contrast.differences == (10.0, 10.0, 10.0, 10.0)
    assert contrast.mean_difference == 10.0
    assert contrast.standard_error == 0.0
    assert contrast.excludes_zero
