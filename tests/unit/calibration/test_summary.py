"""Tests for descriptive calibration summaries."""

from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    CalibrationRunResult,
    CalibrationRunSpec,
    CalibrationScenario,
    summarize_calibration_runs,
)
from abmforge_finance.exceptions import InvalidCalibrationError


def _result(replicate: int, seed: int, trade_count: int) -> CalibrationRunResult:
    scenario = CalibrationScenario("s", "t", 2, (("x", "1"),))
    return CalibrationRunResult(
        spec=CalibrationRunSpec(scenario, replicate, seed),
        dataset_schema_version="1.1",
        participant_count=3,
        decision_count=6,
        cancellation_count=2,
        order_count=6,
        rejected_order_count=0,
        trade_count=trade_count,
        trade_volume=Decimal(trade_count),
        mid_realized_volatility=0.0,
        last_trade_realized_volatility=None,
        maximum_drawdown=Decimal("0"),
        mean_relative_spread=Decimal("0.02"),
        mean_total_depth=Decimal("3"),
        mean_absolute_relative_dislocation=Decimal("0"),
        mean_decision_sign_concentration=Decimal("1"),
    )


def test_summary_reports_sample_dispersion_without_inference() -> None:
    summary = summarize_calibration_runs((_result(0, 11, 2), _result(1, 12, 4)))

    metric = summary.metric("trade_count")
    assert metric.total_replicates == 2
    assert metric.defined_replicates == 2
    assert metric.mean == 3.0
    assert metric.sample_std == pytest.approx(2**0.5)
    assert metric.standard_error == pytest.approx(1.0)
    assert metric.minimum == 2.0
    assert metric.maximum == 4.0

    undefined = summary.metric("last_trade_realized_volatility")
    assert undefined.defined_replicates == 0
    assert undefined.mean is None


def test_summary_rejects_mixed_or_noncontiguous_runs() -> None:
    first = _result(0, 11, 2)
    skipped = _result(2, 12, 4)
    with pytest.raises(InvalidCalibrationError, match="contiguous"):
        summarize_calibration_runs((first, skipped))

    other = CalibrationRunResult(
        spec=CalibrationRunSpec(CalibrationScenario("s", "other", 2), 1, 12),
        dataset_schema_version="1.1",
        participant_count=3,
        decision_count=6,
        cancellation_count=2,
        order_count=6,
        rejected_order_count=0,
        trade_count=4,
        trade_volume=Decimal("4"),
        mid_realized_volatility=0.0,
        last_trade_realized_volatility=None,
        maximum_drawdown=Decimal("0"),
        mean_relative_spread=Decimal("0.02"),
        mean_total_depth=Decimal("3"),
        mean_absolute_relative_dislocation=Decimal("0"),
        mean_decision_sign_concentration=Decimal("1"),
    )
    with pytest.raises(InvalidCalibrationError, match="canonical"):
        summarize_calibration_runs((first, other))
