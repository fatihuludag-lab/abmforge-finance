"""Integration tests for common-seed narrative-stability inference."""

from decimal import Decimal

from abmforge_finance.calibration import (
    NarrativeStabilityBenchmarkConfig,
    NarrativeStabilityRunResult,
    infer_narrative_stability_sweep,
    run_narrative_stability_benchmark,
    run_narrative_stability_homogeneity_sweep,
)


def test_same_seeded_benchmark_is_exactly_reproducible() -> None:
    config = NarrativeStabilityBenchmarkConfig()
    seeds = (101, 202, 303)

    first = run_narrative_stability_benchmark(
        config,
        homogeneity=Decimal("0.5"),
        seeds=seeds,
    )
    second = run_narrative_stability_benchmark(
        config,
        homogeneity=Decimal("0.5"),
        seeds=seeds,
    )

    assert first == second
    assert first.summary.seeds == seeds
    assert all(isinstance(run, NarrativeStabilityRunResult) for run in first.runs)


def test_homogeneity_sweep_preserves_common_seed_tuple_and_metric_schema() -> None:
    config = NarrativeStabilityBenchmarkConfig()
    seeds = (101, 202, 303, 404)
    homogeneities = (
        Decimal("0"),
        Decimal("0.25"),
        Decimal("0.5"),
        Decimal("0.75"),
        Decimal("1"),
    )

    experiments = run_narrative_stability_homogeneity_sweep(
        config,
        homogeneities=homogeneities,
        seeds=seeds,
    )

    assert len(experiments) == 5
    assert all(experiment.summary.seeds == seeds for experiment in experiments)
    assert (
        tuple(
            Decimal(dict(experiment.scenario.parameters)["homogeneity"])
            for experiment in experiments
        )
        == homogeneities
    )

    metric_schemas = tuple(
        tuple(name for name, _ in experiment.runs[0].metric_items()) for experiment in experiments
    )
    assert all(schema == metric_schemas[0] for schema in metric_schemas)


def test_paired_inference_reuses_phase9c3_engine_without_direction_assertion() -> None:
    config = NarrativeStabilityBenchmarkConfig()
    seeds = (101, 202, 303, 404)
    experiments = run_narrative_stability_homogeneity_sweep(
        config,
        homogeneities=(
            Decimal("0"),
            Decimal("0.25"),
            Decimal("0.5"),
            Decimal("0.75"),
            Decimal("1"),
        ),
        seeds=seeds,
    )

    inference = infer_narrative_stability_sweep(
        experiments,
        metric_names=(
            "mean_thin_side_depletion",
            "mid_realized_volatility",
        ),
    )

    assert tuple(item.metric_name for item in inference) == (
        "mean_thin_side_depletion",
        "mid_realized_volatility",
    )
    for metric in inference:
        assert metric.control_homogeneity == Decimal("0")
        assert len(metric.contrasts) == 4
        assert metric.region.contrast_count == 4
        for contrast in metric.contrasts:
            assert contrast.seeds == seeds
            assert contrast.pair_count == 4
            assert contrast.changed_parameters[0][0] == "homogeneity"
            assert len(contrast.changed_parameters) == 1
