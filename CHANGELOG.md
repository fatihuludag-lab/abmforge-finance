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
