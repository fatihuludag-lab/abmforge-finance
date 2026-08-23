"""Validation paths for narrative-stability multi-seed inference."""

from dataclasses import replace
from decimal import Decimal
from functools import lru_cache

import pytest

from abmforge_finance import NarrativeDirection, NarrativeHomogeneityTreatment
from abmforge_finance.calibration import (
    CalibrationExperimentResult,
    CalibrationRunSpec,
    NarrativeStabilityBenchmarkConfig,
    evaluate_narrative_stability_run,
    infer_narrative_stability_sweep,
    run_narrative_stability_benchmark,
    run_narrative_stability_homogeneity_sweep,
)
from abmforge_finance.exceptions import (
    CalibrationInferenceError,
    InvalidCalibrationError,
)
from abmforge_finance.recording import FinanceResearchDataset


def test_sweep_rejects_empty_and_duplicate_homogeneity_grids() -> None:
    config = NarrativeStabilityBenchmarkConfig()

    with pytest.raises(InvalidCalibrationError, match="non-empty"):
        run_narrative_stability_homogeneity_sweep(
            config,
            homogeneities=(),
            seeds=(1, 2),
        )

    with pytest.raises(InvalidCalibrationError, match="unique"):
        run_narrative_stability_homogeneity_sweep(
            config,
            homogeneities=(Decimal("0"), Decimal("0")),
            seeds=(1, 2),
        )


def test_inference_requires_two_experiments_and_explicit_metrics() -> None:
    config = NarrativeStabilityBenchmarkConfig()
    control = run_narrative_stability_benchmark(
        config,
        homogeneity=Decimal("0"),
        seeds=(1, 2),
    )

    with pytest.raises(CalibrationInferenceError, match="at least two"):
        infer_narrative_stability_sweep(
            (control,),
            metric_names=("mean_thin_side_depletion",),
        )

    treatment = run_narrative_stability_benchmark(
        config,
        homogeneity=Decimal("1"),
        seeds=(1, 2),
    )
    with pytest.raises(CalibrationInferenceError, match="non-empty"):
        infer_narrative_stability_sweep(
            (control, treatment),
            metric_names=(),
        )


def test_inference_rejects_duplicate_metrics_and_missing_control() -> None:
    config = NarrativeStabilityBenchmarkConfig()
    experiments = run_narrative_stability_homogeneity_sweep(
        config,
        homogeneities=(Decimal("0.5"), Decimal("1")),
        seeds=(1, 2),
    )

    with pytest.raises(CalibrationInferenceError, match="unique"):
        infer_narrative_stability_sweep(
            experiments,
            metric_names=("trade_volume", "trade_volume"),
            control_homogeneity=Decimal("0.5"),
        )

    with pytest.raises(CalibrationInferenceError, match="exactly one"):
        infer_narrative_stability_sweep(
            experiments,
            metric_names=("trade_volume",),
            control_homogeneity=Decimal("0"),
        )


