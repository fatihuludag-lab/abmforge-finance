"""Architecture boundary for pure research-treatment modules."""

from __future__ import annotations

import ast
from pathlib import Path


def test_experiment_modules_do_not_import_framework_adapter_or_market_engine() -> None:
    experiment_root = Path(__file__).parents[2] / "src" / "abmforge_finance" / "experiments"
    for module_path in sorted(experiment_root.glob("*.py")):
        tree = ast.parse(
            module_path.read_text(encoding="utf-8"),
            filename=str(module_path),
        )
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.append(node.module or "")

            for name in names:
                assert name != "abmforge" and not name.startswith("abmforge.")
                assert name != "abmforge_finance.adapters" and not name.startswith(
                    "abmforge_finance.adapters."
                )
                assert name != "abmforge_finance.market" and not name.startswith(
                    "abmforge_finance.market."
                )
                assert name != "abmforge_finance.calibration" and not name.startswith(
                    "abmforge_finance.calibration."
                )
