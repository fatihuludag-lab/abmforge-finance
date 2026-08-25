"""Architecture boundaries for Phase 11 market-signature preparation."""

from __future__ import annotations

import ast
from pathlib import Path


def _imports(path: Path) -> set[str]:
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )

    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)

    return modules


def _forbidden(
    imports: set[str],
    prefixes: tuple[str, ...],
) -> set[str]:
    return {
        module
        for module in imports
        if any(module == prefix or module.startswith(f"{prefix}.") for prefix in prefixes)
    }


def test_canonical_pipeline_is_source_neutral() -> None:
    imports = _imports(Path("src/abmforge_finance/study/stylized_pipeline.py"))

    forbidden = _forbidden(
        imports,
        (
            "abmforge_finance.recording",
            "abmforge_finance.metrics",
            "abmforge_finance.adapters",
            "abmforge_finance.study.stylized_empirical",
            "abmforge_finance.study.stylized_simulation",
            "numpy",
            "pandas",
            "scipy",
            "requests",
            "httpx",
            "websocket",
            "websockets",
        ),
    )

    assert forbidden == set()


def test_generic_empirical_adapter_is_exchange_neutral() -> None:
    imports = _imports(Path("src/abmforge_finance/study/stylized_empirical.py"))

    forbidden = _forbidden(
        imports,
        (
            "abmforge_finance.recording",
            "abmforge_finance.metrics",
            "abmforge_finance.adapters",
            "abmforge_finance.study.stylized_simulation",
            "numpy",
            "pandas",
            "scipy",
            "requests",
            "httpx",
            "websocket",
            "websockets",
            "binance",
        ),
    )

    assert forbidden == set()


def test_simulation_adapter_does_not_depend_on_empirical_sources() -> None:
    imports = _imports(Path("src/abmforge_finance/study/stylized_simulation.py"))

    forbidden = _forbidden(
        imports,
        (
            "abmforge_finance.study.stylized_empirical",
            "numpy",
            "pandas",
            "scipy",
            "requests",
            "httpx",
            "websocket",
            "websockets",
            "binance",
        ),
    )

    assert forbidden == set()
