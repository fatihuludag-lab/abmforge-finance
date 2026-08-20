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

The package now includes immutable finance-domain primitives, a deterministic
single-instrument resting limit order book, a synchronous matching engine, and an
independent clearing/accounting layer. The market core provides price-time priority,
cancellation, partial fills, maker-price execution, multi-level matching, deterministic
trade sequencing, exact cash/inventory settlement, signed fee accounting, best quotes,
depth, spread, midpoint, and imbalance. Exchange orchestration, traders, recording,
and RL environments remain outside the current branch.

## Planned research scope

The first research core will support a single risky asset, a central exchange, a
price-time-priority limit order book, deterministic discrete-time execution,
baseline behavioral trading policies, fixed pretrained RL policies, multi-seed
experiments, financial metrics, and bounded-memory research artifacts.

The flagship research program asks whether high AI-agent penetration combined with
shared or highly similar narrative-interpretation architectures creates correlated
order flow that amplifies liquidity depletion, volatility, price dislocation, and
tail risk under specific market regimes. Reinforcement-learning traders remain a
planned extension after the market mechanism and baseline-agent layers are validated.

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
exact conversions to integer ticks and lots for the order-book hot path.

## Limit-order-book example

```python
from decimal import Decimal

from abmforge_finance import LimitOrderBook, Side

book = LimitOrderBook(instrument)
book.add(order)

assert book.best_bid == Decimal("99.50")
assert book.best_ask is None
assert book.orders_by_priority(Side.BUY) == (order,)

partially_filled = book.apply_fill("order-1", Decimal("4"))
assert partially_filled.remaining_quantity == Decimal("6")

snapshot = book.snapshot(levels=5)
```

`LimitOrderBook` stores only non-marketable GTC limit orders. Market orders,
crossing limit orders, execution prices, and trade creation belong to the separate
matching-engine layer.

## Matching-engine example

```python
from abmforge_finance import MatchingEngine, OrderType, Side, TimeInForce

engine = MatchingEngine(instrument)
engine.submit(order)  # passive bid rests

market_sell = Order(
    order_id="order-2",
    agent_id="agent-2",
    instrument_id=instrument.instrument_id,
    side=Side.SELL,
    order_type=OrderType.MARKET,
    quantity=Decimal("4"),
    remaining_quantity=Decimal("4"),
    price=None,
    submitted_at=1,
    sequence_number=2,
    time_in_force=TimeInForce.IMMEDIATE_OR_CANCEL,
)
result = engine.submit(market_sell)
assert result.trades[0].price == Decimal("99.50")  # resting maker price
```

The first matching core supports GTC and IOC only. Market orders are IOC, IOC
residuals are cancelled, and a positive GTC limit residual rests after compatible
liquidity is exhausted. FOK and fee generation remain intentionally deferred; signed
fees already present on a `Trade` are handled by the clearing layer.

## Clearing and accounting example

```python
from abmforge_finance import Account, ClearingEngine, Portfolio

clearing = ClearingEngine()
clearing.register(Account("agent-1", Decimal("1000")), Portfolio("agent-1"))
clearing.register(
    Account("agent-2", Decimal("100")),
    Portfolio("agent-2", ((instrument.instrument_id, Decimal("10")),)),
)

settlement = clearing.settle(result.trades[0])
assert settlement.inventory_delta == Decimal("0")
assert clearing.account("agent-1").cash == Decimal("602.00")
assert clearing.portfolio("agent-1").quantity(instrument.instrument_id) == Decimal("4")
```

Baseline clearing rejects negative participant cash and negative inventory. Short
selling is opt-in. Trade IDs are settlement idempotency keys, and failed settlement
does not mutate clearing state. Matching and clearing are still separate transactions;
the future exchange layer will add pre-trade admissibility checks before end-to-end
market experiments.

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
- [ADR-004: Price-time priority implementation](docs/adr/ADR-004-price-time-priority-implementation.md)
- [ADR-005: Deterministic matching responsibility](docs/adr/ADR-005-deterministic-matching-responsibility.md)
- [ADR-006: Clearing and accounting responsibility](docs/adr/ADR-006-clearing-and-accounting-responsibility.md)

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
