"""Architecture boundary for the Phase 11A prespecification layer."""

from pathlib import Path


def test_stylized_protocol_does_not_depend_on_future_validation_implementation() -> None:
    source = Path("src/abmforge_finance/study/stylized_protocol.py").read_text(encoding="utf-8")

    assert "abmforge_finance.validation" not in source
    assert "pandas" not in source
    assert "numpy" not in source
    assert "scipy" not in source
