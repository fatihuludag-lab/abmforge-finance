"""Integration tests for the controlled baseline market ecology."""

from decimal import Decimal

from abmforge_finance.calibration import (
    ConstantFundamentalBenchmarkConfig,
    run_constant_fundamental_benchmark,
    run_passive_depth_sweep,
)


def test_constant_fundamental_benchmark_has_clean_mechanistic_baseline() -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=4,
        passive_quantity=Decimal("2"),
        noise_trader_count=1,
        noise_quantity=Decimal("1"),
        noise_activity_bps=10_000,
    )
    experiment = run_constant_fundamental_benchmark(
        config,
        seeds=(11, 12),
    )

    assert experiment.summary.replicate_count == 2
    assert experiment.scenario.fingerprint == experiment.runs[0].scenario_fingerprint

    for run in experiment.runs:
        assert run.participant_count == 3
        assert run.decision_count == 12
        assert run.order_count == 12
        assert run.cancellation_count == 6
        assert run.rejected_order_count == 0
        assert run.trade_count == 4
        assert run.trade_volume == Decimal("4")
        assert run.mid_realized_volatility == 0.0
        assert run.maximum_drawdown == Decimal("0")
        assert run.mean_relative_spread == Decimal("0.02")
        assert run.mean_total_depth == Decimal("3")
        assert run.mean_absolute_relative_dislocation == Decimal("0")


def test_passive_depth_sweep_reuses_common_seeds_and_changes_displayed_depth() -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=4,
        passive_quantity=Decimal("2"),
        noise_trader_count=1,
        noise_quantity=Decimal("1"),
        noise_activity_bps=10_000,
    )
    sweep = run_passive_depth_sweep(
        config,
        passive_quantities=(Decimal("2"), Decimal("4")),
        seeds=(101, 202, 303),
    )

    assert tuple(experiment.summary.seeds for experiment in sweep) == (
        (101, 202, 303),
        (101, 202, 303),
    )
    low_depth = sweep[0].summary.metric("mean_total_depth").mean
    high_depth = sweep[1].summary.metric("mean_total_depth").mean
    assert low_depth == 3.0
    assert high_depth == 7.0
    assert high_depth > low_depth

    assert sweep[0].summary.metric("trade_count").mean == 4.0
    assert sweep[1].summary.metric("trade_count").mean == 4.0
    assert sweep[0].summary.metric("rejected_order_count").mean == 0.0
    assert sweep[1].summary.metric("rejected_order_count").mean == 0.0
