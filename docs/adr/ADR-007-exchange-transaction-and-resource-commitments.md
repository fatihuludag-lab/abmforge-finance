# ADR-007: Exchange transaction and resource commitments

## Status

Accepted for Phase 5.

## Context

Phase 4 leaves matching and clearing as independently correct components. A caller can
submit an order to `MatchingEngine`, mutate resting liquidity, receive one or more
`Trade` values, and only then discover that `ClearingEngine` rejects settlement for
insufficient cash or inventory. That composition is not a valid end-to-end exchange
transaction because the order book may already have changed.

The first research market needs a single synchronous entry point that preserves
financial state consistency before baseline trader policies or ABMForge integration
are added. It also needs to prevent passive orders from overcommitting resources. A
participant with 1,000 units of cash must not be able to leave two independent buy
orders that each require the same 1,000 units if both could later execute. The same
constraint applies to sell inventory when short selling is disabled.

## Decision

1. `Exchange` owns one single-instrument `MatchingEngine` and one `ClearingEngine`.
   End-to-end research workflows submit and cancel orders through this orchestrator.
2. Each submission is evaluated on deep-copied staged matching and clearing state.
   Matching, all resulting settlements, and post-transaction resting-order resource
   checks must succeed before the staged components replace visible exchange state.
3. Expected validation, matching, clearing, buying-power, and inventory failures
   therefore leave visible order-book, account, portfolio, fee, and sequencing state
   unchanged.
4. Every submitted order must belong to a participant registered with the exchange,
   including IOC/market orders that ultimately execute nothing.
5. Resting buy commitments are valued conservatively at `limit_price *
   remaining_quantity`. The sum of those commitments for each participant may not
   exceed that participant's post-transaction cash balance.
6. When short selling is disabled, the sum of resting sell remaining quantities for
   each participant may not exceed that participant's post-transaction inventory in
   the traded instrument. This check is skipped only when
   `allow_short_selling=True`.
7. The commitment ledger is derived from the post-transaction resting book rather
   than stored as a second mutable reservation structure. The order book remains the
   source of truth for outstanding passive obligations.
8. Cancellation requires the registered participant identifier and may cancel only
   an order owned by that participant. Cancellation reduces obligations and therefore
   does not require a clearing transaction.
9. Matching continues to own execution price, price-time priority, and trade IDs.
   Clearing continues to own cash/inventory settlement and venue fee accounting.
   `Exchange` composes those mechanisms but does not duplicate them.
10. Phase 5 matching still emits zero fees. A future fee model that can charge future
    passive executions must extend the buying-power commitment formula before such
    fees are enabled in integrated experiments.
11. Phase 5 is synchronous and single-process. Atomicity is defined at the visible
    in-memory `Exchange` state boundary; concurrent submissions and external durable
    transaction protocols are out of scope.
12. `FundamentalValueProcess`, market clock/event envelopes, and agent policies are
    separate milestones. They are not added merely because the original roadmap
    grouped them near exchange orchestration.

## Alternatives considered

### Match first and rely on settlement-time rejection

Rejected. It can leave economically inconsistent book state after a failed
settlement and was the explicit integration gap identified in ADR-006.

### Add an independent mutable reservation ledger

Rejected for the first core. It would create a second source of truth that must remain
perfectly synchronized with partial fills and cancellation. With one instrument and a
small in-memory book, resource commitments can be derived exactly from resting orders.

### Add preview/commit protocols to every lower-level component now

Deferred. A transaction protocol could avoid copying state, but it would enlarge the
public/internal contracts of `LimitOrderBook`, `MatchingEngine`, and `ClearingEngine`
before profiling shows that copy-on-commit staging is a bottleneck. Phase 5 favors
correctness and a narrow orchestration boundary.

### Use rollback after mutating live components

Rejected. Rollback adds inverse-operation complexity and increases the risk of hidden
state, sequence, or fee inconsistencies after exceptions.

### Permit passive buy orders based only on current cash at submission time

Rejected. Without accounting for already-resting obligations, a participant can
promise the same cash to multiple orders and create future settlement failures.

## Consequences

- Matching and clearing become safe to use as one end-to-end synchronous market
  transaction through `Exchange`.
- Passive cash and inventory overcommitment are explicit, deterministic rejection
  conditions.
- Expected rejected submissions do not consume visible trade sequence state or alter
  resting liquidity.
- The book itself is the auditable source for outstanding resource commitments.
- Copy-on-commit staging costs memory and CPU proportional to current in-memory market
  state. This is accepted until profiling demonstrates a real performance problem.
- Direct use of lower-level components remains available for isolated mechanism tests,
  but integrated research experiments should use `Exchange`.

## Risks

- `deepcopy` is appropriate for the current pure-Python in-memory state but may become
  unsuitable if future components hold file handles, network clients, native resources,
  or very large state. Such extensions must introduce an explicit transactional
  snapshot/commit protocol before entering the exchange core.
- Resting buy commitments do not yet reserve unknown future positive fees because the
  matching engine does not generate fees. Enabling a fee model without updating the
  commitment rule would weaken pre-trade solvency guarantees.
- Cancellation does not yet carry its own explicit market-event timestamp/sequence.
  Determinism follows synchronous call order until the market clock/event layer is
  introduced.
- The baseline is single-instrument. Multi-asset collateral netting and portfolio-wide
  margin are intentionally outside this decision.

## Validation plan

- Unit tests for registered-participant enforcement, funded passive orders,
  buying-power and inventory overcommitment, ownership-aware cancellation, IOC/market
  behavior, short-selling opt-in, and committed cash/inventory settlement.
- Atomic-failure tests showing insufficient cash/inventory and multi-level settlement
  failures leave book, ledgers, trade sequence, and settled-trade history unchanged.
- Property tests for cash/inventory conservation, exact replay, and resource-commitment
  boundaries.
- Randomized state-machine stress checks across submissions, matching, settlement,
  cancellation, and rejected events.
- Existing architecture tests continue to prohibit ABMForge imports in the market
  engine.
- Ruff, strict Mypy, branch-aware coverage, build, clean-install, and the full CI
  matrix remain milestone gates.
