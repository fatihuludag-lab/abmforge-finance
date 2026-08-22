"""Tests for generic deterministic calibration execution."""

from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    CalibrationRunSpec,
    CalibrationScenario,
    DatasetFactory,
    run_calibration_replicates,
)
from abmforge_finance.exceptions import CalibrationExecutionError
from abmforge_finance.recording import FinanceResearchDataset, MarketStateRecord


def _state(period: int) -> MarketStateRecord:
    return MarketStateRecord(
        period=period,
        instrument_id="CAL",
        fundamental_value=Decimal("100"),
        best_bid=Decimal("99"),
        best_ask=Decimal("101"),
        mid_price=Decimal("100"),
        spread=Decimal("2"),
        bid_depth=Decimal("2"),
        ask_depth=Decimal("2"),
        imbalance=Decimal("0"),
        order_count=2,
        last_trade_price=Decimal("99"),
        price_change=None,
        fee_balance=Decimal("0"),
    )


def test_runner_preserves_explicit_seed_order() -> None:
    scenario = CalibrationScenario("s", "t", 2)

    def factory(spec: CalibrationRunSpec) -> FinanceResearchDataset:
        assert spec.seed in (9, 4)
        return FinanceResearchDataset(market_states=(_state(0), _state(1)))

    runs = run_calibration_replicates(
        scenario,
        seeds=(9, 4),
        dataset_factory=factory,
    )
    assert tuple(run.spec.seed for run in runs) == (9, 4)
    assert tuple(run.spec.replicate for run in runs) == (0, 1)
    assert all(run.mid_realized_volatility == 0.0 for run in runs)


def test_runner_rejects_incomplete_recorded_horizon() -> None:
    scenario = CalibrationScenario("s", "t", 2)

    with pytest.raises(CalibrationExecutionError, match="market-state periods"):
        run_calibration_replicates(
            scenario,
            seeds=(1,),
            dataset_factory=lambda _spec: FinanceResearchDataset(market_states=(_state(0),)),
        )


def test_runner_rejects_wrong_factory_result_type() -> None:
    scenario = CalibrationScenario("s", "t", 2)

    def bad_factory(_spec: CalibrationRunSpec) -> FinanceResearchDataset:
        return object()  # type: ignore[return-value]

    factory: DatasetFactory = bad_factory
    with pytest.raises(CalibrationExecutionError, match="FinanceResearchDataset"):
        run_calibration_replicates(
            scenario,
            seeds=(1,),
            dataset_factory=factory,
        )
