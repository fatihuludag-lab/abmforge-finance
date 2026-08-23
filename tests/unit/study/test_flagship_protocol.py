"""Tests for the frozen flagship protocol."""

from decimal import Decimal

from abmforge_finance.study import (
    MultiplicityMethod,
    OutcomeRole,
    apply_robustness_regime,
    bundled_flagship_protocol_mapping,
    flagship_narrative_stability_protocol,
)


def test_flagship_protocol_contract() -> None:
    protocol = flagship_narrative_stability_protocol()

    assert protocol.homogeneities == (
        Decimal("0"),
        Decimal("0.25"),
        Decimal("0.5"),
        Decimal("0.75"),
        Decimal("1"),
    )
    assert protocol.primary_metric_names == (
        "mean_thin_side_depletion",
        "mean_absolute_relative_dislocation",
    )
    assert protocol.multiplicity_method is MultiplicityMethod.HOLM
    assert protocol.primary_hypothesis_count == 8

    roles = {item.metric_name: item.role for item in protocol.outcomes}
    assert roles["mid_realized_volatility"] is OutcomeRole.SECONDARY
    assert roles["mean_decision_concentration"] is OutcomeRole.MECHANISM


def test_protocol_matches_bundled_snapshot_and_fingerprint() -> None:
    protocol = flagship_narrative_stability_protocol()

    assert protocol.to_mapping() == bundled_flagship_protocol_mapping()
    assert (
        protocol.fingerprint == "483fbae4791b5f30b88bb036a994db411ce16f39a4fbd12a580679975a28c54b"
    )


def test_prespecified_robustness_regimes_remain_valid() -> None:
    protocol = flagship_narrative_stability_protocol()

    assert apply_robustness_regime(
        protocol,
        "liquidity-low",
    ).passive_quantity_per_level == Decimal("3")
    assert (
        apply_robustness_regime(
            protocol,
            "noise-population-high",
        ).noise_trader_count
        == 6
    )
