"""Tests for the controlled public finance-domain API."""

import abmforge_finance
from abmforge_finance import domain


def test_top_level_domain_exports_match_domain_package() -> None:
    """Convenience exports resolve to the canonical domain implementations."""
    for name in domain.__all__:
        assert getattr(abmforge_finance, name) is getattr(domain, name)
