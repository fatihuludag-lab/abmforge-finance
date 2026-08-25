# ADR-032: Binance USD-M empirical market-data contract

## Status

Accepted.

## Context

ADR-029 prespecified the Phase 11 stylized-fact external-validity study.

ADR-030 froze the statistical semantics of SF-01 through SF-07.

ADR-031 froze the canonical source-neutral preparation boundary and required
simulation and empirical representations of the same economic path to produce
equivalent `MarketSignatureInput` measurements.

The next requirement is to freeze the first real empirical source before
official empirical observations are inspected or external-validity results
are computed.

This contract concerns data acquisition and source-specific reconstruction.
It does not change the shared estimators or the canonical preparation
semantics.

## Documentation basis

The contract is based on the Binance USD-M Futures public API documentation
available on 2026-08-25.

Any future Binance API change that changes the scientific meaning of the
captured variables requires explicit review. Official Phase 11 empirical
samples must record the implemented contract version.

## Venue and instrument

The primary empirical source is:

- venue: Binance;
- product family: USD-M Futures;
- primary symbol: BTCUSDT;
- pair: BTCUSDT;
- required contract type: PERPETUAL;
- required trading status: TRADING;
- quote asset: USDT;
- margin asset: USDT;
- required stream symbol type: 1, identifying USD-M;
- timezone: UTC.

Before an official capture begins, `/fapi/v1/exchangeInfo` must confirm the
required symbol identity, contract type, status, quote asset, and margin asset.

ETHUSDT or other instruments are not substitutes for the primary BTCUSDT
reference. They may later be introduced as separately identified robustness
sources.

## WebSocket routing

The contract uses the current routed Binance Futures WebSocket topology.

Depth data use the public route:

`wss://fstream.binance.com/public/ws/btcusdt@depth`

Aggregate trades use the market route:

`wss://fstream.binance.com/market/ws/btcusdt@aggTrade`

The two routed streams are treated as separate source channels.

The standard diff-depth stream is fixed at 100 ms:

`btcusdt@depth@100ms`

The aggregate-trade stream uses its documented 100 ms update cadence.

Changing either source cadence during the official study is a protocol change.

Legacy assumptions that all streams can be consumed from an unrouted
connection are not part of this contract.

A WebSocket reconnect is a source discontinuity. A candidate empirical block
must not silently span a depth-book resynchronization.

## Empirical time scale

Canonical empirical observations are UTC-aligned one-second intervals.

The one-second empirical interval is a prespecified market-data sampling
choice. It does not assert that one ABM simulation period corresponds to one
physical second.

Each empirical reference block contains exactly 4096 canonical observations,
matching the frozen simulation analysis-horizon sample size.

The primary empirical reference distribution uses 64 non-overlapping valid
blocks.

Therefore the intended complete reference consists of 262144 one-second
canonical observations before any separately prespecified robustness sample.

Blocks rejected because of source-integrity failures do not count toward the
64 valid reference blocks.

## Aggregate-trade flow

The Binance aggregate-trade stream provides market trades aggregated over
short intervals when price and taking side agree.

Aggressor direction is determined from the buyer-maker field `m`.

If `m` is false, the buyer is the taker and the observation contributes to
buy-aggressor quantity.

If `m` is true, the buyer is the maker and the seller is the taker; the
observation contributes to sell-aggressor quantity.

The quantity used by the official Phase 11 empirical flow calculation is
`nq`, the normal quantity excluding trades involving RPI orders.

For interval t:

`Q_buy_t = sum(nq where m is false)`

`Q_sell_t = sum(nq where m is true)`

and

`flow_t =
    (Q_buy_t - Q_sell_t)
    / (Q_buy_t + Q_sell_t)`

when total normal aggressor quantity is positive.

If no normal market-trade quantity occurs in an otherwise valid observed
interval, `flow_t = 0.0`.

Zero measured flow is valid observed data. It is not missing data.

SF-07 later removes zero-flow intervals according to ADR-030.

The stream symbol-type field `st` must identify USD-M when supplied by the
source contract. Official capture code must reject a conflicting symbol type.

## RPI consistency

The standard Binance USD-M depth endpoint excludes Retail Price Improvement
orders.

For that reason the empirical aggressor-flow calculation uses `nq`, which
excludes RPI trade quantity, rather than total aggregate quantity `q`.

This keeps the displayed-liquidity and aggressor-flow measurements aligned to
the same non-RPI market representation as closely as the public API permits.

Changing from `nq` to `q` during the official study is a protocol change.

## Local order-book reconstruction

