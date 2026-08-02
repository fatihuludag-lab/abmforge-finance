# ADR-001: Separate finance extension repository

- **Status:** Accepted
- **Date:** 2026-08-02
- **Decision owners:** ABMForge-Finance maintainers
- **Related system:** ABMForge
- **Audited ABMForge commit:** `20c75fa7500ed511c138fab92b359f219aaa3841`

## Context

ABMForge-Finance will provide financial market domain objects, market-microstructure
mechanisms, behavioral and reinforcement-learning policies, financial data artifacts,
and scientific validation scenarios. These concerns are specific to finance and
should not become dependencies of the general-purpose ABMForge core.

ABMForge currently provides the public modeling, scenario, experiment, scheduling,
recording, and reproducibility surfaces needed for an adapter. Its plugin API is
alpha-stage and is not yet wired into automatic external package discovery or the
standard experiment lifecycle. Consequently, the finance package must not depend on
native plugin discovery for its first research core.

## Decision

Develop `abmforge-finance` as an independent distribution and repository with the
import package `abmforge_finance`.

The package will use the following dependency direction:

```text
pure finance domain model
        ↓
financial market engine
        ↓
ABMForge adapter
        ↓
optional Gymnasium and PettingZoo adapters
```

Finance-domain types such as orders, trades, instruments, portfolios, the limit
order book, matching, clearing, fees, market processes, trading policies, metrics,
and finance-specific records will remain in this repository.

Only the adapter layer may import ABMForge. The pure market engine must be usable and
testable without constructing an ABMForge model or agent.

The first release will be adapter-first and plugin-ready. Native ABMForge plugin
integration may be added after ABMForge exposes a stable, domain-independent plugin
discovery, lifecycle, artifact, and provenance contract.

## Alternatives considered

### Add finance classes to ABMForge core

Rejected because it would make a general ABM framework depend on domain-specific
financial concepts and optional data/RL dependencies.

### Build the whole package directly around ABMForge Model and Agent subclasses

Rejected because matching, clearing, accounting, and order-book correctness should
be independently testable and reusable outside a single framework lifecycle.

### Wait for a complete native plugin system

Rejected because the pure finance engine and explicit ABMForge adapter can be built
and validated now. Waiting would couple the project schedule to an experimental API.

### Build a standalone simulator with no ABMForge support

Rejected because ABMForge provides valuable scenario, multi-seed experiment,
reproducibility, archive, and researcher-workflow capabilities.

## Consequences

### Positive

- ABMForge core remains finance-independent.
- Domain mechanisms can be unit- and property-tested without framework state.
- Optional RL and data dependencies can remain extras.
- The engine can later support ABMForge, Gymnasium, PettingZoo, or other adapters.
- Framework compatibility failures are isolated in a small adapter surface.

### Negative

- The project must maintain an explicit compatibility layer for alpha ABMForge APIs.
- Finance artifacts may initially require a sidecar archive bridge rather than a
  first-class ABMForge dataset extension.
- Some lifecycle behavior may be duplicated temporarily in a finance runner.

## Risks

- ABMForge alpha API changes may break the adapter despite an unchanged pre-release
  version number.
- A custom runner may diverge from future ABMForge experiment semantics.
- Premature abstractions could appear if adapters are designed before the pure
  financial contracts are validated.
- Plugin discovery assumptions could create non-working integrations.

## Validation plan

- Test against released `abmforge>=0.3.0a1,<0.4` on Python 3.10–3.13.
- Test against the audited ABMForge `main` commit pinned in
  `constraints/abmforge-main.txt`.
- Keep ABMForge imports out of pure domain and market-engine modules.
- Add architectural import-boundary tests when the domain packages are introduced.
- Validate the market engine independently before adding ABMForge experiment and
  archive integration.
- Record exact ABMForge and ABMForge-Finance versions and commit hashes in research
  provenance.
