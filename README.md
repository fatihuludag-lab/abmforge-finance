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


## Baseline market ecology and calibration

The calibration layer provides a controlled synthetic market ecology for validating
mechanisms before narrative or AI-agent treatments are introduced. It is deliberately
separate from empirical parameter fitting.

A scenario is defined independently of its replicate seed:

```python
from decimal import Decimal

from abmforge_finance.calibration import (
    ConstantFundamentalBenchmarkConfig,
    run_constant_fundamental_benchmark,
)

config = ConstantFundamentalBenchmarkConfig(
    periods=20,
    fundamental_value=Decimal("100"),
    passive_quantity=Decimal("10"),
    quote_offset_ticks=1,
    noise_trader_count=1,
    noise_quantity=Decimal("1"),
    noise_activity_bps=10_000,
)

experiment = run_constant_fundamental_benchmark(
    config,
    seeds=(101, 202, 303),
)
```

Each replicate is identified by scenario, treatment, replicate index, and explicit
seed. Scenario parameters are canonicalized and hashed with SHA-256, while the seed
is excluded from the scenario fingerprint because it identifies a replicate rather
than a treatment definition.

The initial controlled ecology combines a constant latent fundamental, dynamic passive
bid/ask providers, and explicitly seeded noise traders. Replicate-level outputs include
order, cancellation, rejection and trade counts, exact trade volume, realized
volatility, maximum drawdown, relative spread, displayed depth, relative fundamental
dislocation, and decision-sign concentration.

Treatment summaries report defined-replicate count, arithmetic mean, sample standard
deviation, standard error, minimum, and maximum. These are descriptive replication
summaries only; the calibration layer does not produce p-values, confidence intervals,
multiple-testing corrections, or empirical-fit claims.

Passive-depth sweeps reuse the same ordered seed tuple across treatments, supporting a
common-random-number design when stochastic components and agent identities are held
fixed. At this stage the hard assertion is mechanistic: greater configured passive
quantity must generate greater displayed depth. Claims about volatility, tail risk, or
other economic outcomes are evaluated later across replicated treatments rather than
encoded as unit-test truths.


## Calibration benchmark families

Phase 9C.2 extends the baseline ecology with deterministic tracking and
common-random-number treatment sweeps.

### Fundamental tracking

`FundamentalTrackingBenchmarkConfig` freezes an explicit deterministic fundamental
path and evaluates whether the quoted midpoint follows that reference under the
existing dynamic passive-liquidity mechanism.

```python
from decimal import Decimal

from abmforge_finance.calibration import (
    FundamentalTrackingBenchmarkConfig,
    run_fundamental_tracking_benchmark,
)

tracking = run_fundamental_tracking_benchmark(
    FundamentalTrackingBenchmarkConfig(
        fundamental_path=(
            Decimal("100"),
            Decimal("102"),
            Decimal("104"),
            Decimal("101"),
        ),
        passive_quantity=Decimal("2"),
        noise_activity_bps=0,
    ),
    seeds=(101, 202, 303),
)
```

The existing `mean_absolute_relative_dislocation` outcome is used as the midpoint
tracking-error measure. No duplicate tracking metric is introduced. Tick-aligned
fundamental paths with symmetric passive quotes can mechanically have zero midpoint
tracking error; non-grid paths expose the error induced by tick geometry.

### Quote-width sweep

```python
from abmforge_finance.calibration import run_quote_width_sweep

widths = run_quote_width_sweep(
    config,
    quote_offset_ticks=(1, 2, 4),
    seeds=(101, 202, 303),
)
```

Under a constant fundamental and intact two-sided book, larger quote offsets
mechanically produce wider quoted spreads. This is a market-geometry validation, not
an empirical spread model.

### Noise-activity sweep

```python
from abmforge_finance.calibration import run_noise_activity_sweep

activity = run_noise_activity_sweep(
    config,
    activity_bps=(0, 2500, 5000, 7500, 10000),
    seeds=(101, 202, 303),
)
```

`NoisePolicy` uses a fixed seed/agent/instrument/step draw. Reusing the same replicate
seeds therefore creates nested active-event sets as `activity_bps` increases. This is
a common-random-number comparison: increasing the threshold activates additional
events without changing previously active draws.

### Noise-population sweep

```python
from abmforge_finance.calibration import run_noise_population_sweep

populations = run_noise_population_sweep(
    config,
    noise_trader_counts=(1, 2, 4),
    seeds=(101, 202, 303),
)
```

Population treatments preserve stable prefix identities (`noise-0000`,
`noise-0001`, ...) so existing agents retain their component seed names under the same
model seed.

