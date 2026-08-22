"""Architecture boundary tests for calibration and experiment code."""

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


def test_calibration_never_imports_abmforge_directly() -> None:
    root = Path("src/abmforge_finance/calibration")
    violations: list[str] = []
    for path in sorted(root.glob("*.py")):
        for module in _imports(path):
            if module == "abmforge" or module.startswith("abmforge."):
                violations.append(f"{path.name}: {module}")
    assert violations == []


def test_only_benchmark_fixtures_depend_on_finance_adapter() -> None:
    root = Path("src/abmforge_finance/calibration")
    violations: list[str] = []
    for path in sorted(root.glob("*.py")):
        if path.name in {"baseline.py", "tracking.py"}:
            continue
        for module in _imports(path):
            if module == "abmforge_finance.adapters" or module.startswith(
                "abmforge_finance.adapters."
            ):
                violations.append(f"{path.name}: {module}")
    assert violations == []