def test_inference_rejects_invalid_experiment_members() -> None:
    with pytest.raises(CalibrationInferenceError, match="CalibrationExperimentResult"):
        infer_narrative_stability_sweep(
            (object(), object()),  # type: ignore[arg-type]
            metric_names=("trade_volume",),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"direction_schedule": (NarrativeDirection.BULLISH,)},
        {
            "direction_schedule": (
                NarrativeDirection.BULLISH,
                NarrativeDirection.NEUTRAL,
            )
        },
        {"fundamental_value": Decimal("0")},
        {"tick_size": Decimal("NaN")},
        {"narrative_strength": Decimal("NaN")},
        {"narrative_strength": Decimal("0")},
        {"narrative_confidence": Decimal("1.1")},
        {"passive_levels": True},
        {"noise_activity_bps": 10_001},
        {"decision_threshold": Decimal("-0.1")},
        {"narrative_quantity": Decimal("1.5")},
        {
            "fundamental_value": Decimal("3"),
            "passive_levels": 3,
            "passive_quantity_per_level": Decimal("5"),
        },
        {"scenario_id": ""},
    ],
)
def test_config_validation_covers_phase10c2_numeric_contracts(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(InvalidCalibrationError):
        NarrativeStabilityBenchmarkConfig(**kwargs)  # type: ignore[arg-type]


def test_treatment_requires_decimal_homogeneity() -> None:
    config = NarrativeStabilityBenchmarkConfig()

    with pytest.raises(InvalidCalibrationError, match="homogeneity must be a Decimal"):
        config.treatment(0.5)  # type: ignore[arg-type]


def test_public_runners_reject_wrong_config_types_and_grid_container() -> None:
    with pytest.raises(TypeError, match="NarrativeStabilityBenchmarkConfig"):
        run_narrative_stability_benchmark(
            object(),  # type: ignore[arg-type]
            homogeneity=Decimal("0"),
            seeds=(1, 2),
        )

    with pytest.raises(TypeError, match="NarrativeStabilityBenchmarkConfig"):
        run_narrative_stability_homogeneity_sweep(
            object(),  # type: ignore[arg-type]
            homogeneities=(Decimal("0"), Decimal("1")),
            seeds=(1, 2),
        )

    with pytest.raises(InvalidCalibrationError, match="non-empty tuple"):
        run_narrative_stability_homogeneity_sweep(
            NarrativeStabilityBenchmarkConfig(),
            homogeneities=[Decimal("0"), Decimal("1")],  # type: ignore[arg-type]
            seeds=(1, 2),
        )


def _valid_spec_and_treatment() -> tuple[
    NarrativeStabilityBenchmarkConfig,
    CalibrationRunSpec,
    NarrativeHomogeneityTreatment,
]:
    config = NarrativeStabilityBenchmarkConfig()
    treatment = config.treatment(Decimal("0"))
    spec = CalibrationRunSpec(config.scenario(Decimal("0")), 0, 1)
    return config, spec, treatment


def test_run_evaluator_rejects_wrong_public_argument_types() -> None:
    config, spec, treatment = _valid_spec_and_treatment()
    dataset = FinanceResearchDataset()

    with pytest.raises(TypeError, match="CalibrationRunSpec"):
        evaluate_narrative_stability_run(
            object(),  # type: ignore[arg-type]
            dataset,
            treatment,
            reference_side_depth=config.reference_side_depth,
            reference_spread=config.reference_spread,
        )

    with pytest.raises(TypeError, match="FinanceResearchDataset"):
        evaluate_narrative_stability_run(
            spec,
            object(),  # type: ignore[arg-type]
            treatment,
            reference_side_depth=config.reference_side_depth,
            reference_spread=config.reference_spread,
        )

    with pytest.raises(TypeError, match="NarrativeHomogeneityTreatment"):
        evaluate_narrative_stability_run(
            spec,
            dataset,
            object(),  # type: ignore[arg-type]
            reference_side_depth=config.reference_side_depth,
            reference_spread=config.reference_spread,
        )


def _replace_parameter(
    parameters: tuple[tuple[str, str], ...],
    key: str,
    value: str,
) -> tuple[tuple[str, str], ...]:
    return tuple(
        (parameter, value if parameter == key else current) for parameter, current in parameters
    )


def test_run_evaluator_rejects_wrong_family_and_missing_homogeneity() -> None:
    config, spec, treatment = _valid_spec_and_treatment()
    dataset = FinanceResearchDataset()

    wrong_family = replace(
        spec.scenario,
        parameters=_replace_parameter(
            spec.scenario.parameters,
            "benchmark_family",
            "other-family",
        ),
    )
    with pytest.raises(InvalidCalibrationError, match="not a narrative-stability"):
        evaluate_narrative_stability_run(
            replace(spec, scenario=wrong_family),
            dataset,
            treatment,
            reference_side_depth=config.reference_side_depth,
            reference_spread=config.reference_spread,
        )

    missing_h = replace(
        spec.scenario,
        parameters=tuple(item for item in spec.scenario.parameters if item[0] != "homogeneity"),
    )
    with pytest.raises(InvalidCalibrationError, match="valid homogeneity"):
        evaluate_narrative_stability_run(
            replace(spec, scenario=missing_h),
            dataset,
            treatment,
            reference_side_depth=config.reference_side_depth,
            reference_spread=config.reference_spread,
        )


def test_run_evaluator_rejects_scenario_treatment_mismatch_and_window_mismatch() -> None:
    config, spec, treatment = _valid_spec_and_treatment()
    dataset = FinanceResearchDataset()

    mismatched_treatment = config.treatment(Decimal("0.5"))
    with pytest.raises(InvalidCalibrationError, match="does not match"):
        evaluate_narrative_stability_run(
            spec,
            dataset,
            mismatched_treatment,
            reference_side_depth=config.reference_side_depth,
            reference_spread=config.reference_spread,
        )

    short_treatment = replace(
        treatment,
        active_until=config.periods - 1,
    )
    with pytest.raises(InvalidCalibrationError, match="full scenario horizon"):
        evaluate_narrative_stability_run(
            spec,
            dataset,
            short_treatment,
            reference_side_depth=config.reference_side_depth,
            reference_spread=config.reference_spread,
        )


@lru_cache(maxsize=1)
def _valid_experiment_pair() -> tuple[
    CalibrationExperimentResult,
    CalibrationExperimentResult,
]:
    config = NarrativeStabilityBenchmarkConfig()
    return (
        run_narrative_stability_benchmark(
            config,
            homogeneity=Decimal("0"),
            seeds=(11, 22),
        ),
        run_narrative_stability_benchmark(
            config,
            homogeneity=Decimal("1"),
            seeds=(11, 22),
        ),
    )


def test_inference_rejects_blank_metric_and_invalid_control_homogeneity() -> None:
    control, treatment = _valid_experiment_pair()

    with pytest.raises(CalibrationInferenceError, match="non-empty strings"):
        infer_narrative_stability_sweep(
            (control, treatment),
            metric_names=(" ",),
        )

    with pytest.raises(CalibrationInferenceError, match="finite Decimal"):
        infer_narrative_stability_sweep(
            (control, treatment),
            metric_names=("trade_volume",),
            control_homogeneity=Decimal("NaN"),
        )


def test_inference_rejects_wrong_family_missing_and_nonfinite_homogeneity_metadata() -> None:
    control, treatment = _valid_experiment_pair()

    wrong_family_scenario = replace(
        control.scenario,
        parameters=_replace_parameter(
            control.scenario.parameters,
            "benchmark_family",
            "other-family",
        ),
    )
    wrong_family = replace(control, scenario=wrong_family_scenario)
    with pytest.raises(CalibrationInferenceError, match="benchmark family"):
        infer_narrative_stability_sweep(
            (wrong_family, treatment),
            metric_names=("trade_volume",),
        )

    missing_h_scenario = replace(
        control.scenario,
        parameters=tuple(item for item in control.scenario.parameters if item[0] != "homogeneity"),
    )
    missing_h = replace(control, scenario=missing_h_scenario)
    with pytest.raises(CalibrationInferenceError, match="expose homogeneity"):
        infer_narrative_stability_sweep(
            (missing_h, treatment),
            metric_names=("trade_volume",),
        )

    nonfinite_h_scenario = replace(
        control.scenario,
        parameters=_replace_parameter(
            control.scenario.parameters,
            "homogeneity",
            "NaN",
        ),
    )
    nonfinite_h = replace(control, scenario=nonfinite_h_scenario)
    with pytest.raises(CalibrationInferenceError, match="finite and in"):
        infer_narrative_stability_sweep(
            (nonfinite_h, treatment),
            metric_names=("trade_volume",),
        )
