"""Public API checks for narrative domain and policy symbols."""

import abmforge_finance
from abmforge_finance import domain, policies


def test_narrative_domain_symbols_are_exported_from_package_root() -> None:
    for name in (
        "NarrativeDirection",
        "NarrativeExposure",
        "NarrativeSignal",
        "NarrativeState",
        "aggregate_narrative_signal",
    ):
        assert getattr(abmforge_finance, name) is getattr(domain, name)


def test_narrative_policy_is_exported_from_package_root() -> None:
    assert abmforge_finance.NarrativePolicy is policies.NarrativePolicy
