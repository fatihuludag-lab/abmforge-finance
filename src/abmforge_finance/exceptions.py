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


class MarketClockError(MarketError):
    """Base class for deterministic market-clock failures."""


class InvalidMarketTimeError(MarketClockError):
    """Raised when a discrete market period is invalid."""


class FundamentalValueError(MarketError):
    """Base class for fundamental-value process failures."""


class InvalidFundamentalValueError(FundamentalValueError):
    """Raised when a fundamental process configuration or value is invalid."""


class FundamentalPathExhaustedError(FundamentalValueError):
    """Raised when a frozen fundamental path is queried outside its defined horizon."""


class InvalidObservationError(DomainValidationError):
    """Raised when a policy-facing market observation violates its value contract."""


class InvalidDecisionError(DomainValidationError):
    """Raised when a policy decision violates the decision contract."""


class PolicyError(FinanceError):
    """Base class for framework-independent trading-policy failures."""


class InvalidPolicyError(PolicyError):
    """Raised when policy configuration, input, or output is invalid."""


class InvalidTraderError(FinanceError):
    """Raised when trader identity or policy composition is invalid."""


class FinanceAdapterError(FinanceError):
    """Base class for ABMForge finance-adapter failures."""


class FinanceAdapterNotInitializedError(FinanceAdapterError):
    """Raised when adapter state is accessed before finance setup completes."""


class InvalidFinanceComponentsError(FinanceAdapterError):
    """Raised when a finance model returns an invalid component bundle."""


class FinanceClockDriftError(FinanceAdapterError):
    """Raised when ABMForge model steps and finance market time diverge."""


class FinanceSeedUnavailableError(FinanceAdapterError):
    """Raised when deterministic component-seed derivation lacks a model seed."""


class RecordingError(FinanceError):
    """Base class for finance research-recording failures."""


class RecordingStateError(RecordingError):
    """Raised when recorder lifecycle or event metadata is inconsistent."""


class InvalidFinanceDatasetError(RecordingError):
    """Raised when a finance research dataset violates schema-v1 invariants."""


class FinanceArtifactError(RecordingError):
    """Base class for deterministic finance research-artifact failures."""


class InvalidFinanceArtifactError(FinanceArtifactError):
    """Raised when artifact configuration or serialization input is invalid."""


class FinanceArtifactExistsError(FinanceArtifactError):
    """Raised when no-overwrite artifact creation targets an existing path."""


class FinanceArtifactVerificationError(FinanceArtifactError):
    """Raised when a persisted finance artifact bundle fails verification."""
