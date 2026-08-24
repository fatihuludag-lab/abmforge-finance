from abmforge_finance import study


def test_phase10g_public_api() -> None:
    for name in (
        "ConfirmatoryRobustnessAnchor",
        "OFFICIAL_FLAGSHIP_CONFIRMATORY_ARTIFACT_SHA256",
        "RobustnessAuditArtifact",
        "RobustnessRegimeExperiments",
        "build_robustness_audit_artifact",
        "load_confirmatory_robustness_anchor",
        "robustness_seed_tuple",
        "run_flagship_robustness_audit",
        "write_robustness_audit_artifact",
    ):
        assert hasattr(study, name)
