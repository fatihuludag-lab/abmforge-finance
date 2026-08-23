"""Architecture boundary for the top-level study layer."""

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


def test_lower_layers_never_import_study_layer() -> None:
    root = Path("src/abmforge_finance")
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if "study" in path.parts:
            continue
        for module in _imports(path):
            if module == "abmforge_finance.study" or module.startswith("abmforge_finance.study."):
                violations.append(f"{path}: {module}")
    assert violations == []
