"""Public API tests for market-engine symbols."""

import abmforge_finance
from abmforge_finance.market import DepthLevel, LimitOrderBook, OrderBookSnapshot


def test_market_symbols_are_exported_from_package_root() -> None:
    """Researchers can import the initial order-book API from package root."""
    assert abmforge_finance.DepthLevel is DepthLevel
    assert abmforge_finance.LimitOrderBook is LimitOrderBook
    assert abmforge_finance.OrderBookSnapshot is OrderBookSnapshot
