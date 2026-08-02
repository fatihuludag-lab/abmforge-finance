"""Distribution metadata tests."""

from importlib.metadata import metadata, version

import abmforge_finance


def test_distribution_name_and_version_match_package() -> None:
    """Installed metadata and the import package report the same identity."""
    distribution = metadata("abmforge-finance")

    assert distribution["Name"] == "abmforge-finance"
    assert version("abmforge-finance") == abmforge_finance.__version__


def test_distribution_requires_supported_python() -> None:
    """The declared Python floor remains explicit in built metadata."""
    distribution = metadata("abmforge-finance")

    assert distribution["Requires-Python"] == ">=3.10"


def test_distribution_declares_abmforge_compatibility_range() -> None:
    """The package metadata declares the audited ABMForge release line."""
    requirements = metadata("abmforge-finance").get_all("Requires-Dist") or []

    assert "abmforge<0.4,>=0.3.0a1" in requirements
