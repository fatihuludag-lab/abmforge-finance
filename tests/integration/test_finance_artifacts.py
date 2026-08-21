"""End-to-end finance model recording to deterministic research artifacts."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from abmforge_finance import (
    Account,
    ConstantFundamentalValue,
    Exchange,
    Instrument,
    MarketClock,
    Portfolio,
    Trader,
    TradingDecision,
)
from abmforge_finance.adapters import FinanceABMModel, FinanceComponents
from abmforge_finance.recording import (
    FinanceResearchRecorder,
    verify_finance_artifacts,
    write_finance_artifacts,
)


class HoldPolicy:
    def decide(self, observation, *, agent_id):  # type: ignore[no-untyped-def]
        del observation, agent_id
        return TradingDecision.hold()


class ArtifactMarket(FinanceABMModel):
    recorder = FinanceResearchRecorder()

    def build_finance_components(self) -> FinanceComponents:
        instrument = Instrument("ACME", Decimal("1"), Decimal("1"))
        exchange = Exchange(instrument)
        exchange.register(Account("a", Decimal("100")), Portfolio("a"))
        return FinanceComponents(
            exchange=exchange,
            clock=MarketClock(),
            fundamental=ConstantFundamentalValue(Decimal("100.00")),
            traders=(Trader("a", HoldPolicy()),),
            research_recorder=self.recorder,
        )


def test_model_recording_can_be_committed_as_verified_artifact_bundle(tmp_path: Path) -> None:
    model = ArtifactMarket(seed=42)
    model.recorder = FinanceResearchRecorder()
    model.setup()
    model.run_for(2)

    target = write_finance_artifacts(
        model.recorder.dataset,
        tmp_path / "run-42",
        provenance={
            "model_seed": "42",
            "scenario": "artifact-integration",
            "git_commit": "test-fixture",
        },
    )
    verify_finance_artifacts(target)

    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["tables"]["decisions"]["rows"] == 2
    assert manifest["tables"]["market_states"]["rows"] == 2
    assert manifest["tables"]["accounts"]["rows"] == 3
    assert manifest["tables"]["positions"]["rows"] == 3
    assert manifest["provenance"]["model_seed"] == "42"
