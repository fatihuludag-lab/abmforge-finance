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
single-instrument resting limit order book, synchronous matching, independent
clearing/accounting, an atomic exchange orchestrator, deterministic market time,
fundamental-value processes, baseline trader policies, an ABMForge lifecycle adapter,
finance-specific research recording, and canonical research artifacts. The market core
provides price-time priority, cancellation, partial fills, maker-price execution,
multi-level matching, deterministic trade sequencing, exact cash/inventory settlement,
signed fee accounting, passive-order resource commitments, best quotes, depth, spread,
midpoint, and imbalance. Constant, frozen-path, and explicitly seeded synthetic
fundamental dynamics are available. The adapter coordinates common pre-action
observations, deterministic decision-to-order conversion, named finance component
seeds, Exchange submission, and model-level ABMForge Recorder metrics. Finance research
datasets preserve exact `Decimal` values for participants, decisions, orders, trades,
market states, accounts, and positions, and can be written as canonical JSONL/CSV
bundles with explicit provenance and SHA-256 integrity metadata. Primitive market
metrics now cover price series and returns, relative spread and displayed depth,
fundamental-price deviation, decision/accepted/aggressor order-flow imbalance, and
trade count, volume, and VWAP. Stability metrics add unannualized realized volatility,
rolling realized volatility, exact drawdown and maximum drawdown, explicit-reference
depth depletion and spread amplification, directional sign concentration, absolute
price/fundamental dislocation, and explicit-threshold tail-event indicators. Stress
experiment validation, calibrated market ecology, recovery-time analysis, and RL
environments remain planned.
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
does not mutate clearing state. Standalone matching and clearing remain useful for
mechanism tests; integrated market workflows should use `Exchange`.

## Exchange example

```python
from abmforge_finance import Exchange

exchange = Exchange(instrument)
exchange.register(Account("agent-1", Decimal("1000")), Portfolio("agent-1"))
exchange.register(
    Account("agent-2", Decimal("100")),
    Portfolio("agent-2", ((instrument.instrument_id, Decimal("10")),)),
)

exchange.submit(order)  # funded passive bid rests
committed = exchange.submit(market_sell)
assert committed.trades[0].price == Decimal("99.50")
assert exchange.account("agent-1").cash == Decimal("602.00")
assert exchange.portfolio("agent-1").quantity(instrument.instrument_id) == Decimal("4")
```

`Exchange` stages matching and clearing on independent in-memory copies and commits
only after all settlements and post-transaction passive-order obligations are funded.
Resting buys conservatively commit cash at their limit prices; resting sells commit
inventory when short selling is disabled. Expected rejected submissions leave visible
book and ledger state unchanged.

## Market clock and fundamental value example

```python
from abmforge_finance import (
    MarketClock,
    SeededFundamentalRandomWalk,
)

clock = MarketClock()
fundamental = SeededFundamentalRandomWalk(
    Decimal("100"),
    seed=20260821,
    step_size=Decimal("0.01"),
    max_abs_shock_units=5,
)

reference_value = fundamental.value_at(clock.current_step)
clock.advance()
next_reference_value = fundamental.value_at(clock.current_step)
```

`MarketClock` is integer-valued simulation time, not wall-clock time. Fundamental values
are positive exact `Decimal` references and are not required to lie on the executable
instrument tick grid. The seeded baseline owns a fixed SplitMix64 stream and does not use
Python or NumPy global RNG state. It is intended for controlled synthetic experiments;
more substantive stochastic or calibrated processes can implement the same
`FundamentalValueProcess` protocol later.

## Baseline trader-policy example

```python
from decimal import Decimal

from abmforge_finance import (
    FundamentalPolicy,
    MarketObservation,
    Trader,
)

trader = Trader(
    agent_id="agent-1",
    policy=FundamentalPolicy(Decimal("1"), minimum_gap=Decimal("0.50")),
)
observation = MarketObservation(
    step=clock.current_step,
    instrument_id=instrument.instrument_id,
    fundamental_value=Decimal("101"),
    mid_price=Decimal("100"),
    cash=exchange.account("agent-1").cash,
    inventory=exchange.portfolio("agent-1").quantity(instrument.instrument_id),
)
decision = trader.decide(observation)
```

