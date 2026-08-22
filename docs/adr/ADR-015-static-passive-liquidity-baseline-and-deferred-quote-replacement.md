# ADR-015: Static passive-liquidity baseline and deferred quote replacement

## Status

Accepted.

## Context

The finance adapter currently asks each `TradingPolicy` for exactly one `TradingDecision` per
period, and the finance research dataset enforces one decision row per `(period, agent_id)`.
A realistic market maker eventually needs cancel/replace behavior and may emit multiple actions
within one period. Introducing a generic action batch now would therefore require simultaneous
changes to the policy protocol, adapter orchestration, cancellation audit records, and research
dataset schema.

Phase 9A only needs a controlled source of passive two-sided liquidity for baseline market
ecology and sanity experiments.

## Decision

Add `PassiveLiquidityPolicy`, a framework-independent one-shot, one-sided quoting policy.

Each policy instance:

- owns exactly one `Side`;
- uses the observation's latent `fundamental_value` as the reference;
- receives explicit `tick_size`, `quantity`, `offset_ticks`, and `quote_step`;
- emits exactly one GTC limit-order decision on `quote_step`;
- emits `HOLD` on every other period;
- never imports or calls `Exchange` directly.

BUY quotes use `floor(fundamental / tick_size) - offset_ticks`; SELL quotes use
`ceil(fundamental / tick_size) + offset_ticks`. The resulting tick count is converted back to an
exact `Decimal` price. `offset_ticks >= 1` guarantees that a paired BUY/SELL configuration sharing
the same reference cannot cross.

A two-sided Phase 9A baseline is represented by two independently registered and independently
funded traders, one on each side. This is a controlled liquidity fixture, not a claim that the two
participants constitute a realistic single dealer balance sheet.

## Deferred work

Dynamic quote replacement is intentionally deferred to Phase 9B. The existing exchange already
supports ownership-aware cancellation, but a proper dynamic provider should not bypass the policy
boundary. Phase 9B will decide how cancel/replace and multi-action output are represented and
recorded before changing the one-decision-per-agent research schema.

Inventory skew, adaptive spreads, Avellaneda-Stoikov quoting, latency, learning, RL, and LLM-based
market making remain out of scope for this baseline.

## Consequences

- The current `TradingPolicy -> TradingDecision` contract remains backward compatible.
- Research recording remains schema-v1 compatible.
- Static constant-fundamental experiments gain explicit, reproducible two-sided depth.
- Quotes are visible as normal policy decisions and normal exchange orders in research artifacts.
- Dynamic-fundamental market making still requires Phase 9B cancel/replace semantics.