These benchmarks deliberately separate **mechanical truths** from **economic
tendencies**. Quote width determining quoted spread and deterministic tracking under a
symmetric tick-aligned fixture may be asserted as software/mechanism properties.
Claims about volatility, drawdown, tail risk, or liquidity resilience remain
replicated experimental results rather than universal unit-test assertions.


## Paired treatment contrasts and confidence intervals

Common-random-number calibration treatments can be compared with explicit
seed-paired inference. For treatment `T`, control `C`, and common seed `s`, the
library defines:

```text
D_s = Y(T, s) - Y(C, s)
```

The sign convention is always **treatment minus control**.

```python
from abmforge_finance.calibration import paired_treatment_contrast

contrast = paired_treatment_contrast(
    control,
    treatment,
    metric_name="trade_count",
    confidence_level=0.95,
)
```

A valid paired contrast requires identical ordered seed tuples, at least two replicate
pairs, the same scenario identifier and horizon, identical canonical parameter keys,
distinct treatment identifiers, and at least one changed canonical parameter value.
Requested metrics must be defined and finite for every pair; missing values are not
silently dropped.

The reported uncertainty uses the sample standard deviation of paired differences:

```text
SE = s_D / sqrt(n)
```

and a two-sided Student-t interval:

```text
mean(D) +/- t_(1-alpha/2, n-1) * SE
```

The Student-t critical value is computed without adding SciPy as a runtime dependency.
ABMForge-Finance evaluates the Student-t CDF through the regularized incomplete-beta
representation and deterministically inverts it by bisection. Reference critical-value
tests cover small and moderate degrees of freedom.

Related contrasts can also be summarized with `summarize_contrast_region()`, which
reports positive, negative, zero, and mixed mean-effect directions and the number of
individual confidence intervals excluding zero. This is a descriptive robustness
diagnostic only: it is **not** a simultaneous confidence region and performs no
multiple-testing correction.

Formal multiplicity control, bootstrap intervals, regression/meta-models, empirical
parameter fitting, and stylized-fact acceptance criteria remain separate later
analysis steps.


## Robustness, sensitivity, and baseline ecology audit

Phase 9C.4 closes the baseline-calibration layer by auditing whether paired treatment
effects retain a stable direction across an explicit single-parameter region.

```python
from abmforge_finance.calibration import (
    audit_parameter_sweep,
    build_baseline_ecology_audit,
)

depth_audit = audit_parameter_sweep(
    depth_experiments,
    control_index=0,
    family_name="passive-depth",
    parameter_name="passive_quantity",
    metric_name="mean_total_depth",
)

baseline_audit = build_baseline_ecology_audit(
    (depth_audit, width_audit),
    required_families=("passive-depth", "quote-width"),
)
```

Treatment-family audits use the existing seed-paired treatment-minus-control contrast
contract. They are deliberately limited to one changed canonical parameter at a time;
multi-parameter changes are rejected rather than given a misleading sensitivity
interpretation.

Directional outcomes are classified as:

```text
ROBUST_POSITIVE
ROBUST_NEGATIVE
ROBUST_ZERO
MIXED
INSUFFICIENT
```

`ROBUST_*` means that the mean paired effect keeps the same direction across at least
the configured minimum number of treatment points. It does **not** mean statistical
significance, simultaneous confidence coverage, an economic law, or empirical
realism. Individual confidence-interval exclusion counts remain separate.

When normalization is mathematically valid, the audit also reports dimensionless
sensitivity:

```text
S = ((Y_T - Y_C) / Y_C) / ((X_T - X_C) / X_C)
```

Sensitivity is left undefined rather than forced when the parameter is non-numeric,
the control parameter is zero, the control metric mean is zero, or the canonical
parameter strings differ without a numerical parameter change.

`BaselineEcologyAudit` aggregates named treatment-family audits and records missing
families, insufficient regions, mixed-direction findings, whether families share one
replicate-seed tuple, individual interval-exclusion counts, and explicit warnings.

A complete baseline ecology audit means only that requested treatment families are
present and contain enough contrasts for their configured directional classification.
It is **not** a certificate of empirical realism, external validity, calibration
quality, or publication readiness.

With Phases 9C.1-9C.4, the calibration layer now provides reproducible scenario
contracts, benchmark treatment families, seed-paired uncertainty, directional
robustness, normalized sensitivity where defined, and machine-readable baseline
ecology audit results.


## Deterministic narrative signal layer

Phase 10A introduces a framework-independent narrative mechanism before any external
AI/LLM integration. Narrative state, agent exposure, aggregate signal, and the
resulting trading decision are deterministic and independently testable.

