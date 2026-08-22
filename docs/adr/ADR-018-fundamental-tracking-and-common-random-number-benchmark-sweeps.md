# ADR-018: Fundamental tracking and common-random-number benchmark sweeps

## Status

Accepted.

## Context

Phase 9C.1 established canonical scenarios, explicit replicate seeds, descriptive
multi-seed summaries, and a constant-fundamental control ecology. The next validation
step needs benchmark families that exercise price tracking, quote geometry, stochastic
activity, and population composition without conflating these checks with empirical
parameter fitting.

## Decision

A deterministic moving-fundamental benchmark uses `DeterministicFundamentalPath`.
The frozen path is included in canonical scenario parameters. Dynamic passive
liquidity providers re-quote around the contemporaneous fundamental each period.

The existing `mean_absolute_relative_dislocation` outcome is the primary midpoint
tracking-error measure; no duplicate metric is introduced. Tick-aligned paths with
symmetric passive quotes can mechanically produce zero midpoint tracking error.
Non-grid paths may exhibit tick-grid tracking error.

Quote-width treatments vary only `quote_offset_ticks` and reuse identical replicate
seeds. With a constant fundamental and intact two-sided book, larger offsets
mechanically imply wider quoted spreads.

Noise-activity treatments reuse the same model seeds and stable agent identities.
`NoisePolicy` derives activity from a fixed hash of seed, agent, instrument, and step;
raising `activity_bps` therefore creates nested active-event sets under common random
numbers. Monotonic activity/trade counts may be tested under sufficient liquidity,
but monotonic volatility is not a software invariant.

Noise-population treatments preserve stable prefix identities (`noise-0000`,
`noise-0001`, ...) while adding agents. Existing agents keep their component seed
names, preserving their stochastic decisions under the same model seed. Passive
liquidity must remain sufficient for the largest same-period demand.

All benchmark families continue to return replicate outcomes and descriptive
summaries only. Formal treatment contrasts, confidence intervals, empirical fitting,
and stylized-fact acceptance criteria remain later Phase 9C work.

## Consequences

The baseline ecology can now test deterministic price tracking, quote-width geometry,
stochastic participation intensity, and population-size effects using explicit,
reproducible treatment definitions. These families form the control layer for later
narrative and AI-agent composition experiments.
