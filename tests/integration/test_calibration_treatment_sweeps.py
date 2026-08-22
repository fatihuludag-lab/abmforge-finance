"""Integration tests for Phase 9C.2 common-seed benchmark sweeps."""

from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    ConstantFundamentalBenchmarkConfig,
    run_noise_activity_sweep,
    run_noise_population_sweep,
    run_quote_width_sweep,
)
from abmforge_finance.exceptions import InvalidCalibrationError


def test_quote_width_sweep_has_exact_mechanical_spread_geometry() -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=3,
        passive_quantity=Decimal("2"),
        noise_activity_bps=0,
    )
    sweep = run_quote_width_sweep(
        config,
        quote_offset_ticks=(1, 2, 4),
        seeds=(101, 202),
    )

    assert tuple(experiment.summary.seeds for experiment in sweep) == (
        (101, 202),
        (101, 202),
        (101, 202),
    )
    assert tuple(
        experiment.summary.metric("mean_relative_spread").mean for experiment in sweep
    ) == (0.02, 0.04, 0.08)


def test_noise_activity_sweep_uses_nested_common_random_number_events() -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=20,
        passive_quantity=Decimal("2"),
        noise_trader_count=1,
        noise_quantity=Decimal("1"),
    )
    sweep = run_noise_activity_sweep(
        config,
        activity_bps=(0, 5_000, 10_000),
        seeds=(17, 23, 31),
    )

    assert all(experiment.summary.seeds == (17, 23, 31) for experiment in sweep)
    for replicate in range(3):
        trade_counts = tuple(experiment.runs[replicate].trade_count for experiment in sweep)
        assert trade_counts[0] == 0
        assert trade_counts[0] <= trade_counts[1] <= trade_counts[2]
        assert trade_counts[2] == 20


def test_noise_population_sweep_adds_demand_without_rejections() -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=4,
        passive_quantity=Decimal("4"),
        noise_quantity=Decimal("1"),
        noise_activity_bps=10_000,
    )
    sweep = run_noise_population_sweep(
        config,
        noise_trader_counts=(1, 2, 4),
        seeds=(7, 8),
    )

    assert all(experiment.summary.seeds == (7, 8) for experiment in sweep)
    assert tuple(experiment.summary.metric("trade_count").mean for experiment in sweep) == (
        4.0,
        8.0,
        16.0,
    )
    assert tuple(
        experiment.summary.metric("rejected_order_count").mean for experiment in sweep
    ) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize(
    ("function_name", "values"),
    [
        ("quote", ()),
        ("quote", (1, 1)),
        ("quote", (0,)),
        ("activity", ()),
        ("activity", (5_000, 5_000)),
        ("activity", (10_001,)),
        ("population", ()),
        ("population", (1, 1)),
        ("population", (0,)),
    ],
)
def test_sweeps_reject_invalid_treatment_grids(
    function_name: str,
    values: tuple[int, ...],
) -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=3,
        passive_quantity=Decimal("2"),
    )
    with pytest.raises(InvalidCalibrationError):
        if function_name == "quote":
            run_quote_width_sweep(config, quote_offset_ticks=values, seeds=(1,))
        elif function_name == "activity":
            run_noise_activity_sweep(config, activity_bps=values, seeds=(1,))
        else:
            run_noise_population_sweep(
                config,
                noise_trader_counts=values,
                seeds=(1,),
            )


@pytest.mark.parametrize("function_name", ["quote", "activity", "population"])
def test_sweeps_reject_wrong_config_type(function_name: str) -> None:
    with pytest.raises(TypeError, match="ConstantFundamentalBenchmarkConfig"):
        if function_name == "quote":
            run_quote_width_sweep(
                object(),  # type: ignore[arg-type]
                quote_offset_ticks=(1,),
                seeds=(1,),
            )
        elif function_name == "activity":
            run_noise_activity_sweep(
                object(),  # type: ignore[arg-type]
                activity_bps=(5_000,),
                seeds=(1,),
            )
        else:
            run_noise_population_sweep(
                object(),  # type: ignore[arg-type]
                noise_trader_counts=(1,),
                seeds=(1,),
            )
