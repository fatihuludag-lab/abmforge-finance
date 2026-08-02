# ADR-002: Domain engine independent from ABMForge

- **Status:** Accepted
- **Date:** 2026-08-02
- **Decision owners:** ABMForge-Finance maintainers
- **Related ADR:** ADR-001

## Context

Financial orders, trades, instruments, matching rules, clearing rules, and accounting
invariants are domain mechanisms rather than framework lifecycle concerns. Coupling
these values directly to ABMForge `Model` or `Agent` classes would make basic market
correctness dependent on scheduler state, recorder state, or plugin availability.

The first research core must also be testable before the ABMForge adapter, Gymnasium
environment, or reinforcement-learning integration exists.

## Decision

Keep immutable domain primitives under `abmforge_finance.domain` with no imports from
`abmforge`.

The dependency direction is:

```text
abmforge_finance.domain
        ↓
abmforge_finance.market
        ↓
abmforge_finance.adapters.abmforge
```

Domain values may depend on package-level validation exceptions but not on framework
models, agents, recorders, scenarios, experiments, or plugin contexts.

A repository architecture test parses every module under `abmforge_finance.domain`
and fails if it imports `abmforge`.

## Alternatives considered

### Derive orders or traders from ABMForge Agent

Rejected. Orders are immutable instructions and should not acquire framework identity,
scheduling, or lifecycle behavior.

### Implement the order book inside an ABMForge Model

Rejected. The order book must be independently unit-tested and reusable by the
ABMForge, Gymnasium, and PettingZoo adapters.

### Introduce a generic framework abstraction immediately

Rejected. A speculative cross-framework abstraction would add complexity before the
pure domain and market contracts are validated.

## Consequences

### Positive

- Domain tests run without ABMForge runtime state.
- Matching and clearing mechanisms can be validated in isolation.
- Framework API changes are confined to adapters.
- The same engine can serve research scripts and future RL environments.

### Negative

- Adapter code must translate framework time, RNG, and recording concepts explicitly.
- Some orchestration objects will exist outside ABMForge's native model lifecycle.
- Integration tests remain necessary even when domain tests pass.

## Risks

- Domain modules could accidentally import framework types as development proceeds.
- Adapter-specific assumptions could leak into identifiers or timestamps.
- Excessive framework neutrality could create unnecessary abstractions.

## Validation plan

- Keep the AST-based import-boundary test in CI.
- Run domain unit tests without constructing ABMForge models or agents.
- Review every new domain or market dependency during pull requests.
- Add explicit adapter integration tests when `feat/abmforge-adapter` begins.
