# ADR-019: Paired treatment contrasts and confidence intervals

## Status

Accepted.

## Context

Phase 9C.1 established explicit replicate seeds and Phase 9C.2 reused those seeds
across treatment sweeps. The resulting common-random-number design creates natural
within-seed pairs. Treating those runs as independent samples would discard the design
and generally inflate unexplained Monte Carlo variation.

Formal comparison must also remain separate from empirical model fitting and from
multiple-comparison claims.

## Decision

### Estimand

For metric `Y`, control `C`, treatment `T`, and common replicate seed `s`, define

`D_s = Y(T, s) - Y(C, s)`.

The primary treatment effect is the arithmetic mean of the paired differences:

`mean(D_s)`.

The sign convention is always treatment minus control.

### Pairing contract

A paired contrast requires:

- identical ordered replicate seed tuples;
- at least two replicate pairs;
- the same `scenario_id`;
- the same simulation horizon;
- identical canonical parameter keys;
- distinct treatment identifiers; and
- at least one changed canonical parameter value.

Every requested metric must be defined and finite in every pair. Missing values are not
silently dropped because doing so could change the paired design differently across
metrics or treatments.

### Uncertainty

The standard error is computed from the sample standard deviation of paired
differences:

`SE = s_D / sqrt(n)`.

Two-sided confidence intervals use a Student-t critical value with `n - 1` degrees of
freedom:

`mean(D) ± t_(1 - alpha/2, n-1) * SE`.

ABMForge-Finance does not add SciPy as a runtime dependency for this calculation.
The Student-t CDF is evaluated deterministically through the regularized incomplete
beta representation and inverted by bisection. Reference critical-value tests are
included for small and moderate degrees of freedom.

The confidence level is explicit and must be strictly between zero and one.

### Contrast-region summary

Related contrasts can be summarized descriptively by the number of positive, negative,
and exactly zero mean effects, the number of individual intervals excluding zero, and
the minimum/maximum mean effect.

This region summary is not a simultaneous confidence region and applies no
multiple-testing correction. It is a descriptive robustness diagnostic only.

## Consequences

Common-random-number benchmark sweeps can now be analyzed with the paired structure
that was designed into the experiment runner. Effect estimates, standard errors, and
confidence intervals are reproducible and independent of optional statistical
packages.

Multiplicity correction, bootstrap intervals, regression/meta-models, empirical
parameter fitting, and stylized-fact acceptance criteria remain later analysis work.
