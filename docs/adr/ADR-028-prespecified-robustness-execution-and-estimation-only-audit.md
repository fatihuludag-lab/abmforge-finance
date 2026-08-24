# ADR-028: Prespecified robustness execution and estimation-only audit

## Status

Accepted.

## Decision

Phase 10G consumes the eight robustness regimes already frozen by the flagship
protocol without modifying the protocol JSON or fingerprint.

A fixed execution namespace, `robustness-v1`, derives one fresh seed tuple from the
frozen protocol fingerprint. Its count equals the immutable confirmatory replicate
count (10). The same tuple is shared across every regime and homogeneity treatment to
preserve common-random-number comparisons, while overlap with precision-pilot and
confirmatory seeds is forbidden.

The official confirmatory artifact is verified byte-for-byte using SHA-256
`9e78c74483ca20c16fdf3dca8f518957959ec66e3d810518a78e1cb5402831ed`
before its primary effect estimates are used as a descriptive reference.

Robustness inference is estimation-only. No new p-value family, multiplicity
procedure, effect-size threshold, or post-confirmatory success rule is introduced.
Primary outcomes report paired effects, nominal 95% intervals, confirmatory effect
ratios, exact direction preservation, and non-decreasing dose-response in the
confirmatory direction. Secondary, mechanism, and diagnostic outcomes remain
estimation-only without confirmatory-direction audit fields.

The official 400 robustness simulations remain deferred until this implementation is
merged to a CI-green main commit.
