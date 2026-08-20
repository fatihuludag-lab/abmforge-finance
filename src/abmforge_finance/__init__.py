"""Public package interface for :mod:`abmforge_finance`."""

from importlib.metadata import PackageNotFoundError, version

from abmforge_finance.domain import Instrument, Order, OrderType, Side, TimeInForce, Trade
from abmforge_finance.exceptions import (
    CrossingOrderError,
    DomainValidationError,
    DuplicateOrderError,
    DuplicateSequenceNumberError,
    FinanceError,
    InvalidBookOrderError,
    InvalidDepthError,
    InvalidIncomingOrderError,
    InvalidInstrumentError,
    InvalidOrderError,
    InvalidPriceError,
    InvalidQuantityError,
    InvalidTradeError,
    MarketError,
    MatchingEngineError,
    OrderBookError,
    OrderBookInvariantError,
    OrderNotFoundError,
    OverfillError,
)
from abmforge_finance.market import (
    DepthLevel,
    LimitOrderBook,
    MatchingEngine,
    MatchResult,
    OrderBookSnapshot,
)

try:
    __version__ = version("abmforge-finance")
except PackageNotFoundError:  # pragma: no cover - only for an unpackaged source tree
    __version__ = "0.1.0a0"

__all__ = [
    "CrossingOrderError",
    "DepthLevel",
    "DomainValidationError",
    "DuplicateOrderError",
    "DuplicateSequenceNumberError",
    "FinanceError",
    "Instrument",
    "InvalidBookOrderError",
    "InvalidDepthError",
    "InvalidIncomingOrderError",
    "InvalidInstrumentError",
    "InvalidOrderError",
    "InvalidPriceError",
    "InvalidQuantityError",
    "InvalidTradeError",
    "LimitOrderBook",
    "MarketError",
    "MatchResult",
    "MatchingEngine",
    "MatchingEngineError",
    "Order",
    "OrderBookError",
    "OrderBookInvariantError",
    "OrderBookSnapshot",
    "OrderNotFoundError",
    "OrderType",
    "OverfillError",
    "Side",
    "TimeInForce",
    "Trade",
    "__version__",
]
