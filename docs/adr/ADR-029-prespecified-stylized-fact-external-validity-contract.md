# ADR-029: Prespecified stylized-fact external-validity contract

## Status

Accepted.

## Decision

Phase 11 is an external-validity layer separate from the completed flagship
confirmatory and robustness families. It must not retroactively modify the flagship
protocol, primary hypotheses, multiplicity family, or robustness interpretation.

The first validation protocol is `stylized-fact-validation-v1`. It inherits the
CI-green flagship baseline ecology by fingerprint, fixes narrative homogeneity at the
control value `H=0`, and repeats the frozen bullish/bearish four-period direction cycle
over a longer simulation horizon. The design uses 256 burn-in periods followed by
4,096 analysis periods, 16 deterministic independent replicates, midpoint log returns,
and a maximum ACF lag of 20. Only post-burn-in observations are eligible for signature
estimation.

Seven signatures are frozen before validation execution. SF-04 through SF-06 are the
primary external-validity signatures because they are closest to the flagship
microstructure mechanism: aggressive-flow price impact, liquidity-conditioned impact,
and liquidity fragility. Return autocorrelation, tail shape, volatility clustering, and
aggressor-sign persistence remain diagnostic signatures and cannot redefine the
flagship result.

The flow variable is explicitly `aggressor-executed-flow-imbalance`, matching the
existing finance recorder and metric semantics. It is not labelled generic order-flow
imbalance or limit-order-book OFI. This prevents later empirical work from comparing
different estimands under the same name.

The empirical comparison interval is prespecified as the 5th to 95th percentile of an
empirical reference distribution constructed with the same estimator implementation
used for simulation. Later concordance reporting may classify a signature as
`concordant`, `direction-only`, `discordant`, or `uninformative`.

Phase 11 is descriptive external validation. It creates no new confirmatory p-value
family or multiplicity procedure. Model calibration against observed stylized-fact
results is forbidden in this protocol. If a diagnostic or primary signature fails,
the failure is reported rather than repaired by post-hoc parameter tuning.

The empirical market-data contract, empirical sampling interval, shared estimator
implementation, long-horizon execution artifact, and simulation-to-empirical comparison
artifact are deferred to subsequent Phase 11 subphases. No official 69,632-period
validation execution occurs as part of Phase 11A.
