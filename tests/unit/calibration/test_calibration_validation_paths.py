"""Validation, failure-path, and reproducibility tests for calibration."""

from dataclasses import replace
from decimal import Decimal

import pytest

from abmforge_finance.calibration import (
    CalibrationRunResult,
    CalibrationRunSpec,
    CalibrationScenario,
    ConstantFundamentalBenchmarkConfig,
    evaluate_calibration_dataset,
    run_and_summarize_calibration,
    run_calibration_replicates,
    run_constant_fundamental_benchmark,
    run_passive_depth_sweep,
    summarize_calibration_runs,
    validate_seed_tuple,
)
from abmforge_finance.exceptions import (
    InvalidCalibrationError,
)
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
        last_trade_price=Decimal("100"),
        price_change=None,
        fee_balance=Decimal("0"),
    )


def _dataset() -> FinanceResearchDataset:
    return FinanceResearchDataset(
        market_states=(
            _state(0),
            _state(1),
        )
    )


def _result(
    *,
    replicate: int = 0,
    seed: int = 1,
    mid_volatility: float | None = 0.0,
) -> CalibrationRunResult:
    scenario = CalibrationScenario("validation", "baseline", 2)
    return CalibrationRunResult(
        spec=CalibrationRunSpec(scenario, replicate, seed),
        dataset_schema_version="1.1",
        participant_count=0,
        decision_count=0,
        cancellation_count=0,
        order_count=0,
        rejected_order_count=0,
        trade_count=0,
        trade_volume=Decimal("0"),
        mid_realized_volatility=mid_volatility,
        last_trade_realized_volatility=None,
        maximum_drawdown=Decimal("0"),
        mean_relative_spread=Decimal("0.02"),
        mean_total_depth=Decimal("4"),
        mean_absolute_relative_dislocation=Decimal("0"),
        mean_decision_sign_concentration=None,
    )


@pytest.mark.parametrize(
    "parameters",
    [
        [("a", "1")],
        (("a",),),
        (("a", 1),),
        ("not-a-pair",),
    ],
)
def test_scenario_rejects_malformed_parameter_containers(parameters: object) -> None:
    with pytest.raises(InvalidCalibrationError, match="parameters"):
        CalibrationScenario(
            "scenario",
            "treatment",
            2,
            parameters=parameters,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "seed",
    [
        True,
        "1",
        1 << 64,
    ],
)
def test_seed_validation_rejects_type_and_range_boundaries(seed: object) -> None:
    scenario = CalibrationScenario("scenario", "treatment", 2)
    with pytest.raises(InvalidCalibrationError, match="seed"):
        CalibrationRunSpec(
            scenario,
            0,
            seed,  # type: ignore[arg-type]
        )


def test_run_spec_rejects_non_scenario_and_boolean_replicate() -> None:
    with pytest.raises(InvalidCalibrationError, match="scenario"):
        CalibrationRunSpec(object(), 0, 1)  # type: ignore[arg-type]

    scenario = CalibrationScenario("scenario", "treatment", 2)
    with pytest.raises(InvalidCalibrationError, match="replicate"):
        CalibrationRunSpec(scenario, True, 1)


@pytest.mark.parametrize(
    "seeds",
    [
        [1],
        (True,),
        ("1",),
    ],
)
def test_seed_tuple_rejects_invalid_container_or_values(seeds: object) -> None:
    with pytest.raises(InvalidCalibrationError, match="seed"):
        validate_seed_tuple(seeds)


def test_dataset_evaluator_rejects_wrong_public_input_types() -> None:
    scenario = CalibrationScenario("scenario", "treatment", 2)
    spec = CalibrationRunSpec(scenario, 0, 1)
    dataset = _dataset()

    with pytest.raises(TypeError, match="CalibrationRunSpec"):
        evaluate_calibration_dataset(object(), dataset)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="FinanceResearchDataset"):
        evaluate_calibration_dataset(spec, object())  # type: ignore[arg-type]


def test_generic_runner_validates_scenario_and_factory() -> None:
    scenario = CalibrationScenario("scenario", "treatment", 2)

    with pytest.raises(TypeError, match="CalibrationScenario"):
        run_calibration_replicates(
            object(),  # type: ignore[arg-type]
            seeds=(1,),
            dataset_factory=lambda _spec: _dataset(),
        )

    with pytest.raises(TypeError, match="callable"):
        run_calibration_replicates(
            scenario,
            seeds=(1,),
            dataset_factory=object(),  # type: ignore[arg-type]
        )


