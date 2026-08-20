"""Public API tests for baseline policy symbols."""

import abmforge_finance
from abmforge_finance.policies import (
    FundamentalPolicy,
    NoisePolicy,
    TradingPolicy,
    TrendFollowingPolicy,
)


def test_policy_symbols_are_exported_from_package_root() -> None:
    assert abmforge_finance.FundamentalPolicy is FundamentalPolicy
    assert abmforge_finance.NoisePolicy is NoisePolicy
    assert abmforge_finance.TradingPolicy is TradingPolicy
    assert abmforge_finance.TrendFollowingPolicy is TrendFollowingPolicy
