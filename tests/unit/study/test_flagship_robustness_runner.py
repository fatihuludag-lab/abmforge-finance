"""Official Phase 10G runner boundary without executing 400 simulations."""

from __future__ import annotations

from typing import cast

import pytest

from abmforge_finance.calibration import CalibrationExperimentResult
from abmforge_finance.study import flagship_narrative_stability_protocol
from abmforge_finance.study import robustness as robustness_module
from abmforge_finance.study.robustness import (
    ConfirmatoryRobustnessAnchor,
    RobustnessAuditArtifact,
)


def test_official_robustness_runner_verifies_and_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    protocol = flagship_narrative_stability_protocol()
    calls: list[str] = []

    monkeypatch.setattr(
        robustness_module,
        "flagship_narrative_stability_protocol",
        lambda: protocol,
    )
    monkeypatch.setattr(
        robustness_module,
        "verify_bundled_flagship_protocol",
        lambda value: calls.append(f"verify:{value.protocol_id}"),
    )

    anchor = ConfirmatoryRobustnessAnchor(
        artifact_sha256="a" * 64,
        source_git_commit="b" * 40,
        protocol_fingerprint=protocol.fingerprint,
        precision_artifact_sha256="c" * 64,
        selected_seed_count=10,
        confirmatory_seed_fingerprint="d" * 64,
        primary_effects=tuple(
            (
                metric,
                tuple((h, float(index + 1)) for index, h in enumerate(protocol.homogeneities[1:])),
            )
            for metric in protocol.primary_metric_names
        ),
    )

    def fake_loader(
        *args: object,
        **kwargs: object,
    ) -> ConfirmatoryRobustnessAnchor:
        calls.append("load")
        return anchor

    monkeypatch.setattr(
        robustness_module,
        "load_confirmatory_robustness_anchor",
        fake_loader,
    )
    monkeypatch.setattr(
        robustness_module,
        "robustness_seed_tuple",
        lambda _protocol, _count: tuple(range(10)),
    )

    fake_experiments = cast(
        tuple[CalibrationExperimentResult, ...],
        tuple(object() for _ in protocol.homogeneities),
    )

    def fake_sweep(
        *args: object,
        **kwargs: object,
    ) -> tuple[CalibrationExperimentResult, ...]:
        calls.append("sweep")
        return fake_experiments

    monkeypatch.setattr(
        robustness_module,
        "run_narrative_stability_homogeneity_sweep",
        fake_sweep,
    )

    sentinel = cast(RobustnessAuditArtifact, object())

    def fake_builder(
        protocol_arg: object,
        anchor_arg: object,
        regimes_arg: object,
        *,
        source_git_commit: str,
        confidence_level: float = 0.95,
    ) -> RobustnessAuditArtifact:
        assert protocol_arg == protocol
        assert anchor_arg is anchor
        assert source_git_commit == "e" * 40
        assert confidence_level == 0.95
        assert len(cast(tuple[object, ...], regimes_arg)) == 8
        calls.append("build")
        return sentinel

    monkeypatch.setattr(
        robustness_module,
        "build_robustness_audit_artifact",
        fake_builder,
    )

    result = robustness_module.run_flagship_robustness_audit(
        confirmatory_artifact_path="unused.json",
        source_git_commit="e" * 40,
    )

    assert result is sentinel
    assert calls[:2] == [
        f"verify:{protocol.protocol_id}",
        "load",
    ]
    assert calls.count("sweep") == 8
    assert calls[-1] == "build"
