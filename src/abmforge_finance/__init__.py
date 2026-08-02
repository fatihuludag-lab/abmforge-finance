"""Public package interface for :mod:`abmforge_finance`.

The bootstrap release intentionally exports only package metadata. Financial
market domain objects will be introduced through small, separately reviewed
feature branches.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("abmforge-finance")
except PackageNotFoundError:  # pragma: no cover - only for an unpackaged source tree
    __version__ = "0.1.0a0"

__all__ = ["__version__"]
