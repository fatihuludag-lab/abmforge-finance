"""Compatibility checks for the ABMForge public alpha API."""

from abmforge import Agent, Experiment, Model, ParameterGrid, Scenario


def test_required_abmforge_public_symbols_are_importable() -> None:
    """The extension's planned adapter boundary exists in ABMForge's public API."""
    required_symbols = (Agent, Model, Scenario, Experiment, ParameterGrid)

    assert all(symbol is not None for symbol in required_symbols)
