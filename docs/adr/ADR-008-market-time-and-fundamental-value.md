# ADR-008: Market time and fundamental value

## Status

Accepted for Phase 5B implementation.

## Context

The validated market core can submit, match, settle, and atomically commit orders, but it
has no finance-owned notion of economic period and no reference fundamental-value path.
Future baseline traders, price-efficiency metrics, shock experiments, and recovery
analysis require both concepts without binding the finance engine to ABMForge lifecycle
classes or to wall-clock time.

A research comparison also needs frozen and seeded fundamental paths to replay exactly.
Using Python's or NumPy's process-global random state would make hidden call order and
external code capable of changing the path.

## Decision

1. `MarketClock` owns non-negative integer periods only. It advances solely through
   explicit positive integer increments and never reads system time.
2. The clock remains independent from `Exchange`. Callers decide when an exchange event
   belongs to a market period and may use `clock.current_step` as an order timestamp.
3. `FundamentalValueProcess` is a structural protocol exposing `value_at(step) -> Decimal`.
4. The initial implementations are:
   - `ConstantFundamentalValue` for fixed reference value experiments;
   - `DeterministicFundamentalPath` for finite frozen paths;
   - `SeededFundamentalRandomWalk` for controlled stochastic synthetic paths.
5. Fundamental values must be finite and strictly positive, but they are not forced onto
   an instrument tick grid because latent/reference value need not be directly tradable.
6. Frozen paths fail explicitly outside their declared horizon; there is no implicit
   forward fill or extrapolation.
7. The seeded baseline uses a package-owned SplitMix64 integer stream, an explicit 64-bit
   seed, integer shock units, and exact `Decimal` arithmetic. It does not use Python's or
   NumPy's global RNG state.
8. The seeded process caches the generated prefix so `value_at(t)` is independent of the
   order in which periods are queried.
9. The additive random walk and its positive floor are a reproducibility-oriented
   synthetic baseline, not an empirical model of fundamental-price dynamics.

## Alternatives considered

### Use wall-clock or `datetime`

Rejected for the research core because simulation period should not depend on execution
speed, timezone, or host time.

### Let ABMForge own finance time directly

Rejected at this layer because it would violate the finance/framework separation. A later
adapter may map ABMForge simulation time onto `MarketClock`.

### Use NumPy or Python global RNG

Rejected because unrelated code could perturb the path and because the RNG algorithm
would not be an explicit finance artifact contract.

### Start with GBM, OU, or calibrated empirical dynamics

Deferred. Those are substantive model assumptions. The initial process contract should
support controlled validation and frozen-input experiments before adding calibrated
families.

## Consequences

- Market-time and fundamental paths are replayable without ABMForge.
- Frozen paths can become versioned research inputs with straightforward checksums later.
- Fundamentalist policies and price-efficiency metrics receive a stable interface.
- Seeded baseline paths are comparable across supported Python/platform CI targets.
- Exchange event time and market period remain deliberately separate until an orchestration
  layer defines their coupling.
- More realistic stochastic processes can be added behind the same protocol without
  changing downstream policy interfaces.

## Risks

- Users may mistake the seeded additive walk for an empirically realistic process.
  Documentation must preserve the interpretation boundary.
- A positive floor creates a boundary effect and must be reported in experiments that use
  the seeded baseline.
- Changing the SplitMix64 mapping or shock semantics would change replayed paths and must
  therefore be treated as a versioned behavior change.

## Validation plan

- Unit-test clock monotonicity and invalid-time rejection.
- Unit-test constant and frozen-path boundary behavior.
- Freeze a known seeded path to detect accidental algorithm drift.
- Property-test exact same-seed replay and positive-floor preservation.
- Keep market architecture tests enforcing no ABMForge imports.
- Run the existing Python 3.10-3.13 and operating-system CI matrix before merge.
