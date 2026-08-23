# ADR-027: Prespecified confirmatory inference and Holm reporting

## Status

Accepted.

## Context

The Phase 10D protocol prespecifies two primary outcomes, four non-control
homogeneity contrasts per primary outcome, Holm multiplicity control, and a familywise
alpha of 0.05. Phase 10E then selected the confirmatory replicate count exclusively by
precision: the immutable pilot artifact selected 10 seeds.

The confirmatory layer must not reuse pilot seeds, silently alter the treatment grid,
or mix primary significance decisions with secondary, mechanism, or diagnostic
outcomes.

## Decision

### Immutable precision bridge

Confirmatory execution requires the archived Phase 10E precision artifact. The official
artifact SHA-256 is frozen as:

`b43e9a1bfc6a40eadd0c38958068212a12d6feabfc8303c40917284a38d0be84`

The loader verifies the exact bytes, protocol identity and fingerprint, pilot seed
provenance, candidate checkpoint order, the CI-half-width-only decision basis, and the
smallest-qualifying-candidate rule before accepting `selected_seed_count`.

### Fresh confirmatory seeds

Confirmatory seeds are derived from the protocol's distinct `confirmatory` namespace.
Every confirmatory experiment must use the exact ordered seed tuple and the exact
prespecified benchmark scenario for its homogeneity. Pilot/confirmatory overlap is
forbidden and recorded as zero in the result artifact.

### Primary hypothesis family

The formal primary family contains two primary outcome metrics and four
treatment-versus-control homogeneity contrasts per metric, hence exactly eight
hypotheses.

Each primary contrast uses the existing seed-paired treatment-minus-control estimator.
The nominal per-contrast interval level is `1 - familywise_alpha = 0.95`. These are
estimation intervals, explicitly labelled `nominal-per-contrast-not-familywise`.

A two-sided Student-t p-value is computed from the paired contrast. Zero-standard-error
contrasts use the deterministic limiting convention: p=1 when the mean difference is
zero and p=0 when the mean difference is non-zero.

### Holm multiplicity control

Raw primary p-values are adjusted jointly across all eight primary hypotheses using the
Holm step-down procedure. Adjusted p-values are computed monotonically in sorted
p-value order and mapped back to protocol hypothesis order. Rejection uses familywise
alpha 0.05.

### Role separation

Primary outcomes include raw p-values, Holm-adjusted p-values, and Holm rejection
decisions.

Secondary, mechanism, and diagnostic outcomes include paired effect estimates,
standard errors, and nominal 95% intervals, but no significance fields.

### Canonical confirmatory artifact

The artifact records protocol and software provenance, the accepted precision artifact,
confirmatory seed provenance, multiplicity metadata, and all prespecified outcome
roles. It uses sorted-key compact UTF-8 JSON with one trailing newline and no
wall-clock timestamp. Existing artifacts are never overwritten.

## Consequences

Formal significance claims are restricted to the eight prespecified primary contrasts
with Holm FWER control. Phase 10F implements the inference/reporting contract only.
The official 50-run confirmatory experiment remains a later immutable research
execution from a CI-green merged main commit.
