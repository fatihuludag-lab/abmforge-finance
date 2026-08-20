# ADR-004: Price-Time Priority Implementation

- Status: Accepted
- Date: 2026-08-02
- Decision owners: ABMForge-Finance maintainers

## Context

The first research core requires a deterministic single-instrument central limit order
book. The resting book must expose best quotes, ordered liquidity, aggregated depth,
spread, mid-price, and depth imbalance while supporting cancellation and partial fill
state updates.

Priority must not depend on Python container iteration or the order in which callers
happen to invoke `add`. The domain model already carries `submitted_at` and a
non-negative `sequence_number`, and `Instrument` supplies exact conversions between
public `Decimal` prices and integer ticks.

Matching, execution-price selection, trade creation, clearing, and portfolio mutation
are separate responsibilities. Mixing them into the resting-book container would make
mechanism validation and later ABMForge integration harder.

## Decision

`LimitOrderBook` is implemented as a pure Python, ABMForge-independent resting-state
component with these rules:

1. Price levels are keyed internally by integer ticks.
2. Bid and ask price indexes are sorted integer lists.
3. Orders inside a price level are ordered by
   `(submitted_at, sequence_number)`.
4. Order identifiers and sequence numbers cannot be reused during one book lifetime.
5. Only active, non-marketable, good-til-cancelled limit orders may rest.
6. Market orders, immediate-or-cancel orders, and crossing limit orders are delegated
   to the future matching engine.
7. Partial fills replace the immutable active `Order` while preserving its queue
   position; complete fills remove it.
8. Cancellation and full fills remove empty levels from every index.
9. Public snapshots expose exact `Decimal` prices and quantities.
10. Empty two-sided statistics return `None` rather than fabricated zeros.

The initial implementation uses standard-library sorted lists and per-level order-ID
lists. This favors clarity, auditable ordering, and deterministic tests over premature
optimization.

## Alternatives considered

### Floating-point price keys

Rejected because binary floating-point values can produce unstable equality and tick
alignment behavior. ADR-003 already established `Decimal` at the public boundary and
integer ticks internally.

### Heap-only best-price indexes

Deferred. Heaps make best-price access inexpensive but require lazy deletion or
additional synchronization structures for cancellation and arbitrary level queries.
The added complexity is not justified for the first single-asset research core.

### Third-party sorted containers

Deferred to avoid a mandatory runtime dependency before profiling demonstrates a need.
A later implementation may adopt a sorted-map backend behind the same public contract.

### Add crossing orders and match inside the book

Rejected. The resting book should represent state, while the matching engine owns
aggressor behavior, execution price, multi-match loops, and trade sequencing.

### Use insertion call order as time priority

Rejected because it creates a hidden dependency on agent activation or caller list
order. Explicit timestamps and sequence numbers are auditable and reproducible.

## Consequences

### Positive

- Identical valid order sets produce identical priority regardless of `add` call order.
- Price and quantity aggregation remains exact.
- Matching and clearing can be tested independently.
- Depth snapshots are immutable and analysis-friendly.
- The component remains usable without ABMForge.

### Negative

- Insertion and cancellation within a large price level are linear in level size.
- Removing a price from the sorted price index is linear in the number of levels.
- Sequence numbers must be globally unique within a book lifetime.
- Crossing orders cannot be submitted directly to `LimitOrderBook.add`.

## Risks

- Very large simulations may require a different sorted-index backend.
- External callers may misunderstand the book as a complete exchange rather than a
  resting-liquidity store.
- Timestamp equality combined with duplicate sequence numbers would make priority
  ambiguous; duplicate sequences are therefore rejected.
- Corruption of multiple internal indexes could produce inconsistent snapshots;
  `validate_invariants()` is provided for tests and validation runs.

## Validation plan

- Unit tests for best quotes, price priority, time-sequence priority, cancellation,
  partial and complete fills, crossing rejection, depth, spread, midpoint, and
  imbalance.
- Property tests showing that permutations of identical order sets produce identical
  priority and snapshots.
- Property tests showing accepted fills never produce negative remaining quantity.
- Architecture tests preventing ABMForge imports in the market engine.
- Ruff, strict Mypy, Pytest, branch coverage, and the Python 3.10-3.13 CI matrix.
- The next `feat/matching-engine` branch will verify crossing limit orders, market
  orders, partial multi-level execution, and deterministic trade sequencing against
  this contract.