```python
from decimal import Decimal

from abmforge_finance import (
    NarrativeDirection,
    NarrativeExposure,
    NarrativePolicy,
    NarrativeState,
)

policy = NarrativePolicy(
    quantity=Decimal("1"),
    narratives=(
        NarrativeState(
            narrative_id="growth",
            direction=NarrativeDirection.BULLISH,
            strength=Decimal("0.8"),
            confidence=Decimal("0.9"),
            active_from=0,
            active_until=10,
        ),
    ),
    exposures=(
        NarrativeExposure(
            agent_id="trader-0001",
            narrative_id="growth",
            exposure_weight=Decimal("0.75"),
        ),
    ),
    decision_threshold=Decimal("0.25"),
)
```

For agent `i`, narrative `n`, and step `t`, the exact contribution is

```text
z_i,n,t = direction_n,t * strength_n,t * confidence_n,t * exposure_i,n
```

and the aggregate narrative pressure is the sum of all active exposed narrative
streams:

```text
z_i,t = sum_n z_i,n,t
```

The policy uses a symmetric deterministic dead band:

```text
z_i,t >  threshold  -> BUY
z_i,t < -threshold  -> SELL
otherwise           -> HOLD
```

`NarrativeState` uses half-open time intervals `[active_from, active_until)`. The same
conceptual `narrative_id` may change direction, strength, or confidence across
non-overlapping intervals. Overlapping states for the same narrative stream are
rejected as ambiguous.

`NarrativeExposure` deliberately contains one agent-side multiplicative exposure
weight in Phase 10A. A second susceptibility factor is deferred to avoid introducing
an unnecessary non-identifiability before the core narrative-to-decision mechanism is
validated.

Multiple simultaneously active narrative streams can reinforce or cancel one another,
and aggregation uses exact `Decimal` arithmetic. The resulting `NarrativePolicy`
composes with the existing `Trader -> TradingDecision -> Exchange -> Recorder` path;
Exchange and ABMForge adapter semantics are unchanged.

Phase 10A intentionally does **not** include LLM calls, prompt templates, social
diffusion, population-homogeneity treatments, adaptive susceptibility, or claims that
the deterministic policy is an empirical model of investor behavior. Those are
separate treatment layers built on top of this mechanism.


## Population narrative homogeneity treatment

Phase 10B promotes the deterministic narrative mechanism from a single-agent policy
to an explicit population treatment. Homogeneity is assigned before simulation and is
kept separate from its realized behavioral mediator.

For a binary directional narrative population of size `N`:

```text
H = abs(N_focal - N_opposing) / N
N_focal >= N_opposing
```

so that:

```text
N_focal    = N * (1 + H) / 2
N_opposing = N - N_focal
```

For eight treatment agents the exact grid is:

```text
H = 0.00  -> 4 focal / 4 opposing
H = 0.25  -> 5 / 3
H = 0.50  -> 6 / 2
H = 0.75  -> 7 / 1
H = 1.00  -> 8 / 0
```

Intermediate values are accepted only when the implied focal count is exactly an
integer. The library never rounds an infeasible treatment to a nearby composition.

```python
from decimal import Decimal

from abmforge_finance import (
    NarrativeDirection,
    build_narrative_homogeneity_sweep,
)

treatments = build_narrative_homogeneity_sweep(
    tuple(f"narrative-{index:04d}" for index in range(8)),
    homogeneities=(
        Decimal("0"),
        Decimal("0.25"),
        Decimal("0.50"),
        Decimal("0.75"),
        Decimal("1"),
    ),
    focal_direction=NarrativeDirection.BULLISH,
)
```

Every treatment agent remains directionally active. Focal agents receive the focal
narrative and all remaining agents receive an equally strong, equally confident
opposing narrative. This prevents narrative homogeneity from being confounded with
directional participation rate.

Agent IDs are canonicalized lexicographically and the focal group is the canonical
prefix. Across an increasing homogeneity sweep, focal sets are therefore nested rather
than randomly reassigned.

Assigned treatment and realized synchronization are distinct quantities:

```text
assigned H
    |
    v
population narrative allocation
    |
    v
realized decision concentration
    |
    v
realized accepted-order concentration
```

`measure_narrative_homogeneity()` computes realized concentration only within the
assigned narrative-treatment population, excluding passive liquidity providers and
other non-treatment agents.

For directional decisions or accepted orders:

```text
C = abs(N_buy - N_sell) / (N_buy + N_sell)
```

HOLD decisions are excluded from the directional denominator; accepted-order
concentration counts only accepted orders.

Under the controlled Phase 10B mechanism fixture, with zero decision threshold,
non-zero narrative signals, equal quantities, and sufficient two-sided liquidity,
assigned `H` equals realized decision concentration and accepted-order concentration.
That equality is a mechanism validation, not a universal market law.

