"""Architecture tests for trader/policy framework and market-engine separation."""

from __future__ import annotations

import ast
from pathlib import Path


def test_agent_and_policy_modules_do_not_import_framework_or_market_engine() -> None:
    """Behavior modules depend on domain contracts, not ABMForge or exchange internals."""

    package_root = Path(__file__).parents[2] / "src" / "abmforge_finance"
    for relative in ("agents", "policies"):
        for module_path in sorted((package_root / relative).glob("*.py")):
            tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    names.append(node.module or "")
                for name in names:
                    assert name != "abmforge" and not name.startswith("abmforge.")
                    assert name != "abmforge_finance.market" and not name.startswith(
                        "abmforge_finance.market."
                    )
