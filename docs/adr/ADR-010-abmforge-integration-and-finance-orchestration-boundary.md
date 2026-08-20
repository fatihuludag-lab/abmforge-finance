# ADR-010: ABMForge Integration and Finance Orchestration Boundary

## Status

Accepted for Phase 6B.

## Context

The finance package now has a framework-independent market core (`Exchange`, matching,
clearing, accounts/portfolios), deterministic market time and fundamental values, and a
framework-independent trader/policy layer. The missing bridge is reproducible execution
inside ABMForge `Scenario` / `Experiment` runs without moving finance mechanisms into the
ABMForge core or duplicating ABMForge's lifecycle.

ABMForge owns model construction from `parameters` and `seed`, calls `setup()`, invokes
`step()`, increments `Model.steps` and `Model.time`, and calls `Recorder.collect()` after
each completed step. The finance adapter therefore must integrate at the `Model.step()`
boundary rather than reproduce those responsibilities.

`TradingDecision` intentionally omits order identifiers, timestamps, and submission
sequence numbers. Those values must be assigned once at an authoritative orchestration
boundary before a decision reaches `Exchange`.

## Decision

1. All direct imports of `abmforge` remain under `abmforge_finance.adapters`.
   Domain, market, trader, and policy modules remain framework-independent.
2. `FinanceABMModel` subclasses ABMForge `Model` and preserves its constructor contract:
   `parameters=...` and `seed=...` only.
3. User models implement `build_finance_components()` and return `FinanceComponents`
   containing one `Exchange`, one `MarketClock`, one `FundamentalValueProcess`, and an
   immutable tuple of finance `Trader` values.
4. Finance traders are **not** inserted into `Model.agents`. `Exchange` remains the
   authoritative economic state; finance-specific participant tables are deferred to the
   dedicated recorder milestone.
5. At setup, trader IDs are validated, registered exchange participants are required,
   finance time must equal `Model.steps`, and adapter order sequencing starts from the
   exchange's public `next_submission_sequence`.
6. Each finance period uses one common **pre-action** order-book snapshot. All policies
   decide from that same market information set; only personal cash/inventory fields vary
   by trader. This prevents within-period information leakage from earlier executions.
7. Decisions are collected before any order is executed. Decisions are then executed in
   lexicographic `agent_id` order. This is deterministic but can create execution-order
   effects; alternative seeded activation is a later experimental factor.
8. For each `ORDER` decision, the adapter assigns a globally increasing submission
   sequence, deterministic `finance-order-{sequence:012d}` ID, and the current integer
   market period as `submitted_at`. Sequence identity is consumed even when the exchange
   rejects the order, so later identity does not depend on retry behavior.
9. Invalid tick/lot decisions and insufficient cash/inventory are modeled as expected
   order rejections and retained in `FinanceOrderOutcome`. Matching, exchange-invariant,
   duplicate-identity, clock, and other programming/integration failures propagate.
10. `MarketClock` advances exactly once inside every successful `FinanceABMModel.step()`.
    ABMForge increments `Model.steps` immediately afterward, restoring equality before the
    next finance period. Direct repeated manual calls to `step()` therefore fail with a
    clock-drift error rather than silently diverging.
11. Component seeds are derived from the explicit ABMForge model seed and a normalized
    component name using a versioned SHA-256 namespace. The derivation is cached and
    call-order-independent. A model without an explicit seed cannot request a finance
    component seed.
12. A compact set of model-level finance metrics is registered with ABMForge `Recorder`.
    Exact finance state remains `Decimal`; recorder projections use finite Python numeric
    values suitable for the current generic dataset. Exact finance-specific tables and
    Parquet artifacts are deferred to the finance-recorder milestone.
13. `MatchingEngine` / `Exchange` expose read-only `next_submission_sequence` and
    `last_submitted_at` introspection. These are generic orchestration capabilities, not
    ABMForge-specific behavior.

## Alternatives considered

### Put finance traders into `Model.agents`

Rejected for the first adapter. It would either duplicate cash/inventory state or force
framework inheritance into a layer deliberately designed to remain portable to future
Gymnasium, PettingZoo, and non-ABMForge execution contexts.

### Let policies create `Order` directly

Rejected. This would let policy logic control exchange identity, timestamping, and event
sequence, weakening replay and mixing behavioral assumptions with market mechanics.

### Execute each trader immediately after observing the market

Rejected for the baseline because later traders would observe mutations caused by earlier
traders in the same nominal period. The chosen two-stage decision/execution structure
freezes the information set while retaining explicit deterministic execution order.

### Use ABMForge's default RNG directly for finance component seeds

Rejected for named finance components because stream consumption order could then become
part of model identity. A keyed seed derivation gives stable component identity from the
scenario seed without consuming unrelated RNG state.

## Consequences

- `Scenario` and `Experiment` can construct finance models using their normal model
  contract.
- Finance mechanisms remain testable as ordinary Python independently of ABMForge.
- Common pre-action information makes baseline behavioral comparisons easier to interpret.
- Execution order remains a modeling assumption and must be sensitivity-tested later.
- Recorder metrics are convenient summaries, not the final finance artifact schema.
- Finance private state is not yet restored by ABMForge Snapshot Schema v1; exact finance
  checkpoint/replay support remains future work.
- Market-making, cancellation decisions, finance-specific recording, and randomized
  activation remain outside this milestone.

## Risks

- Lexicographic execution order may advantage some trader IDs under scarce liquidity.
- Generic recorder floats lose exact `Decimal` representation, although exact state remains
  available in the finance engine.
- Custom policies can repeatedly emit economically rejected orders; the rejection rate
  must be treated as a scientific diagnostic rather than silently ignored.
- External mutation of `Exchange` or `MarketClock` during a run can violate adapter
  assumptions; clock and sequence checks fail loudly where observable.

## Validation plan

- Architecture test: no package outside `adapters/` imports `abmforge`.
- Integration test: a real ABMForge `Scenario` drives two finance periods, one resting
  limit order, one market execution, clearing, clock alignment, and recorder output.
- Unit tests: component validation, seed derivation, clock drift, existing-exchange
  submission sequencing, expected rejection handling, and sequence consumption.
- Property tests: equal seeds reproduce component seeds and equal finance runs reproduce
  deterministic order identity.
- Existing cross-platform CI continues to test released ABMForge and the audited pinned
  ABMForge `main` line.
