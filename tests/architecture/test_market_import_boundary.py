"""Architecture tests for the framework-independent market engine."""

from __future__ import annotations

import ast
from pathlib import Path


def test_market_engine_does_not_import_abmforge() -> None:
    """Pure market modules must not depend on ABMForge framework classes."""
    market_root = Path(__file__).parents[2] / "src" / "abmforge_finance" / "market"

    for module_path in sorted(market_root.rglob("*.py")):
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names = [alias.name for alias in node.names]
                assert not any(
                    name == "abmforge" or name.startswith("abmforge.") for name in imported_names
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module != "abmforge" and not module.startswith("abmforge.")
