# ADR-016: Cancel/replace trading plans and dynamic passive liquidity

## Status

Accepted.

## Context

The existing finance adapter and research dataset deliberately implement one
`TradingDecision` per trader and period. Dynamic passive liquidity nevertheless
requires a resting quote to be cancelled before a replacement quote is submitted.

A fully general multi-order action batch would broaden the policy, adapter, recorder,
artifact, and metric contracts at once. Phase 9B does not yet require that breadth.

## Decision

Introduce an immutable `TradingPlan` with zero or more `CancelIntent` values and
exactly one existing `TradingDecision`, which may itself be `HOLD`.

Legacy `TradingPolicy.decide()` remains supported. `Trader.plan()` normalizes a legacy
decision into a no-cancellation plan. A new structural `TradingPlanPolicy` may instead
receive the trader's active order identifiers and return a plan.

`DynamicPassiveLiquidityPolicy` implements `TradingPlanPolicy`. It is one-sided and
stateless: each period it requests cancellation of active order identifiers supplied by
orchestration and emits one new GTC limit decision around the current fundamental
reference using the same outward tick-grid rule as the static passive baseline.

Policies never receive `Exchange` and never call cancellation or submission directly.

## Reserved execution semantics

The adapter will execute all validated cancellations before any replacement
submissions for a period. All policies continue to observe one common pre-action
snapshot. Cancellation ownership remains enforced by `Exchange.cancel()`.

The one-decision row per trader-period is intentionally preserved. Cancellation
provenance will be added as a separate research table in the next implementation step.

## Consequences

Existing policies remain source-compatible. Dynamic passive liquidity can be expressed
without mutable policy state or Exchange access. Arbitrary multiple submissions per
trader-period remain out of scope. Adapter execution, cancellation recording, dataset
schema 1.1, and artifact-schema evolution are the next Phase 9B step.
