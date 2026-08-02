# ABMForge-Finance

[![CI](https://github.com/fatihuludag-lab/abmforge-finance/actions/workflows/ci.yml/badge.svg)](https://github.com/fatihuludag-lab/abmforge-finance/actions/workflows/ci.yml)

`abmforge-finance` is an independent, research-oriented Python extension for
building financial market simulations on top of
[ABMForge](https://github.com/fatihuludag-lab/abmforge).

The finance domain engine will remain independent from ABMForge. ABMForge-specific
behavior will be isolated in an adapter layer, allowing the order book, matching,
clearing, accounting, policy, recording, and validation components to be tested as
ordinary Python modules.

## Project status

The package now includes its first immutable finance-domain primitives: instruments,
orders, trades, order sides, order types, time-in-force values, and a typed validation
exception hierarchy. The exchange, order book, matching engine, clearing system,
traders, and RL environments remain outside the current branch.

## Planned research scope

The first research core will support a single risky asset, a central exchange, a
price-time-priority limit order book, deterministic discrete-time execution,
baseline behavioral trading policies, fixed pretrained RL policies, multi-seed
experiments, financial metrics, and bounded-memory research artifacts.

A primary research question is how increasing the share of reinforcement-learning
traders changes volatility, liquidity, price efficiency, tail risk, resilience,
wealth distribution, and systemic fragility.

## Domain example

```python
from decimal import Decimal

from abmforge_finance import Instrument, Order, OrderType, Side, TimeInForce

instrument = Instrument(
    instrument_id="ACME",
    tick_size=Decimal("0.01"),
    lot_size=Decimal("1"),
)

order = Order(
    order_id="order-1",
    agent_id="agent-1",
    instrument_id=instrument.instrument_id,
    side=Side.BUY,
    order_type=OrderType.LIMIT,
    quantity=Decimal("10"),
    remaining_quantity=Decimal("10"),
    price=instrument.ticks_to_price(9950),
    submitted_at=0,
    sequence_number=1,
    time_in_force=TimeInForce.GOOD_TIL_CANCELLED,
)
```

Prices and quantities use `Decimal` at the public boundary. `Instrument` provides
exact conversions to integer ticks and lots for the future order-book hot path.

## Installation

The current package is intended for development use.

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Quality checks

```bash
python -m ruff format --check src tests
python -m ruff check src tests
python -m mypy src tests
python -m pytest --cov=abmforge_finance --cov-report=term-missing
python -m build
python -m twine check dist/*
```

## Compatibility policy

The bootstrap package supports Python 3.10 through 3.13 and declares compatibility
with `abmforge>=0.3.0a1,<0.4`.

CI validates two ABMForge lines:

1. the released `abmforge` dependency selected by the package metadata;
2. the audited ABMForge `main` commit recorded in
   `constraints/abmforge-main.txt`.

Published research must record both package versions and exact source commit hashes.
ABMForge is alpha-stage software, so semantic-version compatibility alone is not a
complete reproducibility record.

## Architecture decisions

Architecture Decision Records are stored under [`docs/adr`](docs/adr).

- [ADR-001: Separate finance extension repository](docs/adr/ADR-001-separate-finance-extension-repository.md)
- [ADR-002: Domain engine independent from ABMForge](docs/adr/ADR-002-domain-engine-independent-from-abmforge.md)
- [ADR-003: Price and quantity representation](docs/adr/ADR-003-price-and-quantity-representation.md)

## Development workflow

Work is developed through small branches with tests and quality checks in the same
pull request. The initial sequence is:

```text
chore/bootstrap-package
feat/domain-primitives
feat/limit-order-book
feat/matching-engine
feat/clearing-portfolio
feat/finance-recorder
feat/abmforge-adapter
```

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
