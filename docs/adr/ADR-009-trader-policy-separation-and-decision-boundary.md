# ADR-009: Trader–Policy Separation and Decision Boundary

## Context

The validated market core now owns instruments, order-book state, matching, clearing,
participant ledgers, atomic exchange transactions, deterministic market time, and
fundamental-value paths. The next research requirement is heterogeneous trader behavior
without coupling decision logic to exchange internals or to ABMForge.

A baseline agent layer must later support classical behavioral policies, frozen RL
policies, narrative-aware policies, and external user policies. If trader identity,
market state, and decision rules are combined in one mutable object, policy comparison
and reproducibility become difficult and the ABMForge adapter becomes the de facto
owner of scientific behavior.

## Decision

1. `Trader` stores only stable identity and a swappable `TradingPolicy`.
2. Cash, inventory, open orders, and settlement state remain authoritative in `Exchange`.
3. Policies receive an immutable `MarketObservation`; they do not receive `Exchange`,
   `LimitOrderBook`, `ClearingEngine`, or ABMForge objects.
4. Policies return an immutable `TradingDecision` that contains economic intent only.
5. Order IDs, timestamps, submission sequence numbers, and conversion to domain `Order`
   objects belong to a later orchestration boundary.
6. The first baseline policies are `FundamentalPolicy`, `TrendFollowingPolicy`, and
   `NoisePolicy`.
7. Baseline policies emit market IOC decisions. Passive-liquidity provision and quote
   lifecycle semantics remain a separate future market-making milestone.
8. `NoisePolicy` is stateless and uses a stable SHA-256 mapping of explicit seed,
   agent identity, instrument, and market step. It never uses Python or NumPy global RNG.
9. The policy and trader packages must not import ABMForge or finance market-engine
   implementation modules.

## Alternatives considered

### Put account and portfolio directly on `Trader`

Rejected because it would duplicate the authoritative clearing ledger and create stale
or contradictory economic state.

### Let policies construct `Order` objects directly

Rejected because order identifiers, sequencing, and market time are orchestration
responsibilities and must be consistent across policy families.

### Pass `Exchange` directly to policies

Rejected because it gives decision logic mutation-capable access to the mechanism under
study and makes isolated policy testing harder.

### Use a mutable RNG stream inside `NoisePolicy`

Rejected for the first baseline because activation order would become a hidden source of
randomness. The stateless keyed design gives exact per-agent/per-step replay.

## Consequences

- Policy families can be swapped on the same trader identity without copying market state.
- ABMForge integration can remain an adapter that schedules observations and decisions.
- Common-random-number experiments can key stochastic behavior by explicit seed and step.
- Baseline policies do not yet create passive liquidity; a dedicated market-maker policy
  is required before stylized-fact validation of endogenous liquidity.
- `MarketObservation` contains derived values such as `price_change`; the future
  orchestrator must document exactly how those values are constructed.

## Risks

- An observation builder could accidentally leak future information into a policy.
- Market-order-only baseline policies can exaggerate impact if used without controlled
  passive liquidity.
- A fixed SHA-256 keyed noise policy is a controlled randomization baseline, not an
  empirical model of trader behavior.

## Validation plan

- Test that equal observations and equal seeds yield equal decisions.
- Test directional fundamental and trend responses around explicit dead bands.
- Test that trader/policy evaluation does not mutate observation or market objects.
- Test policy swapping on the same trader interface.
- Enforce architecture tests preventing ABMForge and market-engine imports.
- Add property tests for deterministic noise replay and decision validity.
