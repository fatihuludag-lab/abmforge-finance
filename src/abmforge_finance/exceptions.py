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


class MatchingEngineError(MarketError):
    """Base class for deterministic matching-engine failures."""


class InvalidIncomingOrderError(MatchingEngineError):
    """Raised when an incoming order cannot be accepted by the matching engine."""


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


class InvalidAccountError(DomainValidationError):
    """Raised when an account value violates the domain contract."""


class InvalidPortfolioError(DomainValidationError):
    """Raised when a portfolio value violates the domain contract."""


class ClearingError(FinanceError):
    """Base class for deterministic clearing and settlement failures."""


class InvalidClearingRegistrationError(ClearingError):
    """Raised when participant ledger registration is inconsistent."""


class DuplicateParticipantError(ClearingError):
    """Raised when a participant is registered more than once."""


class UnknownParticipantError(ClearingError):
    """Raised when settlement references an unregistered participant."""


class DuplicateSettlementError(ClearingError):
    """Raised when the same trade identifier is submitted for settlement twice."""


class OutOfOrderSettlementError(ClearingError):
    """Raised when trade event order moves backwards or repeats a sequence."""


class InsufficientCashError(ClearingError):
    """Raised when settlement would violate the non-negative cash policy."""


class InsufficientInventoryError(ClearingError):
    """Raised when settlement would create a disallowed short position."""


class SettlementInvariantError(ClearingError):
    """Raised when internal settlement conservation identities are violated."""


class ExchangeError(MarketError):
    """Base class for deterministic exchange-orchestration failures."""


class InsufficientBuyingPowerError(ExchangeError):
    """Raised when cash cannot support all post-transaction resting buy commitments."""


class InsufficientAvailableInventoryError(ExchangeError):
    """Raised when inventory cannot support all resting sell commitments."""


class OrderOwnershipError(ExchangeError):
    """Raised when a participant attempts to cancel another participant's order."""


class ExchangeInvariantError(ExchangeError):
    """Raised when staged matching and settlement results are internally inconsistent."""