Phase 10B does **not** yet claim that higher narrative homogeneity causes wider
spreads, liquidity depletion, volatility, dislocation, crashes, or tail risk. Those
market-stability effects belong to the subsequent synchronized-order-flow experiment
layer.


## Narrative synchronization and market-stability outcomes

Phase 10C.1 extends assigned population narrative homogeneity into downstream
liquidity and market-stability measurement while keeping treatment, mediator, and
outcome semantics separate.

The causal ordering is:

```text
assigned homogeneity
        |
        v
decision synchronization
        |
        v
accepted/executed order-flow synchronization
        |
        v
directional liquidity stress
        |
        v
continuous market-stability outcomes
```

The software treats only the treatment assignment and accounting mechanics as hard
properties. Statements such as "higher narrative homogeneity increases volatility"
remain experimental claims and are not encoded as invariants.

### Directional liquidity stress

Total displayed depth can miss one-sided depletion when total aggressive volume is
held fixed. Phase 10C.1 therefore adds:

```text
thin_side_depth = min(bid_depth, ask_depth)

depth_asymmetry =
    abs(bid_depth - ask_depth)
    / (bid_depth + ask_depth)

thin_side_depletion =
    1 - thin_side_depth / reference_side_depth
```

`depth_asymmetry` is undefined when both displayed sides are zero.
`reference_side_depth` is explicit and strictly positive.

This distinction matters because two treatments may consume exactly the same total
depth while very different amounts of liquidity remain on the thinner side.

### Deterministic direction schedule

`NarrativeDirectionSchedule` defines an exogenous focal-direction path that is held
fixed across homogeneity treatments. For example:

```python
from abmforge_finance import NarrativeDirection, NarrativeDirectionSchedule

schedule = NarrativeDirectionSchedule(
    (
        NarrativeDirection.BULLISH,
        NarrativeDirection.BEARISH,
        NarrativeDirection.BULLISH,
        NarrativeDirection.BEARISH,
    )
)
```

Focal agents follow the scheduled direction and opposing agents receive the opposite
direction at every step. The schedule introduces no LLM sampling, social diffusion,
or additional random-number stream.

### Active-window market-stability outcome

`evaluate_narrative_market_stability()` aggregates only the treatment-active window
and reports:

```text
assigned_homogeneity

mean_decision_concentration
mean_accepted_order_concentration
mean_executed_flow_concentration

mean_total_depth
mean_total_depth_depletion
mean_thin_side_depth
mean_thin_side_depletion
mean_depth_asymmetry

mean_relative_spread
mean_spread_amplification

mid_realized_volatility
maximum_drawdown
mean_absolute_relative_dislocation

treatment_rejected_order_count
treatment_executed_volume
market_trade_volume
```

Treatment-specific synchronization measures filter out passive liquidity providers
and other non-treatment agents.

`evaluate_narrative_market_stability_sweep()` additionally checks that a declared
homogeneity sweep keeps agent identities, focal-direction convention, narrative
strength, confidence, exposure weight, and active window fixed. Treatments may differ
only in homogeneity and treatment identifier.

The controlled ladder-book validation intentionally demonstrates a case where total
depth consumption is unchanged while thin-side depletion, depth asymmetry, price
dislocation, and midpoint volatility differ with synchronization. This is a mechanism
validation for the controlled fixture, not an empirical law.

Phase 10C.1 does not choose crash thresholds or tail-event cutoffs and does not yet run
formal multi-seed inference. Multi-seed narrative-stability execution and paired
treatment contrasts are a separate subsequent layer.


## Multi-seed narrative-stability inference

Phase 10C.2 turns the deterministic Phase 10C.1 outcome contract into a
replicated stochastic benchmark with common random numbers and paired treatment
inference.

The benchmark preserves the causal ordering:

```text
assigned homogeneity H
        |
        v
deterministic narrative direction schedule
        +
seeded background noise flow
        |
        v
Phase 10C.1 market-stability outcomes
        |
        v
matched-seed treatment differences
        |
        v
Student-t confidence intervals
```

The stochastic component is a stable population of `NoisePolicy` traders. The
same ordered seed tuple, noise-agent IDs, and component seed names are reused
across every homogeneity treatment. This creates a common-random-number design:
for seed `s`, treatment `H` and the control are exposed to the same deterministic
pseudo-random background flow.

For an outcome `Y` and control homogeneity `H0`:

```text
Delta_s(H) = Y_s(H) - Y_s(H0)
```

The paired mean effect is:

```text
mean(Delta(H)) = sum_s Delta_s(H) / n
```

and confidence intervals are delegated to the existing Phase 9C.3
`paired_treatment_contrast()` implementation rather than reimplementing
Student-t inference.

### Controlled benchmark configuration

