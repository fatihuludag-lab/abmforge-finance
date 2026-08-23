# ADR-021: Deterministic narrative signal and policy boundary

## Status

Accepted.

## Context

The baseline market ecology and calibration layer are now validated independently of
the flagship Agentic Narrative Finance treatments. The next layer must represent
narrative direction, intensity, credibility, agent exposure, and resulting trading
pressure without introducing LLM sampling, text parsing, external services, or mutable
global narrative state.

The existing trader-policy boundary already accepts immutable market observations and
returns immutable trading decisions. Narrative behavior should fit that boundary
rather than changing Exchange or ABMForge orchestration.

## Decision

### Narrative state

`NarrativeState` contains:

- a conceptual `narrative_id`;
- `NarrativeDirection` (`BEARISH`, `NEUTRAL`, `BULLISH`);
- exact Decimal `strength` in `[0, 1]`;
- exact Decimal `confidence` in `[0, 1]`; and
- a half-open discrete interval `[active_from, active_until)`.

The same `narrative_id` may appear in multiple non-overlapping intervals, allowing one
conceptual narrative stream to change direction, strength, or confidence over time.
Overlapping states for the same narrative identifier are rejected as ambiguous.

### Agent exposure

`NarrativeExposure` maps one agent to one conceptual narrative with an exact Decimal
`exposure_weight` in `[0, 1]`. Each `(agent_id, narrative_id)` pair is unique.

Phase 10A deliberately uses one agent-side multiplicative exposure parameter. A
separate susceptibility parameter is deferred because multiplying two unconstrained
agent-side factors would add an unnecessary non-identifiability to the first mechanism
test.

### Signal aggregation

For agent `i`, narrative `n`, and step `t`, the active contribution is

`z_i,n,t = d_n,t * s_n,t * c_n,t * e_i,n`

where direction `d` is exactly `-1`, `0`, or `+1`, strength is `s`, confidence is `c`,
and agent exposure is `e`.

The aggregate signal is the exact Decimal sum over all active exposed narratives:

`z_i,t = sum_n z_i,n,t`.

Simultaneously active narratives can reinforce or cancel one another. Numeric signal
aggregation is independent of configuration order. Unknown narrative references,
duplicate exposure pairs, and overlapping states for one narrative stream are rejected.

### Trading policy

`NarrativePolicy` is a normal framework-independent `TradingPolicy`. It holds an
immutable frozen narrative schedule and exposure tuple and uses the market observation
only for the discrete simulation step.

For non-negative threshold `tau`:

- `z_i,t > tau` emits a market IOC BUY;
- `z_i,t < -tau` emits a market IOC SELL;
- otherwise the policy emits HOLD.

Equality with either threshold therefore remains inside the dead band.

The policy uses a fixed configured quantity. It does not optimize execution and does
not use price, fundamental value, spread, depth, inventory, or cash to change its
directional narrative decision.

### Boundaries

Phase 10A does not add:

- LLM or external model calls;
- prompt templates or text-to-narrative extraction;
- population-homogeneity treatment construction;
- social-network diffusion;
- adaptive susceptibility;
- multi-asset narrative targeting;
- narrative-signal recording schema changes; or
- claims that the deterministic policy represents empirical investor behavior.

The existing recorder still captures resulting decisions, orders, trades, and market
states. Explicit narrative-signal provenance can be added with the population-treatment
experiment layer when its recording contract is known.

## Consequences

Narrative pressure becomes an independently testable mechanism that composes with the
existing Trader, adapter, Exchange, and recording stack. Later AI/LLM adapters can
produce or transform narrative states without changing the financial execution
boundary, and population-homogeneity experiments can vary exposure/state composition
without conflating that treatment with LLM sampling behavior.