def test_run_and_summarize_combines_replicates_and_summary() -> None:
    scenario = CalibrationScenario("scenario", "treatment", 2)

    def factory(_spec: CalibrationRunSpec) -> FinanceResearchDataset:
        return _dataset()

    runs, summary = run_and_summarize_calibration(
        scenario,
        seeds=(7, 9),
        dataset_factory=factory,
    )

    assert tuple(run.spec.seed for run in runs) == (7, 9)
    assert summary.seeds == (7, 9)
    assert summary.replicate_count == 2
    assert summary.metric("mid_realized_volatility").mean == 0.0


def test_summary_public_validation_and_single_replicate_semantics() -> None:
    with pytest.raises(InvalidCalibrationError, match="non-empty tuple"):
        summarize_calibration_runs(())
    with pytest.raises(InvalidCalibrationError, match="non-empty tuple"):
        summarize_calibration_runs([])  # type: ignore[arg-type]
    with pytest.raises(InvalidCalibrationError, match="CalibrationRunResult"):
        summarize_calibration_runs((object(),))  # type: ignore[arg-type]

    summary = summarize_calibration_runs((_result(),))
    metric = summary.metric("mid_realized_volatility")
    assert metric.defined_replicates == 1
    assert metric.mean == 0.0
    assert metric.sample_std is None
    assert metric.standard_error is None

    with pytest.raises(KeyError):
        summary.metric("does-not-exist")


def test_summary_rejects_duplicate_replicate_seeds() -> None:
    with pytest.raises(InvalidCalibrationError, match="seeds"):
        summarize_calibration_runs(
            (
                _result(replicate=0, seed=7),
                _result(replicate=1, seed=7),
            )
        )


@pytest.mark.parametrize("non_finite", [float("nan"), float("inf"), float("-inf")])
def test_summary_rejects_non_finite_defined_metrics(non_finite: float) -> None:
    bad = replace(_result(), mid_realized_volatility=non_finite)
    with pytest.raises(InvalidCalibrationError, match="finite"):
        summarize_calibration_runs((bad,))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scenario_id": ""},
        {"treatment_id": ""},
        {"periods": True},
        {"noise_activity_bps": -1},
        {"noise_activity_bps": True},
    ],
)
def test_baseline_config_rejects_additional_contract_boundaries(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(InvalidCalibrationError):
        ConstantFundamentalBenchmarkConfig(**kwargs)  # type: ignore[arg-type]


def test_benchmark_public_functions_reject_wrong_config_type() -> None:
    with pytest.raises(TypeError, match="ConstantFundamentalBenchmarkConfig"):
        run_constant_fundamental_benchmark(
            object(),  # type: ignore[arg-type]
            seeds=(1,),
        )

    with pytest.raises(TypeError, match="ConstantFundamentalBenchmarkConfig"):
        run_passive_depth_sweep(
            object(),  # type: ignore[arg-type]
            passive_quantities=(Decimal("2"),),
            seeds=(1,),
        )


@pytest.mark.parametrize(
    "quantities",
    [
        [],
        (),
        (Decimal("2"), Decimal("2")),
        (Decimal("0"),),
    ],
)
def test_depth_sweep_rejects_invalid_treatment_grid(quantities: object) -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=2,
        passive_quantity=Decimal("1"),
        noise_trader_count=1,
        noise_quantity=Decimal("1"),
    )
    with pytest.raises(InvalidCalibrationError):
        run_passive_depth_sweep(
            config,
            passive_quantities=quantities,  # type: ignore[arg-type]
            seeds=(1,),
        )


def test_constant_fundamental_benchmark_is_repeatable_for_same_seed() -> None:
    config = ConstantFundamentalBenchmarkConfig(
        periods=3,
        passive_quantity=Decimal("1"),
        noise_trader_count=1,
        noise_quantity=Decimal("1"),
        noise_activity_bps=10_000,
    )

    first = run_constant_fundamental_benchmark(config, seeds=(8128,))
    second = run_constant_fundamental_benchmark(config, seeds=(8128,))

    assert first.scenario == second.scenario
    assert first.runs == second.runs
    assert first.summary == second.summary
