# ADR-030: Shared market-signature estimator semantics

## Status

Accepted.

## Decision

Phase 11 stylized-fact validation uses one source-agnostic estimator implementation for both simulated and empirical market data. Simulation adapters and empirical-data adapters may prepare and align numeric series, but they must call the same estimator functions after preparation. Estimators must not branch on data provenance.

The shared implementation lives in `abmforge_finance.study.stylized_estimators`. It operates on aligned finite numeric sequences and does not depend on `FinanceResearchDataset`, ABMForge, pandas, NumPy, SciPy, exchange state, or empirical-market provider objects. Data extraction, timestamp alignment, resampling, missing-data treatment, forward filling, burn-in removal, and source-specific cleaning remain outside the estimator layer.

The seven frozen Phase 11 signatures are implemented as follows.

SF-01, return linear dependence, uses the lag-1 through lag-K autocorrelation vector of log midpoint returns. The series is centered once around its full-sample arithmetic mean. For lag k,

`ACF(k) = sum_{t=k+1}^n (x_t - x_bar)(x_{t-k} - x_bar) / sum_{t=1}^n (x_t - x_bar)^2`.

The diagnostic summary is the arithmetic mean of the absolute lag autocorrelations.

SF-02, return tail shape, uses population central moments over the supplied analysis sample. Excess kurtosis is

`m4 / m2^2 - 3`,

where `m2` and `m4` divide by the observation count. The standard deviation is `sqrt(m2)`. The empirical two-sided tail probability is the fraction of observations satisfying the strict condition

`abs(r_t - r_bar) > k * sigma`.

The Phase 11A default is `k = 3`.

SF-03, volatility clustering, applies the same autocorrelation estimator used by SF-01 to absolute log midpoint returns. Its diagnostic scalar summary is the arithmetic mean of the signed lag autocorrelations.

SF-04, aggressor-flow price impact, fits ordinary least squares with an intercept:

`r_t = alpha + beta * flow_t + epsilon_t`.

The predictor is the prespecified aggressor-executed-flow-imbalance and the response is the same-interval log midpoint return.

SF-05, liquidity-conditioned price impact, computes low- and high-depth thresholds from the complete aligned pre-interval thin-side-depth series. Quantiles use linear interpolation at position `(n - 1)q`, equivalent to the common Type-7 quantile definition. Low-depth observations satisfy `depth <= Q25`; high-depth observations satisfy `depth >= Q75`. The same intercept-inclusive OLS estimator as SF-04 is then fitted independently within the two strata. The prespecified comparison is

`abs(beta_low) - abs(beta_high)`,

so a positive contrast supports the expected stronger absolute impact under low depth.

SF-06, liquidity fragility, computes Spearman rank correlations between same-interval absolute log midpoint return and (a) relative thin-side-depth drop and (b) pre-interval thin-side depth. Ties receive average ranks. Spearman correlation is Pearson correlation of those rank vectors.

SF-07, aggressor-sign persistence, removes intervals whose aggressor-executed-flow-imbalance is exactly zero before mapping remaining observations to `+1` or `-1`. It then applies the same autocorrelation definition used by SF-01. Its diagnostic scalar summary is the arithmetic mean of the signed lag autocorrelations.

All estimator results are deterministic immutable value objects. Repeated evaluation of identical numeric inputs must produce equal results and no estimator may mutate its input.

Estimator functions reject non-finite observations. They also fail explicitly when an estimator is mathematically undefined, including insufficient observations, non-positive maximum lag, maximum lag greater than or equal to the available series length, zero-variance ACF series, zero-variance OLS predictors, zero-variance correlation ranks, invalid quantile probabilities, non-distinct depth strata, or insufficient non-zero aggressor-flow observations. Undefined estimators must not silently return zero, NaN, infinity, or an imputed statistic.

Pre-interval depth must be non-negative. Phase 11 estimators do not silently clip invalid observations.

The implementation intentionally avoids a new numerical runtime dependency. The frozen estimators are sufficiently small to implement deterministically with the Python standard library. A future dependency change must preserve these statistical semantics and pass the existing oracle and invariance tests before replacing the implementation.

The estimator implementation is protected by hand-calculated oracle tests, tie-handling tests, zero-flow omission tests, invalid-input tests, mathematical invariance tests, and deterministic repeated-evaluation tests.

These choices implement the estimator lock already prespecified by `stylized-fact-validation-v1`: simulation and empirical reference distributions must use the same estimator implementation. Changing an estimator definition after either official simulation validation or empirical-reference construction has begun constitutes a protocol-version change rather than an implementation refactor.
