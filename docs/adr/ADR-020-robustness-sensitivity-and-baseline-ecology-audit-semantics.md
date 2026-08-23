# ADR-020: Robustness, sensitivity, and baseline ecology audit semantics

## Status

Accepted.

## Context

Phase 9C.1 established explicit scenarios and replication, Phase 9C.2 added controlled
treatment families, and Phase 9C.3 added seed-paired treatment contrasts with
Student-t confidence intervals. A final calibration-layer step is needed to summarize
whether comparative-static directions persist across a parameter region without
turning individual confidence intervals into a false simultaneous-inference claim or
turning synthetic validation into a claim of empirical realism.

## Decision

### Parameter-family audit

A treatment-family audit compares every supplied treatment with one explicit control
using the existing common-seed paired-contrast contract.

The audit is intentionally restricted to a **single changed canonical parameter**.
If a treatment differs from the control on more than one parameter, the family audit
rejects it rather than attaching a sensitivity interpretation to a confounded
comparison.

### Directional robustness

For one metric and one parameter family, mean paired effects are classified as:

- `ROBUST_POSITIVE`: all audited mean effects are positive;
- `ROBUST_NEGATIVE`: all audited mean effects are negative;
- `ROBUST_ZERO`: all audited mean effects are exactly zero;
- `MIXED`: effect directions differ across treatment points; or
- `INSUFFICIENT`: fewer than the configured minimum number of contrasts are present.

The default minimum is two contrasts. The minimum is explicit metadata rather than an
implicit significance threshold.

`ROBUST_*` means directional consistency across the supplied treatment region. It
does **not** mean that every individual interval excludes zero, that a simultaneous
confidence statement holds, that an economic law has been established, or that the
model is empirically realistic.

Individual confidence-interval exclusion counts remain separate descriptive fields.

### Normalized sensitivity

When both the treatment parameter and metric have valid non-zero control scales, the
audit may report the dimensionless normalized sensitivity

`S = ((Y_T - Y_C) / Y_C) / ((X_T - X_C) / X_C)`.

Sensitivity is left undefined, with an explicit reason, when:

- the parameter cannot be parsed as a finite number;
- the control parameter is zero;
- the control metric mean is zero; or
- different canonical strings represent no numerical parameter change.

The library does not invent offsets or epsilon denominators to force an elasticity to
exist.

### Baseline ecology audit

A `BaselineEcologyAudit` aggregates named treatment-family audits, records missing and
insufficient families, records mixed-direction findings, checks whether families share
one replicate seed tuple, and counts individual confidence intervals excluding zero.

Its `complete` property means only that requested families are present and not
classified as insufficient. Mixed findings do not make an audit incomplete because
they are substantive results rather than execution failures.

Audit completion is not a certificate of empirical realism, external validity, model
calibration quality, or publication readiness.

### Statistical boundary

Phase 9C.4 does not add multiple-testing correction, simultaneous confidence bands,
bootstrap intervals, regression/meta-models, empirical fitting, or stylized-fact
acceptance thresholds.

## Consequences

The baseline market ecology can be summarized reproducibly across controlled parameter
regions before narrative or AI-agent treatments are introduced. Mechanical invariants,
paired statistical uncertainty, directional robustness, and normalized sensitivity
remain distinct concepts with explicit semantics.
