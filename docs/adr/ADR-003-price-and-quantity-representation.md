# ADR-003: Price and quantity representation

- **Status:** Accepted
- **Date:** 2026-08-02
- **Decision owners:** ABMForge-Finance maintainers
- **Scope:** Prices, quantities, fees, notionals, tick sizes, and lot sizes

## Context

A market simulator needs exact tick and lot validation, deterministic matching,
reproducible accounting, understandable configuration, and acceptable performance.
The main representation choices are binary floating point, decimal values, and
integer tick/lot units.

Binary floating point is fast but values such as `0.1` are not represented exactly.
Direct equality, modulo, and repeated accounting operations can therefore introduce
unwanted rounding behavior.

Integer ticks and lots are exact and efficient for order-book indexing, but a pure
integer public API makes research configurations and artifacts harder to read and
requires every value to carry instrument-specific scale information.

`Decimal` is exact for decimal market grids and researcher-friendly, but it is slower
and less suitable than integers as a hot-path order-book key.

## Decision

Use a hybrid representation:

1. Public domain values use `Decimal` for prices, quantities, fees, tick sizes, and
   lot sizes.
2. Public domain boundaries reject Python `float` for monetary and quantity values.
3. `Instrument` validates exact grid alignment and converts values to and from
   positive integer tick and lot counts.
4. The future limit order book will index price levels by integer ticks and may store
   executable quantities in integer lots internally.
5. Serialized artifacts will retain human-readable decimal values and may also record
   integer tick/lot columns when useful for validation and analysis.
6. Discrete simulation time may use `int` or finite non-negative `float`; it is not a
   monetary value.

## Alternatives considered

### Use float everywhere

Rejected because binary rounding can alter tick validation, equality, aggregation,
and reproducibility in ways unrelated to the modeled mechanism.

### Use Decimal everywhere, including order-book keys

Rejected as the long-term hot-path design because comparisons and mapping operations
can be substantially slower than integer ticks in large simulations.

### Expose only integer ticks and lots

Rejected because configurations, debugging, recorded outputs, and external policy
interfaces would be less accessible to researchers.

### Store scaled integers with one global scale

Rejected because instruments can have different tick and lot sizes, and one global
scale either wastes range or fails to represent all grids cleanly.

## Consequences

### Positive

- Tick and lot alignment is exact.
- Public configuration and output values remain readable.
- Future order-book price keys can be deterministic integers.
- Monetary calculations avoid binary floating-point artifacts.
- Instrument-specific scales are explicit and validated.

### Negative

- Conversion is required at market-engine boundaries.
- Calling code must construct values from decimal strings rather than floats.
- Decimal arithmetic is slower outside optimized integer hot paths.
- Schema documentation must distinguish decimal values from tick/lot indices.

## Risks

- A future component could accidentally accept or create floats.
- Decimal context changes could matter for non-grid arithmetic such as advanced fee
  formulas if precision is not controlled.
- Integer conversion could overflow in external storage types for extreme values.
- Decimal and integer columns could diverge if not derived from one validated source.

## Validation plan

- Unit-test exact price/tick and quantity/lot round trips.
- Reject non-finite, non-positive, and off-grid values.
- Property-test conversion invariants when the order book is introduced.
- Benchmark integer-key and Decimal-key order books before performance claims.
- Record decimal and tick/lot consistency checks in finance artifact validation.
