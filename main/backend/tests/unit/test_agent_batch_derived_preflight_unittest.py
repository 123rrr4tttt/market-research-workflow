from __future__ import annotations

import inspect

from app.services.agent_batch.search_quality_replay import (
    build_live_provider_gap_state,
    build_symbolic_live_quality_threshold_contract,
    build_symbolic_provider_quality_readiness,
    build_symbolic_quality_promotion_readback_gate,
    build_symbolic_quality_regression_evaluator,
)


def test_INVARIANT__symbolic_quality_preflights_are_non_authoritative() -> None:
    builders = (
        build_live_provider_gap_state,
        build_symbolic_provider_quality_readiness,
        build_symbolic_live_quality_threshold_contract,
        build_symbolic_quality_regression_evaluator,
        build_symbolic_quality_promotion_readback_gate,
    )
    for builder in builders:
        annotation = inspect.signature(builder).return_annotation
        assert "NonAuthoritativeDict" in str(annotation), builder.__name__

    gap = build_live_provider_gap_state()
    assert gap.authoritative is False
    assert gap.reverse_write is False
    assert gap.derived_as == "preflight"
    assert gap.fact_source
    assert gap == {
        "status": "not_run",
        "live_provider_probe_performed": False,
        "providers_not_started": ["searxng", "yacy", "web"],
        "quality_claim_allowed": False,
        "reason": "deterministic replay does not start SearXNG, YaCy, browser, or external web providers",
        "unsupported_claims": [
            "searxng_live_quality_verified",
            "yacy_live_quality_verified",
            "web_live_quality_verified",
        ],
    }
