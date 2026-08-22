"""Property tests for passive-liquidity quote geometry."""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from abmforge_finance import MarketObservation, PassiveLiquidityPolicy, Side


@given(
    reference=st.decimals(
        min_value=Decimal("1.00"),
        max_value=Decimal("1000.00"),
        allow_nan=False,
        allow_infinity=False,
        places=2,
    ),
    offset=st.integers(min_value=1, max_value=10),
)
def test_paired_quotes_straddle_reference_and_remain_tick_aligned(
    reference: Decimal,
    offset: int,
) -> None:
    tick = Decimal("0.01")
    observation = MarketObservation(
        step=0,
        instrument_id="ACME",
        fundamental_value=reference,
    )
    bid = PassiveLiquidityPolicy(
        Side.BUY,
        Decimal("1"),
        tick,
        offset_ticks=offset,
    ).decide(observation, agent_id="bid")
    ask = PassiveLiquidityPolicy(
        Side.SELL,
        Decimal("1"),
        tick,
        offset_ticks=offset,
    ).decide(observation, agent_id="ask")

    assert bid.price is not None
    assert ask.price is not None
    assert bid.price < reference < ask.price
    assert bid.price % tick == 0
    assert ask.price % tick == 0
    assert bid.price < ask.price