`Trader` stores identity and policy only; authoritative cash, inventory, orders, and
settlement state remain in `Exchange`. Policies receive immutable observations and emit
immutable economic decisions. Order IDs, timestamps, sequence numbers, and conversion to
domain `Order` values are intentionally deferred to the orchestration layer.

## ABMForge adapter example

```python
from decimal import Decimal

from abmforge.experiment.scenario import Scenario

from abmforge_finance import (
    Account,
    ConstantFundamentalValue,
    Exchange,
    Instrument,
    MarketClock,
    NoisePolicy,
    Portfolio,
    Trader,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents


class BaselineMarket(FinanceABMModel):
    def build_finance_components(self) -> FinanceComponents:
        instrument = Instrument(
            instrument_id="ACME",
            tick_size=Decimal("0.01"),
            lot_size=Decimal("1"),
        )
        exchange = Exchange(instrument)
        exchange.register(
            Account("noise-1", Decimal("1000")),
            Portfolio("noise-1", ((instrument.instrument_id, Decimal("10")),)),
        )
        trader = Trader(
            agent_id="noise-1",
            policy=NoisePolicy(
                quantity=Decimal("1"),
                seed=self.finance_seed("noise-1"),
            ),
        )
        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=(trader,),
        )


result = Scenario(
    model=BaselineMarket,
    seed=42,
    steps=10,
    name="baseline-market",
).run()

assert result.model.finance.clock.current_step == 10
result.dataset.validate()
```

`FinanceABMModel` leaves ABMForge responsible for scenario construction, model
`steps/time`, and recorder collection. Finance traders observe one common pre-action
market snapshot per period; decisions are collected before deterministic execution.
The adapter owns order IDs, timestamps, and submission sequence numbers so policies
remain independent of market orchestration. Named `finance_seed(...)` streams are
derived deterministically from the explicit ABMForge model seed. Expected economic
order rejections are recorded as outcomes rather than treated as model crashes.


## Finance research recording and artifacts

`FinanceResearchRecorder` captures finance-specific research tables without importing
ABMForge. Attach it through `FinanceComponents` when a scenario should retain
participant metadata, every policy decision including `HOLD`, accepted or rejected
orders, committed trades, post-action market states, and exact cash/inventory history.

```python
from pathlib import Path

from abmforge_finance.recording import (
    FinanceResearchRecorder,
    verify_finance_artifacts,
    write_finance_artifacts,
)

class RecordedMarket(FinanceABMModel):
    def build_finance_components(self) -> FinanceComponents:
        recorder = FinanceResearchRecorder()
        # Build the same instrument, exchange, clock, fundamental process, and
        # trader tuple used by the market model.
        return FinanceComponents(
            exchange=exchange,
            clock=clock,
            fundamental=fundamental,
            traders=traders,
            research_recorder=recorder,
        )

result = Scenario(
    model=RecordedMarket,
    seed=42,
    steps=100,
    name="recorded-market",
).run()

recorder = result.model.finance.research_recorder
assert recorder is not None
dataset = recorder.dataset
dataset.validate()

artifact_dir = write_finance_artifacts(
    dataset,
    Path("artifacts/run-42"),
    provenance={
        "model_seed": "42",
        "scenario": "recorded-market",
        "abmforge_finance_git_commit": "<git-sha>",
        "abmforge_commit_or_version": "<abmforge-id>",
    },
)
verify_finance_artifacts(artifact_dir)
```

The default artifact bundle contains `manifest.json` plus canonical JSONL and CSV
representations of `participants`, `decisions`, `orders`, `trades`, `market_states`,
`accounts`, and `positions`. Serialization uses UTF-8 with LF line endings, fixed
column order, deterministic row order, and exact string representations for `Decimal`
values. The manifest stores explicit caller-supplied provenance, table row counts,
column contracts, producer metadata, and SHA-256 digests for data files. Artifact
creation is no-overwrite and commits a completed temporary directory atomically.
SHA-256 verification provides integrity checking relative to the manifest; it is not
presented as cryptographic authenticity.


## Primitive market metrics

