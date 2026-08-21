# ADR-011: Finance research recording and dataset boundary

## Status

Accepted.

## Context

ABMForge already owns generic model, agent, event, lifecycle, provenance, and experiment
recording. ABMForge-Finance additionally needs finance-specific research tables whose
semantics depend on exact `Decimal` prices, quantities, cash, inventory, order identity,
maker/taker attribution, and market microstructure state.

Forcing those tables into ABMForge core would reverse the intended dependency direction and
make a generic framework responsible for domain-specific schema. Recording only executed
orders would also lose explicit HOLD decisions, creating selection bias in later studies of
policy homogeneity and order-flow synchronization.

## Decision

Add a framework-independent `abmforge_finance.recording` layer with schema version `1.0`.

The in-memory dataset has seven tables:

- `participants`
- `decisions`
- `orders`
- `trades`
- `market_states`
- `accounts`
- `positions`

`decisions` is intentionally separate from `orders`. Every policy output can therefore be
analyzed even when the agent holds or when a submitted order is rejected.

Public finance values remain `Decimal` in memory. No float conversion is introduced by the
research recorder.

`FinanceResearchRecorder` depends only on finance domain/market/agent abstractions. It must
not import ABMForge. The ABMForge adapter may optionally own a recorder and forward completed
period outcomes into it.

Initial cash and inventory are captured at setup with phase `initial`; end-of-period cash and
inventory use phase `post`. Market-state rows represent the completed post-action book for
each period.

Export formats are deliberately deferred. Schema and capture semantics are stabilized and
tested before JSONL/CSV/Parquet artifact contracts are added.

## Consequences

- ABMForge core remains generic.
- Finance research tables preserve exact economic values.
- HOLD, rejected-order, accepted-order, and execution populations remain distinguishable.
- Dataset row ordering is deterministic under deterministic simulation replay.
- The adapter gains only an optional integration hook; models without a research recorder
  retain existing behavior.
- Export/provenance artifact design remains a separate follow-up decision.
