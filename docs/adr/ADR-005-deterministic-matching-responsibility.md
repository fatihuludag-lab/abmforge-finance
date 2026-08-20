# ADR-005: Deterministic Matching Responsibility

- Status: Accepted for Phase 3 implementation
- Date: 2026-08-20

## Context

ADR-004 deliberately limits `LimitOrderBook` to resting liquidity. The next research-core capability must turn incoming marketable orders into deterministic `Trade` records without moving matching, price selection, or trade sequencing into the book container.

The current domain contract supports market and limit orders, `GTC` and `IOC` time in force, explicit submission timestamps and sequence numbers, immutable remaining quantity, maker/taker attribution in `Trade`, and exact `Decimal` price/quantity grids. It does not yet define FOK, fees, clearing, account mutation, exchange policy, or a market clock.

For later market-impact, liquidity, volatility, and narrative-synchronization experiments, matching assumptions must be explicit because execution-price and residual-order rules directly affect simulated price formation.

## Decision

Phase 3 uses a synchronous, single-instrument `MatchingEngine` with the following rules:

1. The engine owns a fresh `LimitOrderBook`; normal submissions enter through the engine rather than directly through `LimitOrderBook.add`.
2. Accepted submissions must have non-decreasing `submitted_at` values and strictly increasing `sequence_number` values. This makes call order auditable rather than a hidden event-order rule.
3. A resting order is always the **maker** and the newly submitted order is always the **taker**.
4. The execution price is the resting maker order's limit price. Midpoint pricing and taker-price execution are not used.
5. Matching walks the opposite book in existing price-time priority and may execute across multiple price levels.
6. Each execution quantity is `min(incoming remaining, maker remaining)` and is exact and lot aligned.
7. A market order is IOC by the existing domain contract. Any unfilled market residual is cancelled and never rests.
8. An IOC limit order executes only at prices satisfying its limit; any residual is cancelled and never rests.
9. A GTC limit order executes against all price-compatible makers, then rests any positive residual at its original limit price and original submission priority fields.
10. FOK is **deferred** because it is not part of the current `TimeInForce` enum. Phase 3 does not expand that domain surface merely to anticipate a later feature.
11. Trade sequence numbers start at zero and increase contiguously within one engine lifetime. Trade IDs are derived deterministically as `trade-{sequence:012d}`.
12. `Trade.executed_at` equals the incoming order's `submitted_at` because Phase 3 matching is synchronous and no independent market clock exists yet.
13. Fees remain zero. Fee calculation belongs to the later fee/clearing layer.
14. Self-trades remain representable, consistent with the existing `Trade` contract. A later exchange policy may reject them.
15. Incoming orders must be fresh: `remaining_quantity == quantity`. A partially filled value cannot be resubmitted as a new event because that would hide prior execution provenance.
16. Expected validation failures are detected before book mutation. The first core does not promise transactional rollback for an unexpected internal exception after mutation begins; such a failure is a fail-stop condition to be treated as a software defect.

## Alternatives considered

### Match inside `LimitOrderBook.add`

Rejected. ADR-004 established the book as resting state. Keeping aggressor behavior separate allows independent mechanism tests and later exchange orchestration.

### Execute at the incoming/taker price

Rejected. It makes the aggressor choose a price more favorable to the resting order than necessary and departs from the intended resting-liquidity price rule.

### Midpoint execution

Rejected for the first central-limit-order-book core. Midpoint execution represents a different market mechanism and would materially change price-impact experiments.

### Use Python call order without explicit event constraints

Rejected. Sequential matching is path dependent, so the accepted call sequence must correspond to explicit timestamp and sequence metadata.

### Add FOK now

Deferred. The current domain enum contains only GTC and IOC. FOK requires a separate all-or-none liquidity preflight contract and should be introduced only when a study requires it.

### Add fees during matching

Rejected. Matching determines counterparties, price, and quantity. Fee calculation and balance mutation belong to later layers.

## Consequences

### Positive

- Execution price and maker/taker attribution are explicit and reproducible.
- Multi-level price impact follows observable resting depth and price-time priority.
- IOC cancellation and GTC residual resting are distinguishable in machine-readable `MatchResult` values.
- Trade IDs and sequence numbers are deterministic without UUIDs or wall-clock state.
- Matching remains independent from ABMForge, accounts, clearing, RL, and LLM components.
- The same order stream can be replayed to test exact deterministic equality.

### Negative

- The engine currently owns a single instrument and one in-memory book.
- Submission events must be supplied in explicit monotone event order.
- FOK and other venue-specific time-in-force rules are unavailable.
- Fees and settlement are deliberately absent.
- The first implementation preplans expected mutations but does not implement transactional rollback for unexpected internal failures.

## Risks

- Direct external mutation of `engine.book` can bypass engine-level submission-history checks; application code should treat the engine as the normal submission boundary.
- An incorrect maker-price rule would bias simulated market impact and price discovery, so exact-price tests are required.
- Large market orders can create many trades; performance should be profiled only after correctness is established.
- Future persistence/restart support must record the next trade sequence and accepted submission history to avoid identifier reuse.

## Validation plan

- Unit tests for market orders, crossing limits, non-crossing limits, IOC and GTC residuals, buy/sell symmetry, partial fills, multi-level execution, maker/taker attribution, and exact maker-price execution.
- Tests that duplicate identifiers and sequence numbers are rejected even when the earlier order never rested.
- Tests that out-of-order event metadata is rejected before mutation.
- Property tests for quantity conservation across incoming quantity, executions, residual quantity, and remaining book depth.
- Property tests showing identical explicit order streams produce identical `MatchResult` sequences and final book snapshots.
- Existing order-book invariant checks after matching scenarios.
- Ruff, strict Mypy, Pytest with branch coverage, package build checks, and the existing Python/OS CI matrix.