The framework-independent `abmforge_finance.metrics` layer derives research metrics
directly from a validated `FinanceResearchDataset`. Price-based metrics require an
explicit basis and never silently fall back between midpoint and last-trade price.

```python
from abmforge_finance.metrics import (
    MarketPriceBasis,
    accepted_order_flow_imbalance,
    decision_flow_imbalance,
    fundamental_deviation,
    relative_spreads,
    simple_returns,
    trade_volume,
    trade_vwap,
)

returns = simple_returns(dataset, basis=MarketPriceBasis.MID)
spreads = relative_spreads(dataset)
dislocation = fundamental_deviation(dataset, basis=MarketPriceBasis.MID)

decision_flow = decision_flow_imbalance(dataset)
accepted_flow = accepted_order_flow_imbalance(dataset)

volume = trade_volume(dataset)
vwap = trade_vwap(dataset)
```

Simple returns use `P_t / P_(t-1) - 1`; log returns use the natural logarithm of the
same adjacent-period price ratio. The first observation, a missing endpoint, or a
non-consecutive period gap produces `None` rather than an imputed value. Relative
spread is `spread / mid_price`; total displayed depth is bid depth plus ask depth.
Signed fundamental deviation is `P_t - F_t`, with a relative form
`P_t / F_t - 1`.

Directional-flow metrics intentionally preserve separate populations: policy
decisions (where `HOLD` has no directional quantity), accepted submitted orders,
and quantity executed immediately by the incoming/aggressor order. Trade count,
trade volume, and VWAP are computed from committed trades. Exact algebraic metrics
remain `Decimal`; natural-log returns are finite statistical `float` values.


## Stability, synchronization, and tail-event metrics

The stability layer extends the primitive market metrics without changing their
price-basis or missing-data semantics.

```python
from decimal import Decimal

from abmforge_finance.metrics import (
    decision_sign_concentration,
    depth_depletion,
    downside_return_breaches,
    drawdowns,
    maximum_drawdown,
    realized_volatility,
    rolling_realized_volatility,
    spread_amplification,
)

rv = realized_volatility(dataset)
rolling_rv = rolling_realized_volatility(dataset, window=20)

dd = drawdowns(dataset)
mdd = maximum_drawdown(dataset)

depth_stress = depth_depletion(
    dataset,
    reference_depth=Decimal("100"),
)
spread_stress = spread_amplification(
    dataset,
    reference_spread=Decimal("2"),
)

synchronization = decision_sign_concentration(dataset)

large_down_moves = downside_return_breaches(
    dataset,
    threshold=Decimal("0.10"),
)
```

Realized volatility is unannualized and uses the square root of the sum of squared
adjacent-period log returns. Missing prices or period gaps remain explicit instead of
being silently bridged. Drawdown is `P_t / running_peak_t - 1`.

Liquidity stress requires caller-supplied reference depth and spread values. The
library does not infer the first row as a baseline. Decision and accepted-order sign
concentration are unweighted directional-concentration measures and are deliberately
separate from quantity-weighted order-flow imbalance.

Tail-event indicators also require explicit thresholds. ABMForge-Finance does not
hard-code a universal definition of a crash. Recovery-time analysis is deferred to
the stress-experiment layer because it requires an explicit shock window, baseline,
and recovery criterion.


## Static passive-liquidity baseline

`PassiveLiquidityPolicy` provides a deterministic one-shot, one-sided GTC quote around
the latent fundamental value. Two independently registered and independently funded
traders can be paired to create a controlled two-sided static-liquidity baseline.

```python
from decimal import Decimal

from abmforge_finance import PassiveLiquidityPolicy, Side, Trader

bid_provider = Trader(
    "lp-bid",
    PassiveLiquidityPolicy(
        side=Side.BUY,
        quantity=Decimal("10"),
        tick_size=instrument.tick_size,
        offset_ticks=1,
    ),
)

ask_provider = Trader(
    "lp-ask",
    PassiveLiquidityPolicy(
        side=Side.SELL,
        quantity=Decimal("10"),
        tick_size=instrument.tick_size,
        offset_ticks=1,
    ),
)
```

For a fundamental value of `100`, tick size `1`, and one-tick offset, the paired
baseline quotes `99` bid and `101` ask with the configured quantity on each side.
Non-grid fundamentals are rounded outward: BUY uses the floor-side grid and SELL uses
the ceiling-side grid, keeping paired quotes non-crossing for the same configuration.

