# ADR-014: Stability, synchronization, and tail-event metric semantics

## Status

Accepted.

## Decision summary

Phase 8B adds framework-independent stability metrics over `FinanceResearchDataset`.

- Full-sample realized volatility is `sqrt(sum(log_return**2))`, with no annualization.
  Missing prices or period gaps make the full-sample value undefined.
- Rolling realized volatility uses the same formula over an explicit trailing window and is
  undefined unless the complete window is present.
- Drawdown is `P_t / running_peak_t - 1`; missing prices remain undefined and do not erase the
  previous peak. Maximum drawdown is the minimum defined drawdown.
- Depth depletion is `1 - depth_t / reference_depth`.
- Spread amplification is `spread_t / reference_spread - 1`.
  Both references are explicit caller inputs; the library never guesses a baseline.
- Absolute dislocation is the absolute value of the ADR-013 signed fundamental-deviation metrics.
- Decision and accepted-order sign concentration are unweighted
  `abs(N_buy-N_sell)/(N_buy+N_sell)` measures. HOLD is preserved but excluded from the
  directional denominator. These are distinct from quantity-weighted flow imbalance.
- Extreme-return, downside-return, and drawdown breach indicators require explicit thresholds.
  No universal crash threshold is hard-coded. Drawdown thresholds satisfy `0 < threshold <= 1`.
- Undefined underlying returns/drawdowns remain undefined indicators, not `False`.

Recovery time is deferred because it requires an externally defined shock/reference window and
recovery criterion. Cross-time sign persistence, pairwise correlations, VaR/ES, and calibrated
stress thresholds are also deferred to later experiment-analysis layers.
