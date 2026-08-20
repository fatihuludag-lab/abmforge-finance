"""Compatibility checks for the ABMForge public alpha API."""

from __future__ import annotations

import abmforge
from abmforge.api import STABLE_ALPHA_API
from abmforge.core.agent import Agent
from abmforge.core.model import Model
from abmforge.experiment.experiment import Experiment
from abmforge.experiment.parameter_grid import ParameterGrid
from abmforge.experiment.scenario import Scenario

from abmforge_finance.adapters import FinanceABMModel

_REQUIRED_PUBLIC_SYMBOLS = {
    "Agent": Agent,
    "Model": Model,
    "Scenario": Scenario,
    "Experiment": Experiment,
    "ParameterGrid": ParameterGrid,
}


def test_required_symbols_are_declared_stable_alpha() -> None:
    """Required adapter symbols remain in ABMForge's stable-alpha API."""
    assert set(_REQUIRED_PUBLIC_SYMBOLS).issubset(STABLE_ALPHA_API)


def test_required_symbols_are_available_from_top_level_api() -> None:
    """Top-level ABMForge exports resolve to their canonical implementations."""
    for name, canonical_symbol in _REQUIRED_PUBLIC_SYMBOLS.items():
        assert getattr(abmforge, name) is canonical_symbol


def test_finance_adapter_subclasses_stable_abmforge_model() -> None:
    """The finance adapter binds only to the stable-alpha ABMForge Model contract."""
    assert issubclass(FinanceABMModel, Model)
