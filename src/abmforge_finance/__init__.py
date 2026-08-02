"""Public package interface for :mod:`abmforge_finance`."""

from importlib.metadata import PackageNotFoundError, version

from abmforge_finance.domain import Instrument, Order, OrderType, Side, TimeInForce, Trade
from abmforge_finance.exceptions import (
    DomainValidationError,
    FinanceError,
    InvalidInstrumentError,
    InvalidOrderError,
    InvalidPriceError,
    InvalidQuantityError,
    InvalidTradeError,
)

try:
    __version__ = version("abmforge-finance")
except PackageNotFoundError:  # pragma: no cover - only for an unpackaged source tree
    __version__ = "0.1.0a0"

__all__ = [
    "DomainValidationError",
    "FinanceError",
    "Instrument",
    "InvalidInstrumentError",
    "InvalidOrderError",
    "InvalidPriceError",
    "InvalidQuantityError",
    "InvalidTradeError",
    "Order",
    "OrderType",
    "Side",
    "TimeInForce",
    "Trade",
    "__version__",
]
