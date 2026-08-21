# ADR-012: Deterministic finance research artifacts and canonical serialization

## Status

Accepted.

## Context

ADR-011 defines the exact in-memory finance research dataset. Publication workflows also need
persistent artifacts that can be compared across reruns, machines, Python versions, and
experiment conditions without silently converting `Decimal` economic values to binary floats.

A research bundle must distinguish content determinism from file authenticity. Internal SHA-256
digests can detect accidental modification relative to a manifest, but they do not authenticate
a maliciously rewritten manifest and payload set.

## Decision

Finance artifact schema version `1.0` writes one directory containing `manifest.json` plus
canonical JSONL and CSV files for all seven finance tables by default.

Canonicalization rules are:

- UTF-8 encoding and LF line endings;
- fixed table membership and fixed column ordering;
- deterministic row ordering by table-specific semantic keys;
- `Decimal` values serialized with `str(Decimal)` so scale is preserved;
- JSONL uses compact JSON with no insignificant whitespace;
- CSV uses the standard library writer with LF records, lowercase booleans, and empty fields for
  `None`; JSONL is authoritative when null-versus-empty-string semantics matter;
- no wall-clock creation timestamp is written;
- provenance is an explicit caller-supplied string-to-string mapping;
- the producer package name/version is recorded without discovering Git state implicitly.

Every data file receives a SHA-256 digest in the manifest. Verification checks manifest schema,
directory membership, digests, row counts, columns, and canonical text encoding.

Artifact creation is no-overwrite and uses a temporary sibling directory followed by an atomic
directory rename. A failed serialization must not leave the requested target directory.

## Consequences

- Equal semantic finance datasets plus equal provenance produce byte-identical bundles even when
  input tuple order differs.
- Published experiments can explicitly record model seeds, scenario identifiers, ABMForge
  version/commit, and ABMForge-Finance Git commit in provenance.
- The core package gains no PyArrow/Pandas dependency.
- CSV remains a convenience interchange format; canonical JSONL preserves null semantics.
- SHA-256 verification is an integrity mechanism, not a cryptographic authenticity claim.
- Parquet and archive-level experiment packaging remain optional later extensions.
