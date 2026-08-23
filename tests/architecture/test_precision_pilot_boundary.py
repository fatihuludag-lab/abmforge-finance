"""Phase 10E architecture checks."""

from __future__ import annotations

import ast
from pathlib import Path


def test_precision_module_does_not_import_finance_adapter_directly() -> None:
    path = Path("src/abmforge_finance/study/precision.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)

    assert not any(
        name == "abmforge_finance.adapters" or name.startswith("abmforge_finance.adapters.")
        for name in imports
    )
