# ADR-023: Narrative synchronization and downstream market-stability outcomes

## Status

Accepted.

## Context

Phase 10B identifies population narrative homogeneity as an assigned treatment and
separately measures realized decision and accepted-order synchronization. The next
layer must evaluate whether that synchronized flow changes liquidity and market
stability without promoting an economic comparative static into a software invariant.

A second issue is measurement. When total directional order volume is fixed,
homogeneity can redistribute liquidity consumption from two sides toward one side
without changing total displayed depth. Total depth alone can therefore miss the
mechanism of directional liquidity stress.

## Decision

### Causal ordering

The Phase 10C interpretation is:

`assigned homogeneity -> measured synchronization -> downstream market outcomes`.

Homogeneity is assigned before simulation. Decision, accepted-order, and executed-flow
concentration are mediators. Liquidity, spread, volatility, drawdown, and fundamental
dislocation are downstream outcomes.

Only the treatment-assignment and accounting mechanics are hard software properties.
Claims such as "higher homogeneity increases volatility" remain experimental results.

### Directional liquidity metrics

Add three generic market metrics:

- `thin_side_depth = min(bid_depth, ask_depth)`;
- `depth_asymmetry = abs(bid_depth - ask_depth) / (bid_depth + ask_depth)`;
- `thin_side_depletion = 1 - thin_side_depth / reference_side_depth`.

Depth asymmetry is undefined when both sides have zero displayed depth. Reference
side depth is explicit and strictly positive.

Existing total-depth depletion remains available and is intentionally reported beside
thin-side depletion. A design with fixed total market-order volume can therefore show
constant total depletion while thin-side depletion and depth asymmetry change with
directional synchronization.

### Deterministic direction schedule

`NarrativeDirectionSchedule` defines an exogenous focal-direction path held fixed
across homogeneity treatments. Every step is explicitly BULLISH or BEARISH; NEUTRAL
is excluded from this controlled stress path.

The schedule must exactly match the treatment active window, and its first direction
must match the treatment's configured focal direction. Focal agents follow the
schedule; opposing agents receive the opposite direction at every step.

This permits controlled alternating or shock-like paths without introducing LLM
sampling, narrative diffusion, or additional RNG.

### Active-window stability outcome

`NarrativeMarketStabilityOutcome` aggregates only periods inside the treatment active
window and reports:

- assigned homogeneity;
- realized decision concentration;
- realized accepted-order concentration;
- realized treatment executed-flow concentration;
- total depth and total-depth depletion;
- thin-side depth and thin-side depletion;
- depth asymmetry;
- relative spread and spread amplification;
- midpoint realized volatility;
- maximum midpoint drawdown;
- absolute relative midpoint/fundamental dislocation;
- treatment rejected-order count;
- treatment executed volume; and
- total market trade volume.

Treatment-specific mediator calculations filter out passive liquidity providers and
other non-treatment agents.

### Controlled sweep boundary

A stability sweep must keep agent identities, focal-direction convention, signal
strength, confidence, exposure weight, and active window fixed. Treatments may differ
only in homogeneity and treatment identifier. This prevents the evaluator from
silently describing a multi-factor change as a homogeneity sweep.

### Statistical boundary

Phase 10C does not hard-code crash thresholds, tail-event cutoffs, or monotonic
volatility assertions. Extreme-event thresholds remain explicit user/researcher
choices in the existing metric layer.

The outcome exposes a stable `metric_items()` projection so replicate-level paired
inference can be layered on without changing outcome semantics. Formal multi-seed
narrative-stability inference is a separate execution/inference step rather than being
embedded in the deterministic evaluator.

## Consequences

ABMForge-Finance can now distinguish aggregate liquidity consumption from
directional thin-side stress and can evaluate synchronized narrative flow against
continuous market-stability outcomes. The layer remains independent of ABMForge
orchestration and does not require an AI provider.
