"""Package import smoke tests."""

import abmforge_finance


def test_package_import_exposes_version() -> None:
    """The public package imports and exposes a non-empty version string."""
    assert isinstance(abmforge_finance.__version__, str)
    assert abmforge_finance.__version__
