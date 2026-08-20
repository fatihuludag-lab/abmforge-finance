"""Public API tests for the explicit ABMForge adapter namespace."""

from abmforge_finance.adapters import (
    FinanceABMModel,
    FinanceAdapterError,
    FinanceAdapterNotInitializedError,
    FinanceClockDriftError,
    FinanceComponents,
    FinanceOrderOutcome,
    FinanceSeedUnavailableError,
    FinanceStepResult,
    InvalidFinanceComponentsError,
)


def test_adapter_symbols_are_importable_from_adapter_namespace() -> None:
    assert FinanceABMModel.__name__ == "FinanceABMModel"
    assert FinanceComponents.__name__ == "FinanceComponents"
    assert FinanceOrderOutcome.__name__ == "FinanceOrderOutcome"
    assert FinanceStepResult.__name__ == "FinanceStepResult"
    assert issubclass(FinanceAdapterNotInitializedError, FinanceAdapterError)
    assert issubclass(FinanceClockDriftError, FinanceAdapterError)
    assert issubclass(FinanceSeedUnavailableError, FinanceAdapterError)
    assert issubclass(InvalidFinanceComponentsError, FinanceAdapterError)
