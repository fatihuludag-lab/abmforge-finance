# ADR-031: Shared market-signature preparation pipeline and source equivalence

## Status

Accepted.

## Context

ADR-029 prespecified the Phase 11 stylized-fact external-validity contract.

ADR-030 froze the statistical semantics of the seven shared market-signature
estimators and required the same estimator implementation for simulated and
empirical data.

Sharing estimators alone is insufficient. Simulation and empirical sources
could still apply different transformations before reaching those estimators.
Phase 11 therefore requires a canonical preparation boundary that freezes
measurement semantics independently of source representation.

## Decision

Phase 11 uses a source-neutral canonical estimator-input contract represented
by `MarketSignatureInput`.

The contract contains exactly four aligned numeric series:

- log midpoint returns;
- aggressor-executed-flow imbalance;
- pre-interval thin-side depth;
- relative thin-side-depth drop.

Source identity is kept separate from statistical data in
`MarketSignatureInputProvenance`.

A complete prepared observation set is represented by
`PreparedMarketSignatureSample`.

The shared execution function `estimate_prepared_market_signatures()` receives
a prepared sample and delegates to the estimators frozen by ADR-030.

Estimator behavior must not branch on source kind or provenance.

## Canonical interval alignment

For analysis interval `t`:

`r_t = log(mid_t / mid_{t-1})`

`flow_t = aggressor-executed-flow imbalance during interval t`

`pre_depth_t = thin_side_depth_{t-1}`

`relative_depth_drop_t =
    (thin_side_depth_{t-1} - thin_side_depth_t)
    / thin_side_depth_{t-1}`

Thin-side depth is the applicable source representation of the minimum
bid-side and ask-side depth.

Pre-interval thin-side depth must be strictly positive when relative depletion
is computed.

## Simulation preparation

Simulation preparation consumes `FinanceResearchDataset`.

It reuses existing ABMForge-Finance metric semantics for midpoint returns,
aggressor-flow imbalance, and thin-side depth rather than creating competing
definitions.

The Phase 11 simulation adapter prepares the frozen post-burn-in analysis
window and must emit exactly the frozen analysis horizon.

Missing required market states, undefined midpoint returns, undefined
aggressor flow, non-positive pre-interval depth, or cross-instrument
contamination are explicit preparation failures.

Undefined simulation aggressor flow is not silently converted to zero.

## Empirical preparation

The generic empirical boundary consists of completed
`EmpiricalMarketInterval` observations.

This generic layer does not:

- download exchange data;
- reconstruct an order book;
- infer aggressor direction;
- resample raw timestamps;
- fill missing intervals;
- forward-fill prices;
- or impute missing observations.

Those responsibilities belong to future source-specific ingestion contracts.

Empirical intervals supplied to the generic adapter must be:

- ordered;
- contiguous;
- non-overlapping;
- equal-width;
- finite;
- positive in midpoint price;
- non-negative in thin-side depth.

A measured empirical aggressor-flow value of zero is valid data and remains
zero. It is not equivalent to missing flow. SF-07 later removes zero-flow
observations according to ADR-030.

## Source equivalence

If simulation and empirical source representations encode the same economic
interval path, both preparation routes must produce equivalent canonical
measurement series.

The repository protects this invariant with a cross-source equivalence test
covering:

- log midpoint returns;
- aggressor flow;
- pre-interval thin-side depth;
- relative thin-side-depth depletion;
- and the resulting SF-01 through SF-07 estimates.

Phase 11 therefore freezes two complementary requirements:

1. same estimator semantics;
2. same measurement semantics before estimation.

## Provenance

Provenance records:

- source kind;
- source identity;
- preparation identity;
- prepared observation count.

Provenance supports auditability and later artifact construction, but it must
not alter statistical estimates.

## Dependency boundary

The canonical pipeline is source-neutral.

`stylized_pipeline.py` must not depend on simulation recording or empirical
source implementations.

`stylized_empirical.py` must remain exchange-neutral and must not depend on a
specific venue, network client, pandas, NumPy, or SciPy.

`stylized_simulation.py` may depend on ABMForge-Finance recording and metric
layers because its purpose is explicitly source-specific preparation.

## Consequences

Simulation and empirical ingestion remain source-specific while scientific
comparison begins only after conversion to the common canonical input
contract.

Future Binance or other exchange adapters must terminate at this boundary.

Any change to interval alignment, flow interpretation, depth definition,
depletion formula, missing-data treatment, or source-equivalence semantics
after official validation begins is a protocol change rather than a refactor.
