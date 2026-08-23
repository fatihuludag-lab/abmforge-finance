# ADR-022: Population narrative homogeneity treatment semantics

## Status

Accepted.

## Context

Phase 10A introduced deterministic narrative state, exposure, exact signal aggregation,
and a narrative-driven trading policy. The next flagship mechanism is population-level
narrative alignment.

A treatment called "homogeneity" must not be confused with the share of agents aligned
to one arbitrarily labelled focal narrative. If homogeneity were defined only as that
share, a population that was unanimously opposed to the focal narrative would receive
a value of zero despite being perfectly homogeneous.

The treatment also must not change directional participation at the same time as
homogeneity. Assigning non-focal agents to HOLD would confound narrative alignment with
the number of active traders.

## Decision

### Assigned homogeneity

For a binary directional narrative population of size `N`, define

`H = abs(N_focal - N_opposing) / N`

with the focal direction constrained to be the weak majority:

`N_focal >= N_opposing`.

Therefore

`N_focal = N * (1 + H) / 2`

and

`N_opposing = N - N_focal`.

`H = 0` is a balanced directional population and `H = 1` is complete focal-direction
homogeneity. Intermediate values are accepted only when `N * (1 + H) / 2` is exactly an
integer. The implementation never rounds an infeasible treatment to a nearby
population composition.

For eight agents, the exact grid is:

- `H=0.00`: 4 focal / 4 opposing;
- `H=0.25`: 5 / 3;
- `H=0.50`: 6 / 2;
- `H=0.75`: 7 / 1; and
- `H=1.00`: 8 / 0.

### Participation control

Every treatment agent is directionally active during the treatment window. Focal
agents receive one narrative stream and all remaining agents receive an equally strong,
equally confident opposing stream. Non-focal agents are not converted to HOLD.

Strength, confidence, exposure weight, decision quantity, active window, and decision
threshold are therefore separate controls and are not part of `H`.

### Deterministic assignment

Agent IDs are canonicalized lexicographically. Focal agents occupy the canonical prefix
of length `N_focal`. When the same population is evaluated at increasing `H`, the focal
set is nested. Phase 10B deliberately uses no assignment RNG.

A future randomized-assignment design must use an explicit seed and must be a separate
experimental contract.

### Assigned treatment versus realized mediator

`H` is assigned before simulation. It must not be reconstructed from market outcomes.

Realized decision and accepted-order concentration are measured separately within the
treatment population:

`C = abs(N_buy - N_sell) / (N_buy + N_sell)`.

HOLD decisions are excluded from the directional denominator. Accepted-order
concentration includes only accepted orders. The experiment-specific measurement
filters out passive liquidity providers and other non-treatment agents.

Under the controlled Phase 10B fixture, zero decision threshold, non-zero narrative
signal, equal quantities, and sufficient two-sided liquidity imply realized decision
and accepted-order concentration equal assigned `H`. That equality is a mechanism
validation, not a universal market law.

### Boundaries

Phase 10B does not yet claim that higher narrative homogeneity causes volatility,
liquidity depletion, dislocation, crashes, or tail risk. Those market-stability effects
belong to the subsequent synchronized-order-flow experiments.

Phase 10B also does not add LLM calls, social diffusion, endogenous narrative updates,
random exposure assignment, or empirical estimates of real investor homogeneity.

## Consequences

The flagship treatment is now mathematically identified and separated from both
participation intensity and its realized behavioral mediator. Later experiments can
compare market outcomes across exact homogeneity levels while preserving fixed
population size and deterministic agent identities.
