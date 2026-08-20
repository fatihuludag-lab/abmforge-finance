"""Architecture tests for the narrow ABMForge dependency boundary."""

from __future__ import annotations

import ast
from pathlib import Path


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_only_adapter_package_imports_abmforge() -> None:
    package_root = Path("src/abmforge_finance")
    violations: list[str] = []
    for path in package_root.rglob("*.py"):
        relative = path.relative_to(package_root)
        if relative.parts and relative.parts[0] == "adapters":
            continue
        if any(
            module == "abmforge" or module.startswith("abmforge.")
            for module in _imported_modules(path)
        ):
            violations.append(str(relative))
    assert violations == []