`NarrativeStabilityBenchmarkConfig` explicitly controls:

```text
direction schedule
fundamental value
tick and lot size
passive-liquidity ladder
narrative population size
narrative order quantity
narrative strength / confidence / exposure
decision threshold
noise population size
noise order quantity
noise activity rate
scenario identity
```

The benchmark validates that passive capacity on each side strictly exceeds the
worst-case same-side narrative plus noise demand for one period. This prevents
the controlled fixture from mechanically exhausting one side of the book before
the intended treatment comparison can be evaluated.

A homogeneity sweep changes only the canonical `homogeneity` scenario parameter.
All other scenario controls and the ordered seed tuple are frozen.

```python
from decimal import Decimal

from abmforge_finance.calibration import (
    NarrativeStabilityBenchmarkConfig,
    infer_narrative_stability_sweep,
    run_narrative_stability_homogeneity_sweep,
)

config = NarrativeStabilityBenchmarkConfig()

experiments = run_narrative_stability_homogeneity_sweep(
    config,
    homogeneities=(
        Decimal("0"),
        Decimal("0.25"),
        Decimal("0.5"),
        Decimal("0.75"),
        Decimal("1"),
    ),
    seeds=(101, 202, 303, 404),
)

inference = infer_narrative_stability_sweep(
    experiments,
    metric_names=(
        "mean_thin_side_depletion",
        "mid_realized_volatility",
    ),
)
```

`NarrativeStabilityRunResult` extends the existing `CalibrationRunResult`, so
the established calibration summary and inference machinery can operate on the
new benchmark without a second statistical engine.

### Interpretation boundary

The inference layer does not assert that increasing homogeneity must increase
volatility, dislocation, drawdown, or liquidity stress. Those are empirical
simulation hypotheses.

A confidence interval that contains zero is compatible with insufficient
evidence for a non-zero paired effect under the specified benchmark. An interval
excluding zero identifies a direction for that metric under that design, but
does not by itself establish external validity or a universal market law.

The reported intervals are individual per-metric, per-treatment intervals.
Phase 10C.2 does not claim family-wise multiplicity control and does not silently
choose a primary endpoint. Primary/secondary outcomes, seed counts, robustness
regimes, and any multiplicity procedure should be prespecified before the
flagship simulation study is interpreted.


## Prespecified flagship narrative-stability study

Phase 10D freezes the flagship confirmatory study design before confirmatory
simulation results are run or interpreted. The study contract is represented both
as immutable Python objects and as a bundled machine-readable JSON snapshot.

Protocol:

```text
protocol_id      = flagship-narrative-stability-v1
protocol_version = 1.0.0
status           = precision-pilot-prespecified
fingerprint      = 483fbae4791b5f30b88bb036a994db411ce16f39a4fbd12a580679975a28c54b
```

The canonical SHA-256 fingerprint is derived from the complete study mapping rather
than from a filename or wall-clock timestamp. Runtime construction and the bundled
JSON snapshot are tested to resolve to the same mapping and fingerprint.

### Confirmatory treatment grid

```text
H = 0.00
H = 0.25
H = 0.50
H = 0.75
H = 1.00
```

`H=0` is the prespecified control.

### Outcome hierarchy

Primary:

```text
mean_thin_side_depletion
mean_absolute_relative_dislocation
```

Secondary:

```text
mean_depth_asymmetry
mid_realized_volatility
maximum_drawdown
```

Mechanism:

```text
mean_decision_concentration
mean_accepted_order_concentration
mean_executed_flow_concentration
```

Diagnostic:

```text
mean_total_depth_depletion
mean_relative_spread
mean_spread_amplification
treatment_rejected_order_count
treatment_executed_volume
market_trade_volume
```

Secondary, mechanism, and diagnostic outcomes do not become primary because they
produce favorable results.

### Primary multiplicity family

The primary family contains two primary metrics crossed with four non-control
treatment contrasts:

```text
2 metrics x 4 contrasts = 8 primary hypotheses
```

Holm family-wise error control at alpha `0.05` is prespecified. Phase 10D freezes
that decision but deliberately does not duplicate the existing paired Student-t
engine or prematurely implement confirmatory reporting. A subsequent reporting
layer must implement and test the Holm-adjusted decision table before confirmatory
claims are produced.

### Precision-based seed-count selection

Confirmatory replicate count is selected from an independent precision pilot:

```text
n = 10
n = 20
n = 40
n = 80
n = 160
```

For every candidate nested prefix, all four treatment-vs-control contrasts must
meet both 95% confidence-interval half-width targets:

```text
mean_thin_side_depletion:
    maximum half-width <= 0.02

mean_absolute_relative_dislocation:
    maximum half-width <= 0.0025
```

