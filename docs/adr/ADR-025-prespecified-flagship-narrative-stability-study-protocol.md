# ADR-025: Prespecified flagship narrative-stability study protocol

## Status

Accepted.

## Decision

The flagship confirmatory study is frozen before confirmatory results are run or
interpreted. Development fixtures used to validate software mechanisms are not
confirmatory study results.

The treatment grid is `H={0, 0.25, 0.50, 0.75, 1.00}`, with `H=0` as control.

Primary outcomes are `mean_thin_side_depletion` and
`mean_absolute_relative_dislocation`. Secondary outcomes are depth asymmetry,
midpoint realized volatility, and maximum drawdown. Decision, accepted-order, and
executed-flow concentration are mechanism outcomes. Remaining liquidity, spread,
rejection, execution-volume, and market-volume fields are diagnostic.

The primary multiplicity family contains two primary metrics crossed with four
non-control contrasts: eight hypotheses. Holm family-wise control at alpha 0.05 is
prespecified. Phase 10D records this decision but does not duplicate the existing
paired Student-t engine; a later reporting layer must implement and test Holm-adjusted
decisions before confirmatory claims are produced.

Replicate count is selected using an independent precision pilot with nested candidate
counts `10, 20, 40, 80, 160`. Selection uses confidence-interval width only, never
effect direction or significance. All four treatment-vs-control contrasts must meet
both absolute half-width targets:

- thin-side depletion: at most `0.02`;
- absolute relative dislocation: at most `0.0025`.

These are design tolerances, not estimated effect sizes. If no candidate through 160
meets both targets, the confirmatory run does not begin without a protocol amendment.

Pilot and confirmatory seeds are deterministically derived from distinct namespaces
and the protocol fingerprint. Pilot seeds are not reused for confirmatory effect
estimation.

The primary regime uses the default narrative-stability benchmark configuration.
Prespecified one-factor-at-a-time robustness regimes vary passive liquidity, noise
activity, noise population, direction clustering, or polarity. Robustness runs do not
replace the primary regime.

The protocol is distributed as immutable Python contracts plus a bundled JSON
snapshot. Runtime and JSON representations must have the same canonical SHA-256
fingerprint.
