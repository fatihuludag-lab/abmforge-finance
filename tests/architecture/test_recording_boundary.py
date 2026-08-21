"""Architecture tests for the framework-independent recording layer."""

from __future__ import annotations

import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_recording_layer_does_not_import_abmforge_or_adapter() -> None:
    violations: list[str] = []
    root = Path("src/abmforge_finance/recording")
    for path in root.rglob("*.py"):
        imported = _imports(path)
        if any(
            module == "abmforge"
            or module.startswith("abmforge.")
            or module == "abmforge_finance.adapters"
            or module.startswith("abmforge_finance.adapters.")
            for module in imported
        ):
            violations.append(str(path))
    assert violations == []