The selected confirmatory seed count is the smallest candidate meeting every
primary precision criterion. Selection is based on interval width only, never
effect sign, statistical significance, or whether a result is favorable.

If no candidate through `n=160` meets the precision targets, the confirmatory run
does not begin without an explicit protocol amendment.

### Independent pilot and confirmatory seeds

Pilot and confirmatory seeds are derived deterministically from separate namespaces:

```text
precision-pilot
confirmatory
```

and the protocol fingerprint. Pilot seeds are not reused in confirmatory effect
estimation.

```python
from abmforge_finance.study import (
    confirmatory_seed_tuple,
    flagship_narrative_stability_protocol,
    precision_pilot_seed_tuple,
)

protocol = flagship_narrative_stability_protocol()
pilot_seeds = precision_pilot_seed_tuple(protocol)

# Only after the precision pilot selects a prespecified candidate count:
confirmatory_seeds = confirmatory_seed_tuple(protocol, 40)
```

### Prespecified robustness regimes

Robustness analyses remain separate from the primary regime and are
one-factor-at-a-time deviations:

```text
liquidity-low
liquidity-high
noise-activity-low
noise-activity-high
noise-population-low
noise-population-high
schedule-clustered
polarity-reversed
```

They cannot replace the baseline primary regime merely because their results are
stronger.

The bundled machine-readable specification is:

```text
src/abmforge_finance/study/specs/flagship_narrative_stability_v1.json
```

The next scientific step after Phase 10D is merged is an auditable independent
precision-pilot run. Confirmatory simulations should not be launched before that
pilot produces a valid prespecified seed-count decision.


## Auditable flagship precision-pilot execution

Phase 10E operationalizes the prespecified Phase 10D replicate-count decision without
turning the precision pilot into an early look at confirmatory effect results.

The official runner:

```text
frozen runtime protocol
        |
        v
bundled JSON identity verification
        |
        v
protocol-derived pilot seed tuple
        |
        v
full H treatment grid
        |
        v
paired 95% CI widths
        |
        v
smallest prespecified n meeting every primary precision target
        |
        v
canonical precision-only artifact
```

The full protocol uses five homogeneity treatments and 160 pilot seeds, so the official
pilot executes:

```text
5 treatments x 160 seeds = 800 simulation replicates
```

### Precision-only disclosure boundary

The pilot artifact contains only information required for the replicate-count decision:

```text
artifact schema version
protocol ID / version / fingerprint
source Git commit
pilot seed namespace / count / fingerprint
candidate seed counts

for each candidate n:
    primary metric name
    target CI half-width
    treatment-specific CI half-widths
    maximum CI half-width
    criterion status

selected_seed_count
confirmatory_eligible
```

It deliberately does **not** serialize:

```text
mean treatment effects
effect signs
p-values
confidence-interval endpoints
whether an interval excludes zero
```

The artifact records:

```text
decision_basis = ci-half-width-only
effect_estimates_included = false
```

This does not make the internal Student-t calculations disappear; paired effects are
still required mathematically to obtain confidence intervals. The boundary prevents
those effect-direction results from becoming part of the official precision-pilot
output used to choose the confirmatory replicate count.

### Exact provenance verification

Before an artifact can be constructed, every pilot experiment must match:

```text
the prespecified H ordering
the exact benchmark scenario
all non-H controls
the full active horizon
the full ordered pilot seed tuple
```

Any scenario or seed mismatch causes artifact construction to fail.

The precision artifact is also self-checked against the protocol. Verification rejects
tampering with protocol identity, seed provenance, candidate counts, primary metric
order, treatment contrast order, precision targets, maximum widths, criterion flags,
or the smallest-qualifying-n decision.

### Canonical artifact serialization

Precision artifacts use canonical JSON:

```text
sorted keys
compact separators
UTF-8
one trailing newline
no wall-clock timestamp
```

CI half-width floats are emitted as deterministic 17-significant-digit strings.

The caller must provide the exact source Git commit. The writer refuses to overwrite an
existing artifact and returns SHA-256 for the exact canonical bytes.

Example after Phase 10E has been merged to a CI-green `main`:

```python
from abmforge_finance.study import (
    run_flagship_precision_pilot,
    write_precision_pilot_artifact,
)

artifact = run_flagship_precision_pilot(
    source_git_commit="<CI-GREEN-MERGED-MAIN-SHA>",
)

digest = write_precision_pilot_artifact(
    artifact,
    "artifacts/flagship/precision-pilot.json",
)
```

The result is only one of two decisions:

```text
selected_seed_count = 10 / 20 / 40 / 80 / 160
confirmatory_eligible = true
```

or:

```text
selected_seed_count = null
confirmatory_eligible = false
```