The policy emits its quote only on `quote_step` and returns `HOLD` afterwards, so
resting depth is not duplicated every period. Quotes follow the normal
policy -> decision -> adapter -> Exchange -> research-recorder path.

This is a controlled liquidity fixture, not a realistic single-dealer balance sheet.
Dynamic quote replacement, ownership-aware cancellation orchestration, inventory skew,
adaptive spreads, and multi-action policy output are deferred to the next
market-ecology milestone.


## Dynamic passive liquidity and cancel/replace lifecycle

`DynamicPassiveLiquidityPolicy` extends the static liquidity fixture with deterministic
cancel-before-replace behavior while preserving the one-decision-per-trader-period
research contract.

```python
from decimal import Decimal

from abmforge_finance import DynamicPassiveLiquidityPolicy, Side, Trader

bid_provider = Trader(
    "lp-bid",
    DynamicPassiveLiquidityPolicy(
        side=Side.BUY,
        quantity=Decimal("10"),
        tick_size=instrument.tick_size,
        offset_ticks=1,
    ),
)
```

Each period the policy receives only its own active order identifiers. It requests
their cancellation and produces exactly one replacement GTC decision around the
current fundamental reference. The orchestration layer validates every cancellation
before changing exchange state, then executes **all cancellations before any new
submission**.

For a one-tick offset:

```text
fundamental 100 -> bid 99, ask 101
fundamental 102 -> cancel stale quotes -> bid 101, ask 103
fundamental 101 -> cancel stale quotes -> bid 100, ask 102
```

Finance research dataset schema `1.1` and artifact schema `1.1` add a separate
`cancellations` table. Cancellation artifacts are included in canonical CSV/JSONL
output, deterministic manifest membership, row counts, and SHA-256 integrity
verification.

The current plan contract permits zero or more cancellations plus exactly one trading
decision. Arbitrary multi-submit batches, inventory-aware market making, adaptive
spreads, latency, RL, and LLM-based liquidity provision remain later work.

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
- [ADR-007: Exchange transaction and resource commitments](docs/adr/ADR-007-exchange-transaction-and-resource-commitments.md)
- [ADR-008: Market time and fundamental value](docs/adr/ADR-008-market-time-and-fundamental-value.md)
- [ADR-009: Trader-policy separation and decision boundary](docs/adr/ADR-009-trader-policy-separation-and-decision-boundary.md)
- [ADR-010: ABMForge integration and finance orchestration boundary](docs/adr/ADR-010-abmforge-integration-and-finance-orchestration-boundary.md)
- [ADR-011: Finance research recording and dataset boundary](docs/adr/ADR-011-finance-research-recording-and-dataset-boundary.md)
- [ADR-012: Deterministic finance research artifacts and canonical serialization](docs/adr/ADR-012-deterministic-finance-research-artifacts-and-canonical-serialization.md)
- [ADR-013: Finance market metrics and statistical semantics](docs/adr/ADR-013-finance-market-metrics-and-statistical-semantics.md)
- [ADR-014: Stability, synchronization, and tail-event metric semantics](docs/adr/ADR-014-stability-synchronization-and-tail-event-metric-semantics.md)
- [ADR-015: Static passive-liquidity baseline and deferred quote replacement](docs/adr/ADR-015-static-passive-liquidity-baseline-and-deferred-quote-replacement.md)
- [ADR-016: Cancel/replace trading plans and dynamic passive liquidity](docs/adr/ADR-016-cancel-replace-trading-plans-and-dynamic-passive-liquidity.md)

## Development workflow

Work is developed through small branches with tests and quality checks in the same
pull request. The initial sequence is:

```text
chore/bootstrap-package
feat/domain-primitives
feat/limit-order-book
feat/matching-engine
feat/clearing-portfolio
feat/exchange
feat/fundamental-clock
feat/baseline-policies
feat/abmforge-adapter
feat/finance-recorder
feat/finance-artifacts
feat/market-metrics
feat/stability-metrics
feat/passive-liquidity
feat/dynamic-liquidity
```

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