The initial local book is seeded from:

`GET /fapi/v1/depth?symbol=BTCUSDT&limit=1000`

The snapshot limit is fixed at 1000.

Depth events received before snapshot synchronization are buffered.

Events whose final update id `u` is below the REST `lastUpdateId` are
discarded.

The first processed depth event must satisfy:

`U <= lastUpdateId <= u`

For each subsequent processed event:

`pu == previous_u`

must hold.

A failure of this continuity relation invalidates the active candidate block.
The local book is discarded and initialized again from a new REST snapshot.

Depth-update quantities are absolute quantities for their price levels.

A quantity of zero removes the corresponding price level.

Removing a level that is not currently represented locally is not by itself
treated as a sequence failure.

## Depth measurement

The empirical adapter measures captured displayed non-RPI liquidity from the
synchronized local-book representation seeded by the 1000-level snapshot and
maintained by subsequent depth updates.

The synchronized local book is an event-driven state.

If no diff-depth update occurs during an otherwise continuous and valid
one-second interval, the most recently synchronized local-book state persists
until a later absolute depth update changes it.

Using that still-valid state at an interval close is state persistence, not
forward filling of missing market data.

State persistence is permitted only while the WebSocket session remains valid
and update-id continuity has not failed. A sequence gap or reconnect
invalidates the active candidate according to this ADR.

For each valid one-second interval, the interval-closing synchronized local
book supplies:

- best bid;
- best ask;
- bid-side maintained displayed quantity;
- ask-side maintained displayed quantity.

Midpoint is:

`mid_t = (best_bid_t + best_ask_t) / 2`

Thin-side depth is:

`D_t = min(bid_depth_t, ask_depth_t)`

ADR-031 then constructs:

`r_t = log(mid_t / mid_{t-1})`

`pre_depth_t = D_{t-1}`

`relative_depth_drop_t = (D_{t-1} - D_t) / D_{t-1}`

The empirical depth measure is explicitly a public-API captured displayed
depth measure. It must not be described as complete hidden exchange
liquidity.

## Missing-data and integrity policy

The collector must not:

- forward-fill a broken order book;
- interpolate a missing synchronized depth state;
- silently repair an update-id discontinuity;
- convert an unavailable trade stream to measured zero flow;
- combine observations across an unsynchronized depth reconnect.

A depth sequence gap invalidates the active candidate block.

A connection failure requiring depth reinitialization invalidates the active
candidate block.

A new valid block may begin only after the local depth book has been
successfully resynchronized.

## Raw-data preservation

Raw source observations used by an official empirical block are preserved
before scientific aggregation.

The canonical raw storage representation is deterministic JSON Lines.

Raw chunks and derived manifests use SHA-256 content hashes.

A later artifact layer must preserve at least:

- empirical contract id;
- repository commit SHA;
- symbol;
- capture start and end timestamps;
- source stream identities;
- REST snapshot identity;
- raw chunk hashes;
- block-validity status;
- rejection reason when invalid;
- prepared observation count.

Raw files are immutable inputs. Scientific preparation must not overwrite
them.

## Reference-block rule

The primary empirical reference consists of the first 64 candidate blocks
that satisfy the frozen validity contract.

Invalid candidate blocks are recorded but excluded.

Valid blocks are non-overlapping.

Selection must not depend on the resulting SF-01 through SF-07 estimates.

The empirical 5th and 95th percentile reference limits are computed only
after the required valid reference set is complete.

## Consequences

The empirical source definition is fixed before official external-validity
results are inspected.

The Binance-specific collector terminates at the generic empirical preparation
boundary defined by ADR-031.

No Binance-specific logic may enter the shared estimators.

Changes to the symbol, physical interval, flow quantity field, RPI treatment,
book synchronization rule, depth representation, missing-data policy, block
size, or reference-block selection after official collection begins require a
new empirical-contract version.


### Complete UTC-second acceptance

Canonical empirical intervals must not include a partially observed opening
second.

Offline reconstruction establishes a market-data readiness time as the later
of:

1. the first synchronized local-book transaction time; and
2. the first observed aggregate-trade trade time.

The first accepted interval begins at the first UTC-second boundary at or after
that readiness time.

The synchronized book state immediately preceding that boundary is retained as
the seed state for the first accepted interval.

The closing boundary is conservatively bounded by the final synchronized depth
event. A capture artifact is written only after both coupled WebSocket reader
tasks complete normally; a reader failure invalidates the capture rather than
creating zero-flow observations.

Thus partial opening or closing seconds are not admitted to the empirical
reference sample.
