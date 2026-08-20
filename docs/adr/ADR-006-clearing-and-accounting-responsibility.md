# ADR-006: Clearing and accounting responsibility

## Status

Accepted for Phase 4.

## Context

Phase 3 converts incoming orders and resting liquidity into immutable `Trade`
records. Those records identify the buyer, seller, instrument, exact price and
quantity, maker/taker roles, execution sequence, and signed buyer/seller fees. A
trade is not yet a settled economic transfer: participant cash and inventory still
need to change exactly once and conservation identities need to remain auditable.

The first research core must support transparent financial accounting before trader
policies, ABMForge integration, or AI experiments are added. At the same time,
clearing must remain independent from ABMForge and from the matching algorithm so
that market mechanics can be tested as ordinary Python components.

## Decision

1. `Account` is an immutable participant cash value object. It represents any finite
   `Decimal` balance; borrowing policy belongs to clearing rather than the domain
   primitive.
2. `Portfolio` is an immutable deterministic sparse inventory value object. Positions
   are sorted `(instrument_id, quantity)` pairs. Negative positions are representable
   at the domain layer so future margin/short-selling models do not require a new
   value type.
3. `ClearingEngine` owns registered account and portfolio state and settles immutable
   `Trade` values atomically with respect to those ledgers.
4. The baseline clearing policy disallows negative participant cash. Borrowing and
   margin are out of scope.
5. Short selling is disabled by default and can be enabled explicitly with
   `allow_short_selling=True`.
6. A positive participant fee means cash paid by that participant; a negative fee is
   a rebate. For notional `N`:

   - buyer cash delta = `-(N + buyer_fee)`;
   - seller cash delta = `N - seller_fee`;
   - venue fee delta = `buyer_fee + seller_fee`.

   Participant cash plus the venue fee balance is therefore conserved exactly.
7. Buyer inventory increases by trade quantity and seller inventory decreases by the
   same quantity. Aggregate instrument units are conserved exactly.
8. Trade identifiers are settlement idempotency keys. A successfully settled
   `trade_id` cannot settle again. Accepted settlements also require non-decreasing
   `executed_at` values and strictly increasing trade `sequence_number` values.
9. Validation is completed and replacement `Account`/`Portfolio` values are created
   before internal state is mutated. Expected settlement failures therefore leave
   clearing state unchanged.
10. Self-trades remain representable because the `Trade` domain permits them. Their
    notional and inventory transfers net to zero for the participant; only signed
    fees can change participant cash. A future exchange policy may reject self-trades
    before matching.
11. Phase 4 does **not** make matching and clearing one atomic transaction. Until the
    exchange orchestration layer exists, callers must not interpret standalone
    matching followed by failed settlement as a valid market event. Phase 5 must add
    pre-trade admissibility/risk checks before orders reach matching.

## Alternatives considered

### Mutate cash and inventory directly inside `MatchingEngine`

Rejected. It would couple execution price/priority logic to participant accounting,
make isolated mechanism tests harder, and prevent later clearing-policy variants.

### Put cash and all positions into one mutable trader object

Rejected. It would tie accounting state to a future agent implementation and weaken
framework independence and auditability.

### Require all risk constraints to be enforced only at settlement time

Rejected as an integrated-market design. Settlement rejection after matching can
leave the order book economically inconsistent. Phase 4 retains defensive rejection
for standalone correctness, but the future exchange layer must prevalidate orders.

### Add margin, collateral, settlement delay, or multi-currency ledgers now

Rejected under YAGNI. The first research core needs exact spot cash/inventory
accounting, not a broker-dealer back office.

## Consequences

- Cash and inventory transfers can be audited independently of matching.
- Duplicate settlement is explicit and testable.
- Exact `Decimal` conservation avoids floating-point accounting drift.
- Short-selling assumptions become an explicit experimental configuration.
- Signed fee/rebate accounting is already compatible with a future `FeeModel`.
- Matching and settlement are not yet safe to compose blindly; Phase 5 exchange
  orchestration is required before end-to-end market experiments.

## Risks

- A caller can still run matching first and discover insufficient funds or inventory
  only at clearing. This is a known Phase 4 integration boundary, not a valid
  end-to-end exchange workflow.
- Allowing negative positions in the domain value object can be misunderstood as
  enabling short selling globally. Only `ClearingEngine(allow_short_selling=True)`
  permits settlement into negative inventory.
- Fee rebates can make the venue fee balance negative. This is intentional and must
  be interpreted as a net venue payout, not a conservation failure.

## Validation plan

- Unit tests for account and portfolio immutability and validation.
- Unit tests for cash/inventory transfer, signed fees, rebates, self-trades, duplicate
  settlement, event-order rejection, unknown participants, insufficient cash, and
  insufficient inventory.
- Tests that failed settlement leaves every ledger and the fee balance unchanged.
- Property tests for exact cash-plus-fee conservation, exact inventory conservation,
  and deterministic replay from identical starting state.
- Ruff, strict Mypy, branch-aware coverage, build, clean-install, and full CI matrix.
