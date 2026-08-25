"""Architecture boundary for Binance empirical block validity."""

from __future__ import annotations

import ast
from pathlib import Path


def test_binance_block_validity_does_not_import_estimators() -> None:
    path = Path("src/abmforge_finance/study/binance_usdm_blocks.py")

    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )

    imported_modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)

        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    forbidden = {
        module
        for module in imported_modules
        if (
            module == "abmforge_finance.study.stylized_estimators"
            or module.startswith("abmforge_finance.study.stylized_estimators.")
        )
    }

    assert forbidden == set()
