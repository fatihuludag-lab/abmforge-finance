"""Property tests for deterministic finance recording."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from abmforge_finance import Account, Exchange, Instrument, Portfolio, Trader, TradingDecision
from abmforge_finance.recording import FinanceResearchRecorder


class HoldPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.hold()


@given(order=st.permutations(("a", "b", "c")))
def test_participant_capture_is_input_order_independent(order: list[str]) -> None:
    exchange = Exchange(Instrument("ACME", Decimal("1"), Decimal("1")))
    for agent_id in ("a", "b", "c"):
        exchange.register(Account(agent_id, Decimal("100")), Portfolio(agent_id))
    traders = tuple(Trader(agent_id, HoldPolicy()) for agent_id in order)

    recorder = FinanceResearchRecorder()
    recorder.start(exchange, traders)

    assert tuple(row.agent_id for row in recorder.dataset.participants) == ("a", "b", "c")
