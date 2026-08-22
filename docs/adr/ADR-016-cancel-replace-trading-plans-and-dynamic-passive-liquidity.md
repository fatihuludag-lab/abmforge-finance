# ADR-016: Cancel/replace trading plans and dynamic passive liquidity

## Status

Accepted and implemented.

## Context

The finance model preserves one `TradingDecision` per trader and period because that
contract is useful for reproducibility, decision-level metrics, and the
`(period, agent_id)` research key. Dynamic passive liquidity nevertheless requires a
resting quote to be cancelled before a replacement quote is submitted.

A fully general multi-order action batch would broaden the policy, adapter, recorder,
artifact, and metric contracts at once. The dynamic-liquidity milestone does not
require that breadth.

## Decision

Introduce an immutable `TradingPlan` with zero or more `CancelIntent` values and
exactly one existing `TradingDecision`, which may be `HOLD`.

Legacy `TradingPolicy.decide()` remains supported. `Trader.plan()` normalizes a legacy
decision into a no-cancellation plan. A structural `TradingPlanPolicy` can instead
receive the trader's own active order identifiers and return a cancel/replace plan.

`DynamicPassiveLiquidityPolicy` is one-sided and stateless. Each period it requests
cancellation of its currently active order identifiers and emits one replacement GTC
limit decision around the current fundamental reference using the same outward
tick-grid rule as the static passive baseline.

Policies never receive `Exchange` and never call cancellation or submission directly.

## Deterministic execution semantics

All policies observe the same pre-action market snapshot. The adapter then:

1. collects every trader plan;
2. validates every cancellation intent before mutating the exchange;
3. executes all valid cancellations in deterministic trader/plan order;
4. executes all replacement submissions in deterministic trader order;
5. records resulting trades, balances, positions, and post-action market state.

Therefore all cancellations occur before any new submission in a period. Cancellation
ownership remains enforced by `Exchange.cancel()`. Invalid, duplicate, inactive, or
foreign cancellation targets are rejected before the cancellation phase mutates the
exchange.

## Participant-scoped active-order view

`Exchange.active_order_ids(participant_id)` exposes only immutable identifiers for
orders currently resting on behalf of that registered participant. Identifiers are
returned in original submission order. Policies do not receive book internals or
other participants' active-order sets.

## Research provenance and schema evolution

The decision table retains its one-row-per-`(period, agent_id)` semantics.

Finance dataset schema `1.1` adds a separate `cancellations` table containing period,
cancellation sequence number, agent identifier, cancelled order identifier, original
order sequence number, instrument, side, original limit price, and cancelled remaining
quantity.

Artifact schema `1.1` serializes the same table to canonical JSONL and CSV and includes
it in deterministic manifest membership, row counts, and SHA-256 integrity metadata.

The change is additive: existing participant, decision, order, trade, market-state,
account, and position meanings are unchanged.

## Consequences

Existing one-decision policies remain source-compatible. Dynamic passive liquidity can
reprice without mutable policy state or direct Exchange access. Stale passive quotes
do not accumulate when the reference value changes, and cancel/replace activity is
independently auditable from submitted orders and trades.

Arbitrary multiple new submissions per trader-period, inventory-aware quoting,
adaptive spreads, multi-level books, latency, RL, and LLM market makers remain later
extensions.
