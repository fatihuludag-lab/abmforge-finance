"""End-to-end deterministic cancel/replace liquidity integration."""

from decimal import Decimal
from pathlib import Path

from abmforge_finance import (
    Account,
    DeterministicFundamentalPath,
    DynamicPassiveLiquidityPolicy,
    Exchange,
    Instrument,
    MarketClock,
    Portfolio,
    Side,
    Trader,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.recording import (
    FinanceResearchRecorder,
    verify_finance_artifacts,
    write_finance_artifacts,
)


class DynamicLiquidityMarket(FinanceABMModel):
    recorder = FinanceResearchRecorder()

    def build_finance_components(self) -> FinanceComponents:
        instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
        exchange = Exchange(instrument)
        exchange.register(Account("a-bid", Decimal("10000")), Portfolio("a-bid"))
        exchange.register(
            Account("b-ask", Decimal("0")),
            Portfolio("b-ask", (("ACME", Decimal("100")),)),
        )
        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=DeterministicFundamentalPath(
                (Decimal("100"), Decimal("102"), Decimal("101"))
            ),
            traders=(
                Trader(
                    "a-bid",
                    DynamicPassiveLiquidityPolicy(
                        Side.BUY,
                        Decimal("10"),
                        instrument.tick_size,
                    ),
                ),
                Trader(
                    "b-ask",
                    DynamicPassiveLiquidityPolicy(
                        Side.SELL,
                        Decimal("10"),
                        instrument.tick_size,
                    ),
                ),
            ),
            research_recorder=self.recorder,
        )


def _run() -> DynamicLiquidityMarket:
    model = DynamicLiquidityMarket(seed=42)
    model.recorder = FinanceResearchRecorder()
    model.setup()
    model.run_for(3)
    return model


def test_dynamic_quotes_replace_stale_liquidity_without_accumulation() -> None:
    model = _run()
    snapshot = model.finance.exchange.snapshot()

    assert snapshot.best_bid == Decimal("100")
    assert snapshot.best_ask == Decimal("102")
    assert snapshot.order_count == 2
    assert model.last_finance_step is not None
    assert model.last_finance_step.cancellation_count == 2

    dataset = model.recorder.dataset
    dataset.validate()
    assert dataset.schema_version == "1.1"
    assert dataset.row_counts["decisions"] == 6
    assert dataset.row_counts["cancellations"] == 4
    assert dataset.row_counts["orders"] == 6
    assert dataset.row_counts["trades"] == 0
    assert dataset.row_counts["market_states"] == 3

    assert tuple((row.period, row.order_id) for row in dataset.cancellations) == (
        (1, "finance-order-000000000000"),
        (1, "finance-order-000000000001"),
        (2, "finance-order-000000000002"),
        (2, "finance-order-000000000003"),
    )
    assert tuple(
        (row.period, row.best_bid, row.best_ask, row.order_count) for row in dataset.market_states
    ) == (
        (0, Decimal("99"), Decimal("101"), 2),
        (1, Decimal("101"), Decimal("103"), 2),
        (2, Decimal("100"), Decimal("102"), 2),
    )


def test_dynamic_liquidity_artifacts_are_byte_reproducible(tmp_path: Path) -> None:
    first = _run()
    second = _run()

    left = write_finance_artifacts(
        first.recorder.dataset,
        tmp_path / "left",
        provenance={"seed": "42", "scenario": "dynamic-liquidity"},
    )
    right = write_finance_artifacts(
        second.recorder.dataset,
        tmp_path / "right",
        provenance={"scenario": "dynamic-liquidity", "seed": "42"},
    )
    verify_finance_artifacts(left)
    verify_finance_artifacts(right)

    left_payloads = {path.name: path.read_bytes() for path in left.iterdir()}
    right_payloads = {path.name: path.read_bytes() for path in right.iterdir()}
    assert left_payloads == right_payloads
    assert (left / "cancellations.jsonl").read_bytes()
