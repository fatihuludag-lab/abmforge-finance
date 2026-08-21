# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Strengthened the market import-boundary architecture test with AST inspection.
- Broadened order-book property validation across both sides, terminal cleanup, and depth aggregation.
- Refreshed the audited ABMForge `main` compatibility target to the 2026-08-20 audit baseline.
- Aligned the README flagship research question with the Agentic Narrative Finance program.
- Corrected the `LimitOrderBook` class example docstring.

### Added
- Finance research schema v1 with participant, decision, order, trade, market-state, account, and position tables.
- Framework-independent `FinanceResearchRecorder` preserving exact `Decimal` economic values.
- Optional ABMForge adapter hook for deterministic per-period finance research capture.
- ADR-011 documenting the finance recording and dataset boundary.

- Narrow `abmforge_finance.adapters` boundary with `FinanceABMModel` orchestration.
- Immutable `FinanceComponents`, `FinanceOrderOutcome`, and `FinanceStepResult` audit values.
- Deterministic decision-to-order identity, finance clock synchronization, and expected-rejection capture.
- Call-order-independent named finance component seeds derived from the ABMForge scenario seed.
- ABMForge Recorder model metrics plus real `Scenario` integration tests.
- Public exchange submission-sequence/time introspection for generic orchestration.
- ADR-010 documenting the ABMForge integration and finance orchestration boundary.
- Immutable `MarketObservation` and `TradingDecision` policy-boundary values.
- Framework-independent `Trader` identity composed with swappable `TradingPolicy` logic.
- Directional `FundamentalPolicy` and `TrendFollowingPolicy` baselines.
- Stateless explicitly seeded `NoisePolicy` with keyed SHA-256 replay semantics.
- Policy/trader architecture tests and deterministic decision property tests.
- ADR-009 documenting trader-policy separation and the decision/orchestration boundary.
- Framework-independent `MarketClock` with explicit monotone integer periods.
- `FundamentalValueProcess` protocol with constant, frozen-path, and explicitly seeded synthetic implementations.
- Package-owned SplitMix64 seeded fundamental random walk with exact Decimal shock arithmetic.
- Market-time and fundamental replay/property tests plus a frozen known-seed path.
- ADR-008 documenting simulation-time, frozen-input, RNG, and interpretation boundaries.
- Atomic single-instrument `Exchange` orchestration using staged copy-on-commit transactions.
- Post-transaction resting buy/sell resource-commitment validation.
- Ownership-aware exchange cancellation without exposing mutable book internals.
- Exchange atomicity, conservation, overcommitment, and exact-replay tests.
- ADR-007 documenting transaction staging and resource-commitment policy.
- Immutable `Account` and deterministic sparse `Portfolio` domain values.
- Atomic `ClearingEngine` for exact cash and inventory settlement.
- Signed fee/rebate accounting with an explicit venue fee balance.
- Duplicate-settlement, insufficient-cash, insufficient-inventory, and registration guards.
- Clearing conservation and deterministic-replay property tests.
- ADR-006 documenting clearing, short-selling, fee, idempotency, and integration boundaries.
- Deterministic single-instrument `MatchingEngine` with maker-price execution.
- Multi-level market and crossing-limit execution with explicit maker/taker attribution.
- Immutable `MatchResult` values exposing executed, unfilled, cancelled, and resting quantities.
- Engine-level submission-history and monotone event-order validation.
- Matching conservation and exact-replay property tests.
- ADR-005 documenting matching responsibility, execution price, IOC/GTC residuals, and trade sequencing.
- Deterministic single-instrument `LimitOrderBook` resting-state component.
- Explicit price-time priority independent of order submission call order.
- Cancellation and partial/full fill state transitions.
- Best bid/ask, spread, mid-price, aggregated depth, and depth imbalance queries.
- Immutable `DepthLevel` and `OrderBookSnapshot` values.
- Market-engine exception hierarchy and invariant diagnostics.
- Property tests for insertion-order independence and non-negative remaining quantity.
- ADR-004 documenting the price-time-priority implementation.
- Immutable `Instrument`, `Order`, and `Trade` domain values.
- `Side`, `OrderType`, and `TimeInForce` enumerations.
- Exact Decimal-to-integer tick and lot conversion.
- Typed finance-domain validation exception hierarchy.
- Domain import-boundary architecture test.
- ADR-002 and ADR-003.
- Initial `src`-layout package scaffold.
- Python 3.10–3.13 metadata.
- ABMForge 0.3.x dependency contract.
- Ruff, Mypy, Pytest, coverage, build, and Twine configuration.
- Released and audited-main ABMForge compatibility checks.
- Linux, Windows, and macOS CI.
- Citation metadata and ADR-001.
