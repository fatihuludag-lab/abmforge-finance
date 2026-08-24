from abmforge_finance.study import flagship_narrative_stability_protocol
from abmforge_finance.study.robustness import (
    OFFICIAL_FLAGSHIP_CONFIRMATORY_ARTIFACT_SHA256,
    load_confirmatory_robustness_anchor,
)


def test_official_confirmatory_anchor_is_locked() -> None:
    protocol = flagship_narrative_stability_protocol()
    anchor = load_confirmatory_robustness_anchor(
        "artifacts/flagship/confirmatory.json",
        protocol,
    )
    assert anchor.artifact_sha256 == OFFICIAL_FLAGSHIP_CONFIRMATORY_ARTIFACT_SHA256
    assert anchor.source_git_commit == "1c9ef59130511a9d8cf47ca343862fef3b947bd4"
    assert anchor.selected_seed_count == 10
    assert tuple(metric for metric, _ in anchor.primary_effects) == protocol.primary_metric_names
