"""Unit tests for the multi-seed narrative-stability benchmark contract."""

from decimal import Decimal

import pytest

from abmforge_finance import NarrativeDirection
from abmforge_finance.calibration import (
    NarrativeStabilityBenchmarkConfig,
    NarrativeStabilityRunResult,
)
from abmforge_finance.exceptions import InvalidCalibrationError


def test_default_config_has_explicit_stochastic_and_liquidity_controls() -> None:
    config = NarrativeStabilityBenchmarkConfig()

    assert config.periods == 4
    assert config.narrative_agent_count == 8
    assert config.noise_trader_count == 4
    assert config.noise_activity_bps == 5_000
    assert config.reference_side_depth == Decimal("20")
    assert config.reference_spread == Decimal("2")


def test_scenarios_differ_only_in_homogeneity() -> None:
    config = NarrativeStabilityBenchmarkConfig()
    control = config.scenario(Decimal("0"))
    treatment = config.scenario(Decimal("0.5"))

    control_parameters = dict(control.parameters)
    treatment_parameters = dict(treatment.parameters)
    changed = tuple(
        key for key in control_parameters if control_parameters[key] != treatment_parameters[key]
    )

    assert changed == ("homogeneity",)
    assert control_parameters["benchmark_family"] == "narrative-stability-v1"
    assert control.periods == treatment.periods == config.periods


def test_treatment_uses_full_direction_schedule_window() -> None:
    config = NarrativeStabilityBenchmarkConfig()
    treatment = config.treatment(Decimal("0.5"))

    assert treatment.active_from == 0
    assert treatment.active_until == config.periods
    assert treatment.focal_direction is NarrativeDirection.BULLISH
    assert treatment.assigned_directional_concentration == Decimal("0.5")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"narrative_agent_count": 7},
        {"passive_levels": 1},
        {"noise_activity_bps": 0},
        {"decision_threshold": Decimal("1")},
        {"fundamental_value": Decimal("100.5")},
        {"passive_quantity_per_level": Decimal("2")},
    ],
)
def test_config_rejects_confounded_or_degenerate_fixture_controls(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(InvalidCalibrationError):
        NarrativeStabilityBenchmarkConfig(**kwargs)  # type: ignore[arg-type]


def test_run_result_remains_a_calibration_run_result_subclass() -> None:
    from abmforge_finance.calibration import CalibrationRunResult

    assert issubclass(NarrativeStabilityRunResult, CalibrationRunResult)
