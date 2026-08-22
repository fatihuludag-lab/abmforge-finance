"""Unit tests for controlled baseline benchmark configuration."""

from decimal import Decimal

import pytest

from abmforge_finance.calibration import ConstantFundamentalBenchmarkConfig
from abmforge_finance.exceptions import InvalidCalibrationError


def test_config_provenance_contains_all_treatment_parameters() -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=5,
        passive_quantity=Decimal("4"),
        treatment_id="depth-four",
    )
    scenario = config.scenario()

    assert scenario.periods == 5
    assert scenario.treatment_id == "depth-four"
    assert dict(scenario.parameters)["passive_quantity"] == "4"
    assert dict(scenario.parameters)["noise_activity_bps"] == "10000"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"periods": 1},
        {"passive_quantity": Decimal("0")},
        {"quote_offset_ticks": 0},
        {"noise_trader_count": 0},
        {"noise_activity_bps": 10_001},
        {"passive_quantity": Decimal("0.5"), "lot_size": Decimal("1")},
        {"noise_quantity": Decimal("0.5"), "lot_size": Decimal("1")},
        {
            "passive_quantity": Decimal("1"),
            "noise_trader_count": 2,
            "noise_quantity": Decimal("1"),
        },
    ],
)
def test_invalid_baseline_config_is_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(InvalidCalibrationError):
        ConstantFundamentalBenchmarkConfig(**kwargs)  # type: ignore[arg-type]
