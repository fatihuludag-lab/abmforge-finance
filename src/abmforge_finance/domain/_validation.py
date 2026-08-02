"""Private validation helpers shared by immutable domain values."""

from __future__ import annotations

import math
from decimal import Decimal
from typing import TypeVar

from abmforge_finance.exceptions import DomainValidationError

_ErrorT = TypeVar("_ErrorT", bound=DomainValidationError)


def require_non_empty_text(value: object, *, field_name: str, error_type: type[_ErrorT]) -> str:
    """Return a validated non-empty string."""
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    return value


def require_decimal(
    value: object,
    *,
    field_name: str,
    error_type: type[_ErrorT],
    minimum: Decimal | None = None,
    minimum_inclusive: bool = True,
) -> Decimal:
    """Return a finite Decimal satisfying an optional lower bound."""
    if not isinstance(value, Decimal):
        raise error_type(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise error_type(f"{field_name} must be finite")
    if minimum is not None:
        below_minimum = value < minimum if minimum_inclusive else value <= minimum
        if below_minimum:
            comparator = ">=" if minimum_inclusive else ">"
            raise error_type(f"{field_name} must be {comparator} {minimum}")
    return value


def require_non_negative_int(value: object, *, field_name: str, error_type: type[_ErrorT]) -> int:
    """Return a validated non-negative integer, excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise error_type(f"{field_name} must be an integer")
    if value < 0:
        raise error_type(f"{field_name} must be non-negative")
    return value


def require_non_negative_timestamp(
    value: object, *, field_name: str, error_type: type[_ErrorT]
) -> int | float:
    """Return a finite, non-negative integer or floating-point timestamp."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise error_type(f"{field_name} must be an int or float")
    if isinstance(value, float) and not math.isfinite(value):
        raise error_type(f"{field_name} must be finite")
    if value < 0:
        raise error_type(f"{field_name} must be non-negative")
    return value
