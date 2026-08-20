"""Exception hierarchy for ABMForge-Finance."""


class FinanceError(Exception):
    """Base class for all package-specific errors.

    Determinism
    -----------
    Exception types and messages depend only on the validated inputs.
    """


class DomainValidationError(FinanceError):
    """Base class for invalid finance-domain values."""


class InvalidInstrumentError(DomainValidationError):
    """Raised when an instrument definition is internally inconsistent."""


class InvalidPriceError(DomainValidationError):
    """Raised when a price is invalid or not aligned to an instrument tick."""


class InvalidQuantityError(DomainValidationError):
    """Raised when a quantity is invalid or not aligned to an instrument lot."""


class InvalidOrderError(DomainValidationError):
    """Raised when an order violates the domain contract."""


class InvalidTradeError(DomainValidationError):
    """Raised when a trade violates the domain contract."""


class MarketError(FinanceError):
    """Base class for market-engine operation failures."""


class OrderBookError(MarketError):
    """Base class for deterministic limit-order-book failures."""


class InvalidBookOrderError(OrderBookError):
    """Raised when an order cannot be represented as active resting liquidity."""


class CrossingOrderError(InvalidBookOrderError):
    """Raised when a marketable order is sent directly to the resting book."""


class DuplicateOrderError(OrderBookError):
    """Raised when an order identifier is reused within one book lifetime."""


class DuplicateSequenceNumberError(OrderBookError):
    """Raised when a deterministic submission sequence number is reused."""


class OrderNotFoundError(OrderBookError):
    """Raised when an operation targets an order that is not active."""


class OverfillError(OrderBookError):
    """Raised when a fill exceeds an order's active remaining quantity."""


class InvalidDepthError(OrderBookError):
    """Raised when a depth or snapshot level limit is invalid."""


class OrderBookInvariantError(OrderBookError):
    """Raised when internal order-book indexes are inconsistent."""
