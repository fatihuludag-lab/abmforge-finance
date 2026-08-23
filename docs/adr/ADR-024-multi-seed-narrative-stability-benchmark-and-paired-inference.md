# ADR-024: Multi-seed narrative-stability benchmark and paired inference

## Status

Accepted.

## Context

Phase 10C.1 freezes deterministic narrative-synchronization and downstream
market-stability outcome semantics. Re-running that purely deterministic fixture under
different model seeds would not create a sampling distribution: the narrative schedule
contains no seed-dependent component.

Phase 10C.2 therefore needs an explicit stochastic background while preserving the
homogeneity treatment as the only changed factor and reusing the already-audited
paired Student-t inference machinery from Phase 9C.3.

The experiment layer must remain independent of calibration. Existing architecture
tests deliberately prohibit `experiments/` from importing `calibration/`.

## Decision

### Benchmark placement

The stochastic narrative benchmark lives in `abmforge_finance.calibration`, not in
`experiments/`.

This is a controlled synthetic benchmark and replication layer. It may consume the
Phase 10C.1 experiment/outcome contract, but the lower deterministic experiment layer
does not depend back on calibration.

### Common-random-number design

For each explicit model seed, background `NoisePolicy` agents use stable agent IDs and
stable finance component seed names:

`noise-policy:0000`, `noise-policy:0001`, ...

The same ordered seed tuple and same noise-agent population are reused for every
homogeneity treatment. Therefore a seed-paired contrast compares treatments under the
same deterministic pseudo-random background flow.

The direction schedule itself remains exogenous and identical across treatments.

### Liquidity capacity

The benchmark uses a deterministic multi-level passive-liquidity ladder. Per-side
displayed capacity must strictly exceed worst-case same-side narrative plus noise
demand within one period.

This preserves a two-sided displayed book even under the most synchronized treatment
and the most adverse same-side noise realization. Rejected orders therefore remain an
observed outcome rather than a mechanical consequence of an intentionally exhausted
fixture.

### Replicate result

`NarrativeStabilityRunResult` extends `CalibrationRunResult` and preserves the existing
calibration metrics while adding Phase 10C.1 narrative-specific mediator and liquidity
metrics.

Because it remains a `CalibrationRunResult`, existing treatment summaries and
Phase 9C.3 paired inference can operate without a second statistical implementation.

### Paired inference

For each selected metric and treatment homogeneity `H`, the control is an explicitly
identified homogeneity treatment, normally `H=0`.

For matched seed `s`:

`Delta_s(H) = Y_s(H) - Y_s(H_control)`.

Inference delegates to the existing `paired_treatment_contrast()` implementation,
which requires identical ordered seed tuples and computes the Student-t confidence
interval from paired replicate differences.

The narrative wrapper additionally requires that `homogeneity` is the only changed
canonical scenario parameter.

### Multiplicity and interpretation

`infer_narrative_stability_sweep()` requires the caller to explicitly name metrics.
It does not silently designate a primary endpoint.

Confidence intervals are individual per-metric, per-treatment intervals. The existing
contrast-region summary is descriptive and does not provide family-wise multiplicity
control.

A positive contrast is not universally "worse". Metric direction remains
metric-specific. For example, a more negative maximum drawdown has a different
interpretation from a positive increase in thin-side depletion.

No monotonicity, volatility increase, liquidity deterioration, or tail-risk result is
encoded as a software assertion.

## Consequences

ABMForge-Finance can now generate reproducible common-seed narrative-homogeneity
replicates and send their outcomes through the same paired Student-t engine used by the
calibration benchmark family.

The next scientific step is to prespecify primary/secondary outcomes, seed counts, and
robustness regimes before interpreting empirical simulation results.
