"""Integration tests for deterministic fundamental tracking."""

from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    FundamentalTrackingBenchmarkConfig,
    run_fundamental_tracking_benchmark,
)
from abmforge_finance.exceptions import InvalidCalibrationError


def test_tick_aligned_fundamental_path_is_tracked_by_midpoint() -> None:
    config = FundamentalTrackingBenchmarkConfig(
        fundamental_path=(
            Decimal("100"),
            Decimal("102"),
            Decimal("104"),
            Decimal("101"),
        ),
        passive_quantity=Decimal("2"),
        noise_trader_count=1,
        noise_quantity=Decimal("1"),
        noise_activity_bps=0,
    )
    experiment = run_fundamental_tracking_benchmark(config, seeds=(11, 12))

    assert experiment.summary.seeds == (11, 12)
    assert dict(experiment.scenario.parameters)["fundamental_path"] == "100,102,104,101"

    for run in experiment.runs:
        assert run.participant_count == 3
        assert run.decision_count == 12
        assert run.order_count == 8
        assert run.cancellation_count == 6
        assert run.trade_count == 0
        assert run.last_trade_realized_volatility is None
        assert run.mid_realized_volatility is not None
        assert run.mid_realized_volatility > 0
        assert run.mean_absolute_relative_dislocation == Decimal("0")


def test_non_grid_path_preserves_explicit_grid_tracking_error() -> None:
    config = FundamentalTrackingBenchmarkConfig(
        fundamental_path=(Decimal("100.25"), Decimal("101.25")),
        passive_quantity=Decimal("2"),
        noise_activity_bps=0,
    )
    experiment = run_fundamental_tracking_benchmark(config, seeds=(7,))
    error = experiment.runs[0].mean_absolute_relative_dislocation

    assert error is not None
    assert error > Decimal("0")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fundamental_path": ()},
        {"fundamental_path": (Decimal("100"),)},
        {"fundamental_path": (Decimal("100"), Decimal("0"))},
        {
            "fundamental_path": (Decimal("100"), Decimal("101")),
            "quote_offset_ticks": 0,
        },
        {
            "fundamental_path": (Decimal("100"), Decimal("101")),
            "noise_trader_count": 0,
        },
        {
            "fundamental_path": (Decimal("100"), Decimal("101")),
            "noise_activity_bps": 10_001,
        },
        {
            "fundamental_path": (Decimal("100"), Decimal("101")),
            "passive_quantity": Decimal("1"),
            "noise_trader_count": 2,
        },
    ],
)
def test_invalid_tracking_config_is_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(InvalidCalibrationError):
        FundamentalTrackingBenchmarkConfig(**kwargs)  # type: ignore[arg-type]


def test_tracking_runner_rejects_wrong_config_type() -> None:
    with pytest.raises(TypeError, match="FundamentalTrackingBenchmarkConfig"):
        run_fundamental_tracking_benchmark(
            object(),  # type: ignore[arg-type]
            seeds=(1,),
        )
