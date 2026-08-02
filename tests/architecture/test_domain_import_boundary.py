"""Architectural tests for the pure finance-domain boundary."""

from __future__ import annotations

import ast
from pathlib import Path


def test_domain_modules_do_not_import_abmforge() -> None:
    """Pure domain modules remain independent from the ABMForge framework."""
    domain_root = Path(__file__).parents[2] / "src" / "abmforge_finance" / "domain"

    for module_path in sorted(domain_root.glob("*.py")):
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
