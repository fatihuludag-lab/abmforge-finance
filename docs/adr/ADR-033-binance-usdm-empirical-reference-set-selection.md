# ADR-033: Binance USD-M Empirical Reference-Set Selection Protocol

## Status

Accepted.

## Context

ADR-032 freezes the Binance USD-M BTCUSDT empirical market-data
contract and defines the canonical one-second observation semantics.

The external-validity study requires an official empirical reference
set against which the ABMForge-Finance simulation market signature
will be compared.

A reference block contains:

- 4,097 raw one-second empirical intervals;
- one initial t-1 state;
- 4,096 canonical observations;
- SF-01 through SF-07 computed only after block acceptance.

Reference-set construction must not depend on stylized-fact values,
market-signature results, price direction, volatility, liquidity,
or any other outcome observed after capture.

## Decision

### 1. Primary market

The official primary empirical reference set uses the frozen
ADR-032 contract:

- Binance USD-M Futures;
- BTCUSDT;
- PERPETUAL;
- TRADING;
- UTC;
- one-second canonical intervals.

### 2. Reference-set size

The official primary reference set consists of the first 64
non-overlapping VALID empirical blocks.

Each VALID block contains exactly:

- 4,097 raw empirical intervals;
- 4,096 canonical observations.

Therefore the completed primary reference set contains:

- 262,144 canonical one-second observations.

This corresponds to approximately 72.82 hours of accepted
empirical observations.

### 3. Candidate ordering

Candidate attempts are ordered strictly by capture start time.

Candidate identifiers must preserve that ordering and must not
be changed after capture.

Rejected candidates remain part of the provenance registry and
must not be deleted, renumbered, or silently replaced.

### 4. Capture duration

Each normal candidate capture targets 4,200 wall-clock seconds.

The additional duration is operational margin only.

It does not increase the analytical block size and must never
be used to select a more favorable sub-window.

### 5. Candidate analytical window

After artifact verification and deterministic offline replay,
the analytical candidate window is the first 4,097 complete,
UTC-aligned reconstructed intervals admitted by ADR-032.

Any later reconstructed intervals in the same capture are outside
that candidate analytical block and are not searched for a more
favorable alternative window.

### 6. Insufficient observations

If fewer than 4,097 admissible complete intervals are available,
the candidate is REJECTED.

The capture must not be extended retrospectively in response to
observed SF values or other analytical results.

A new candidate may subsequently be attempted under the same
frozen protocol.

### 7. Validity

Candidate validity is determined only from source integrity,
temporal alignment, interval structure, and canonical preparation
requirements frozen by ADR-032 and the block evaluator.

SF-01 through SF-07 estimates are not candidate-validity criteria.

No candidate may be rejected because its empirical signature is
unusual, inconvenient, extreme, or poorly matched by the simulation.

### 8. Stopping rule

Collection stops when 64 VALID candidates have been accepted.

Rejected candidates do not count toward the 64-block target but
remain recorded.

The stopping rule must not depend on:

- empirical SF estimates;
- simulation results;
- statistical significance;
- agreement between empirical and simulated signatures;
- market regime labels;
- BTCUSDT price direction;
- realized volatility.

### 9. Non-overlap

Accepted analytical blocks must not overlap in UTC time.

If candidate captures overlap operationally, only a candidate whose
analytical window begins at or after the exclusive end of the previously
accepted analytical block may enter the official reference set.

### 10. Raw-data preservation

Every successfully finalized candidate artifact, VALID or REJECTED,
must preserve:

- immutable raw capture artifact;
- SHA-256 manifest;
- capture provenance;
- repository commit identity;
- candidate identifier;
- source-integrity outcome;
- block-evaluation outcome.

A capture attempt that fails before atomic raw-artifact finalization is
classified as CAPTURE_FAILED rather than block-level REJECTED.

CAPTURE_FAILED attempts:

- remain permanently recorded in the reference-set registry;
- retain candidate id, capture id, timestamps, commit identity,
  exception type, and failure detail;
- do not count toward the 64 VALID-block target;
- are never inspected for SF-01 through SF-07;
- cannot be silently deleted or renumbered.

The absence of a finalized raw artifact for CAPTURE_FAILED is recorded
explicitly rather than represented as a valid raw-data artifact.

### 11. Pilot exclusion

Previously collected smoke and pilot captures are excluded from the
official reference set.

They were used only for implementation and pipeline validation.

### 12. No post-hoc substitution

Once the 64th VALID block is accepted, the primary empirical
reference set is frozen.

Blocks may not later be replaced because alternative observations
produce stronger, weaker, or more favorable empirical findings.

Any alternative time period or market becomes a separately declared
robustness dataset.

## Consequences

This protocol separates technical data-quality acceptance from
scientific outcomes and makes the empirical reference-set selection
auditable and reproducible.

The reference set is sequential rather than outcome-selected.

Rejected technical candidates remain observable in the provenance
record, allowing publication reporting of collection failures and
rejection reasons.

The protocol intentionally sacrifices opportunistic market-regime
selection in favor of external-validity credibility.
