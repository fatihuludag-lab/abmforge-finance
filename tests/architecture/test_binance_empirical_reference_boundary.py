import ast
from pathlib import Path

SOURCE = (
    Path(__file__).parents[2] / "src" / "abmforge_finance" / "study" / "binance_usdm_reference.py"
)

ALLOWED_ABMFORGE_IMPORTS = {
    "abmforge_finance.exceptions",
    "abmforge_finance.study.binance_usdm_artifacts",
    "abmforge_finance.study.binance_usdm_blocks",
    "abmforge_finance.study.binance_usdm_collector",
    "abmforge_finance.study.binance_usdm_contract",
    "abmforge_finance.study.binance_usdm_replay",
}


def test_binance_empirical_reference_selection_boundary() -> None:
    """Reference selection must remain independent of scientific outcomes."""

    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))

    observed: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module

            if module is not None and module.startswith("abmforge_finance"):
                observed.add(module)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("abmforge_finance"):
                    observed.add(alias.name)

    unexpected = observed - ALLOWED_ABMFORGE_IMPORTS

    assert not unexpected, (
        "Empirical reference-set selection acquired "
        "forbidden project dependencies: "
        f"{sorted(unexpected)}"
    )