A successful precision decision authorizes the next confirmatory stage; it does not
constitute evidence for a substantive narrative-homogeneity market effect.


## Prespecified confirmatory inference and Holm reporting

Phase 10F implements the confirmatory inference contract frozen by the flagship study
protocol. It does **not** run the official confirmatory experiment during development.

The confirmatory execution boundary is:

```text
immutable precision-pilot artifact
        |
        v
exact SHA-256 + protocol verification
        |
        v
selected_seed_count = 10
        |
        v
fresh confirmatory seed namespace
        |
        v
prove pilot / confirmatory seed overlap = 0
        |
        v
5 homogeneity levels x 10 seeds
        |
        v
paired treatment-minus-control estimates
        |
        v
primary two-sided Student-t p-values
        |
        v
Holm correction across 8 primary hypotheses
        |
        v
canonical confirmatory artifact
```

The formal primary family contains two primary outcomes and four non-control
homogeneity contrasts per outcome:

```text
2 primary outcomes x 4 treatment-control contrasts = 8 hypotheses
```

Family-wise error is controlled with the prespecified Holm procedure at:

```text
alpha = 0.05
```

Primary contrasts report paired effect estimates, standard errors, nominal 95%
confidence intervals, raw two-sided p-values, Holm-adjusted p-values, and Holm rejection
decisions.

The confidence intervals are explicitly labelled:

```text
nominal-per-contrast-not-familywise
```

Holm multiplicity control applies to the eight primary p-values; the nominal confidence
intervals are estimation intervals and are not presented as simultaneous family-wise
intervals.

Secondary, mechanism, and diagnostic outcomes remain estimation-only in the canonical
confirmatory artifact. They may report paired effects, standard errors, and nominal
confidence intervals, but they do not receive p-values, Holm-adjusted p-values, or
formal rejection flags.

Confirmatory execution is gated by the archived Phase 10E precision artifact with
SHA-256:

```text
b43e9a1bfc6a40eadd0c38958068212a12d6feabfc8303c40917284a38d0be84
```

The accepted precision decision is:

```text
selected_seed_count = 10
confirmatory_eligible = true
```

Pilot and confirmatory seeds are derived from distinct protocol namespaces and exact
seed overlap is forbidden.

The official 50-simulation confirmatory run is intentionally deferred until this Phase
10F implementation has been merged and the post-merge `main` CI is green.


## Prespecified flagship robustness audit

Phase 10G implements the robustness execution contract already frozen by the flagship
study protocol. It does not modify the protocol JSON or fingerprint and it does not
introduce a second confirmatory significance search after the main results are known.

The robustness design consumes the eight prespecified one-factor regimes:

```text
liquidity-low
liquidity-high
noise-activity-low
noise-activity-high
noise-population-low
noise-population-high
schedule-clustered
polarity-reversed
```

Every regime is evaluated over the same homogeneity grid:

```text
H = 0, 0.25, 0.50, 0.75, 1.00
```

### Fresh shared robustness seeds

The execution layer derives one deterministic seed tuple from the frozen study
fingerprint under the fixed namespace:

```text
robustness-v1
```

The replicate count is inherited from the immutable confirmatory decision:

```text
selected_seed_count = 10
```

The same ten robustness seeds are shared across all eight regimes and all homogeneity
levels, preserving a common-random-number design for regime comparisons. The
robustness seed tuple must be disjoint from both the 160 precision-pilot seeds and the
10 confirmatory seeds.

The official robustness execution therefore contains:

```text
8 regimes x 5 homogeneity treatments x 10 seeds = 400 simulations
```

### Immutable confirmatory anchor

Robustness execution is anchored to the official confirmatory artifact with SHA-256:

```text
9e78c74483ca20c16fdf3dca8f518957959ec66e3d810518a78e1cb5402831ed
```

The anchor loader verifies the exact artifact bytes, protocol identity, selected
replicate count, confirmatory seed fingerprint, outcome roles, treatment order, and
the primary confirmatory effect direction before robustness execution is allowed.

### Estimation-only audit

Phase 10G intentionally creates no new p-value family, Holm family, or post-hoc
effect-size threshold.

For each primary outcome and robustness regime, the audit records:

```text
paired treatment-minus-control effect
standard error
nominal 95% confidence interval
confirmatory reference effect
robustness / confirmatory effect ratio
confirmatory-direction preservation
non-decreasing dose-response in the confirmatory direction
```

These are descriptive robustness quantities rather than a new confirmatory hypothesis
family.

Secondary, mechanism, and diagnostic outcomes remain estimation-only and do not receive
post-confirmatory significance flags.

This design lets the study report where the confirmed mechanism remains directionally
stable, where its magnitude changes, and where a dose-response pattern weakens or
reverses without redefining statistical success after seeing the confirmatory results.

