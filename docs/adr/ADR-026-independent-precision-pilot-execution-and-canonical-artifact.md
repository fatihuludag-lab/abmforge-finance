# ADR-026: Independent precision-pilot execution and canonical result artifact

## Status

Accepted.

## Context

ADR-025 freezes the flagship study design and defines an independent precision pilot
for choosing the confirmatory replicate count. The pilot must be auditable without
becoming a channel for inspecting confirmatory effect direction or significance.

The Phase 10C.2 inference engine necessarily computes paired effect estimates to obtain
confidence intervals, but those estimates are not needed for the replicate-count
decision.

## Decision

### Execution boundary

The official runner loads the frozen flagship protocol, verifies that its runtime
mapping exactly matches the bundled JSON snapshot, derives the complete pilot seed
tuple from the protocol fingerprint, and executes the full prespecified homogeneity
grid.

The official runner returns a precision artifact, not the underlying experiment
objects.

### Precision-only artifact

The canonical artifact contains:

- artifact schema version;
- protocol ID, version, and fingerprint;
- explicit source Git commit;
- pilot seed namespace, count, and ordered-seed fingerprint;
- candidate seed counts;
- per-candidate primary metrics;
- per-treatment CI half-widths;
- maximum CI half-width for each primary metric;
- target half-width and criterion status;
- selected seed count; and
- confirmatory eligibility.

The artifact deliberately excludes mean treatment effects, effect signs, p-values,
confidence-interval endpoints, and whether an interval excludes zero.

The decision basis is fixed to `ci-half-width-only`.

### Exact experiment provenance

Before artifact construction, every pilot experiment must match the protocol treatment
order, exact benchmark scenario, full pilot horizon, and complete ordered pilot seed
tuple. A scenario that differs in any non-homogeneity parameter is rejected.

### Seed-count decision

The selected count is the smallest prespecified candidate for which every primary
metric meets its maximum CI half-width target across every non-control contrast.

If no checkpoint satisfies all targets, `selected_seed_count` is null and
`confirmatory_eligible` is false.

### Canonical serialization

Artifacts are canonical JSON with sorted keys, compact separators, UTF-8 encoding, and
one trailing newline. Floating-point CI half-widths are serialized as deterministic
17-significant-digit strings.

No wall-clock timestamp is included. The caller supplies the source Git commit
explicitly.

The writer refuses to overwrite an existing artifact and returns the SHA-256 of the
exact canonical bytes.

## Consequences

The independent precision pilot can now be executed and archived without publishing or
persisting effect-direction information used only internally to form confidence
interval widths.

A successful precision decision makes the confirmatory study eligible to run; it does
not itself support a substantive market-effect claim.
