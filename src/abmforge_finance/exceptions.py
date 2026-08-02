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
