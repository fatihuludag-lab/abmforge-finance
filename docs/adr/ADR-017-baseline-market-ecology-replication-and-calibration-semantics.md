# ADR-017: Baseline market ecology, replication, and calibration semantics

## Status

Accepted.

## Context

Before narrative or AI-agent treatments are introduced, the project needs a
reproducible control ecology and a clear distinction between software invariants,
synthetic comparative statics, and empirical calibration. Tuning parameters until a
desired empirical result appears would create circular validation risk.

## Decision

One replicate is identified by `scenario × treatment × replicate index × explicit
seed`. Scenario/treatment parameters are canonicalized as sorted string key/value
pairs and hashed with SHA-256. The seed is excluded from the scenario fingerprint
because it identifies a replicate rather than a treatment definition.

Replicate seeds are explicit, ordered, and unique. Multi-treatment sweeps reuse the
same seed tuple. Stable component names and `finance_seed()` therefore provide a
common-random-number design when stochastic components and agent identities are
otherwise unchanged.

Replicate outcomes are computed from immutable `FinanceResearchDataset` values using
existing public metrics. Exact quantities remain `Decimal`; statistical volatility
uses the existing finite-float realized-volatility contract.

Treatment summaries report defined-replicate count, arithmetic mean, sample standard
deviation, standard error, minimum, and maximum. These are descriptive summaries only.
No p-values, confidence intervals, multiple-testing corrections, empirical fitting, or
empirical claims are produced by this milestone.

The first controlled ecology uses one constant fundamental, one dynamic passive bid
provider, one dynamic passive ask provider, and one or more explicitly seeded noise
traders. Funding and inventory are derived deterministically from the configured
horizon and worst-case same-side noise demand. Passive depth must cover that
same-period demand so account shortfalls do not confound the benchmark.

Passive-depth treatments reuse the same replicate seeds and noise-agent identities.
The initial mechanistic assertion is only that greater configured passive quantity
produces greater displayed depth under otherwise identical stochastic demand. The
library does not encode a universal claim that greater depth must reduce volatility in
every replicate.

## Consequences

ABMForge-Finance gains a reproducible baseline ecology before narrative/AI treatments.
Treatment provenance is explicit and hashable, replicate results remain inspectable,
and descriptive statistics are separated from model execution.

Empirical parameter fitting, stylized-fact targets, formal treatment contrasts,
confidence intervals, sensitivity analysis, and robustness regions remain later
Phase 9C milestones.