The official 400-simulation robustness study is intentionally deferred until the
Phase 10G implementation has been merged and the post-merge `main` CI is green.


## Prespecified stylized-fact external validation

Phase 11A freezes an external-validity contract before any long-horizon validation
result or empirical market comparison is observed. This layer is deliberately separate
from the completed flagship confirmatory and robustness families and cannot redefine
their hypotheses, multiplicity family, or conclusions.

The machine-readable protocol is:

```text
stylized-fact-validation-v1
```

with fingerprint:

```text
a0906ab5529e78c8410448eb2e1bede78a3ab2f295d2500d5dc277a5dccf0b6b
```

The simulation design is fixed at 256 burn-in periods plus 4,096 analysis periods,
16 deterministic independent replicates, midpoint log returns, and a maximum
autocorrelation lag of 20. It inherits the fingerprinted flagship baseline ecology,
uses the control narrative homogeneity value `H=0`, and repeats the frozen
bullish/bearish direction cycle over the long horizon.

Seven signatures are prespecified. SF-04 through SF-06 are the primary
external-validity signatures because they directly probe the flagship microstructure
mechanism:

```text
SF-04  aggressor-flow price impact
SF-05  liquidity-conditioned price impact
SF-06  liquidity fragility
```

Return autocorrelation, return-tail shape, volatility clustering, and aggressor-sign
persistence are diagnostic rather than new confirmatory outcomes.

The flow estimand is explicitly `aggressor-executed-flow-imbalance`; it is not generic
limit-order-book OFI. The same estimator implementation must later be used for both
simulation and empirical data.

The empirical reference interval is prespecified as the 5th to 95th percentile of the
empirical reference distribution. Later comparison results may be classified as
`concordant`, `direction-only`, `discordant`, or `uninformative`.

Phase 11A permits no model calibration against observed stylized-fact results and
creates no new p-value or multiplicity family. Failures must be reported rather than
repaired through post-hoc parameter tuning.

The official long-horizon validation execution is intentionally deferred until the
Phase 11A implementation is merged to a CI-green `main` commit.

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
- [ADR-017: Baseline market ecology, replication, and calibration semantics](docs/adr/ADR-017-baseline-market-ecology-replication-and-calibration-semantics.md)
- [ADR-018: Fundamental tracking and common-random-number benchmark sweeps](docs/adr/ADR-018-fundamental-tracking-and-common-random-number-benchmark-sweeps.md)
- [ADR-019: Paired treatment contrasts and confidence intervals](docs/adr/ADR-019-paired-treatment-contrasts-and-confidence-intervals.md)
- [ADR-020: Robustness, sensitivity, and baseline ecology audit semantics](docs/adr/ADR-020-robustness-sensitivity-and-baseline-ecology-audit-semantics.md)
- [ADR-021: Deterministic narrative signal and policy boundary](docs/adr/ADR-021-deterministic-narrative-signal-and-policy-boundary.md)
- [ADR-022: Population narrative homogeneity treatment semantics](docs/adr/ADR-022-population-narrative-homogeneity-treatment-semantics.md)
- [ADR-023: Narrative synchronization and downstream market-stability outcomes](docs/adr/ADR-023-narrative-synchronization-and-market-stability-outcomes.md)
- [ADR-024: Multi-seed narrative-stability benchmark and paired inference](docs/adr/ADR-024-multi-seed-narrative-stability-benchmark-and-paired-inference.md)
- [ADR-025: Prespecified flagship narrative-stability study protocol](docs/adr/ADR-025-prespecified-flagship-narrative-stability-study-protocol.md)
- [ADR-026: Independent precision-pilot execution and canonical result artifact](docs/adr/ADR-026-independent-precision-pilot-execution-and-canonical-artifact.md)
- [ADR-027: Prespecified confirmatory inference and Holm reporting](docs/adr/ADR-027-prespecified-confirmatory-inference-and-holm-reporting.md)
- [ADR-028: Prespecified robustness execution and estimation-only audit](docs/adr/ADR-028-prespecified-robustness-execution-and-estimation-only-audit.md)
- [ADR-029: Prespecified stylized-fact external-validity contract](docs/adr/ADR-029-prespecified-stylized-fact-external-validity-contract.md)

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
feat/baseline-market-ecology
feat/calibration-benchmarks
feat/calibration-inference
feat/calibration-robustness
feat/narrative-signal-layer
feat/narrative-homogeneity
feat/narrative-market-stability
feat/narrative-stability-inference
feat/flagship-study-protocol
feat/flagship-precision-pilot
feat/confirmatory-holm-inference
feat/flagship-robustness-audit
```

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE).
