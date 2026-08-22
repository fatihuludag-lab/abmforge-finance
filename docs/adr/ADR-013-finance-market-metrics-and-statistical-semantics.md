# ADR-013: Finance market metrics and statistical semantics

## Status

Accepted.

## Context

The finance research dataset now provides exact period-level market states, policy decisions,
order outcomes, trades, cash, and positions. Research claims about liquidity, order-flow
synchronization, price dislocation, and volatility require derived metrics whose mathematical
meaning is fixed before experiments are run.

Metric definitions must not silently forward-fill missing prices, bridge time gaps, mix
fundamental values with market prices, or confuse attempted, accepted, and executed order flow.

## Decision

Add a framework-independent `abmforge_finance.metrics` layer. Phase 8A provides deterministic
primitive metrics over `FinanceResearchDataset`; it does not import ABMForge or mutate recorded
data.

Price-based metrics require an explicit `MarketPriceBasis`:

- `MID`: recorded midpoint;
- `LAST_TRADE`: recorded last trade price.

No automatic fallback is performed between these bases.

For consecutive recorded periods:

- simple return: `P_t / P_(t-1) - 1`;
- log return: `ln(P_t / P_(t-1))`.

The first observation, a missing endpoint, or a non-consecutive period gap produces an undefined
(`None`) return. Prices are never forward-filled.

Liquidity primitives are:

- relative spread: `spread / mid_price`;
- total displayed depth: `bid_depth + ask_depth`.

Price dislocation primitives are:

- signed fundamental deviation: `P_t - F_t`;
- relative fundamental deviation: `P_t / F_t - 1`.

Directional-flow imbalance is always normalized as:

`(Q_buy - Q_sell) / (Q_buy + Q_sell)`.

Three distinct populations are retained:

- policy-decision flow: quantity from every ORDER decision; HOLD contributes no directional
  quantity;
- accepted-order flow: original submitted quantity for accepted orders only;
- aggressor executed flow: quantity executed immediately by the incoming order at its submission
  event.

The third measure is explicitly not total market volume and does not reassign later passive fills
to an old resting-order submission period.

Trade primitives are:

- period trade count;
- period trade volume: sum of committed trade quantity;
- VWAP: `sum(price * quantity) / sum(quantity)`.

When market-state rows are present, their periods define the canonical time axis for event metrics;
event periods outside that set are included as well. No-event periods therefore receive zero
trade count/volume and undefined normalized imbalance or VWAP.

Exact algebraic metrics use `Decimal`. Natural-log returns use finite Python `float` values because
they are statistical derived quantities rather than accounting state.

## Consequences

- Missing prices and time gaps remain visible instead of being silently imputed.
- Decision intent, accepted submissions, aggressor execution, and total trade volume remain
  analytically distinct.
- The flagship narrative-homogeneity study can later connect decision synchronization to order
  flow and liquidity without changing metric semantics.
- Rolling volatility, drawdown, crash/tail thresholds, cross-agent sign correlation, stress
  validation, and annualization are deferred to Phase 8B.
