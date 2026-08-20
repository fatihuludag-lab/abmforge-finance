"""Property tests for adapter seed and order-identity determinism."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from abmforge_finance import (
    Account,
    ConstantFundamentalValue,
    Exchange,
    Instrument,
    MarketClock,
    Portfolio,
    Side,
    Trader,
    TradingDecision,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.policies import TradingPolicy


class HoldPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.hold()


class LimitPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.limit(Side.BUY, Decimal("1"), Decimal("99"))


class PropertyModel(FinanceABMModel):
    policy: TradingPolicy = HoldPolicy()

    def build_finance_components(self) -> FinanceComponents:
        instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
        exchange = Exchange(instrument)
        exchange.register(Account("agent", Decimal("1000")), Portfolio("agent"))
        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100")),
            traders=(Trader("agent", self.policy),),
        )


@given(seed=st.integers(min_value=0, max_value=2**63 - 1), name=st.text(min_size=1))
def test_finance_seed_exact_replay(seed: int, name: str) -> None:
    normalized = name.strip()
    if not normalized:
        return
    first = PropertyModel(seed=seed)
    second = PropertyModel(seed=seed)
    assert first.finance_seed(normalized) == second.finance_seed(normalized)


def test_order_identity_replays_across_equal_models() -> None:
    first = PropertyModel(seed=10)
    second = PropertyModel(seed=10)
    first.policy = LimitPolicy()
    second.policy = LimitPolicy()
    first.setup()
    second.setup()
    first._run_for(1, finalize=False)
    second._run_for(1, finalize=False)
    first_result = first.last_finance_step
    second_result = second.last_finance_step
    assert first_result is not None and second_result is not None
    assert first_result.outcomes[0].order == second_result.outcomes[0].order
