"""Tests for calibration scenario and replicate contracts."""

import pytest

from abmforge_finance.calibration import (
    CalibrationRunSpec,
    CalibrationScenario,
    validate_seed_tuple,
)
from abmforge_finance.exceptions import InvalidCalibrationError


def test_scenario_canonicalizes_parameter_order_and_fingerprint() -> None:
    left = CalibrationScenario("scenario", "treatment", 5, (("z", "2"), ("a", "1")))
    right = CalibrationScenario("scenario", "treatment", 5, (("a", "1"), ("z", "2")))

    assert left.parameters == (("a", "1"), ("z", "2"))
    assert left == right
    assert left.fingerprint == right.fingerprint
    assert len(left.fingerprint) == 64


@pytest.mark.parametrize(
    "scenario",
    [
        lambda: CalibrationScenario("", "t", 2),
        lambda: CalibrationScenario("s", "", 2),
        lambda: CalibrationScenario("s", "t", 0),
        lambda: CalibrationScenario("s", "t", 2, (("a", "1"), ("a", "2"))),
        lambda: CalibrationScenario("s", "t", 2, (("", "1"),)),
    ],
)
def test_invalid_scenarios_are_rejected(scenario) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(InvalidCalibrationError):
        scenario()


def test_run_spec_and_seed_tuple_validation() -> None:
    scenario = CalibrationScenario("s", "t", 2)
    assert CalibrationRunSpec(scenario, 0, 7).seed == 7
    assert validate_seed_tuple((7, 3)) == (7, 3)

    with pytest.raises(InvalidCalibrationError):
        CalibrationRunSpec(scenario, -1, 7)
    with pytest.raises(InvalidCalibrationError):
        CalibrationRunSpec(scenario, 0, -1)
    with pytest.raises(InvalidCalibrationError):
        validate_seed_tuple(())
    with pytest.raises(InvalidCalibrationError):
        validate_seed_tuple((7, 7))
