from __future__ import annotations

import pytest

from app.services.ingest.postprocess_frontdoor import run_unified_structured_extraction

pytestmark = pytest.mark.unit


def test_unified_extraction_is_blocked_without_agent_cell_context() -> None:
    result = run_unified_structured_extraction(content="evidence text" * 20)

    assert result["status"] == "failed"
    assert result["reason"] == "agent_cell_binding_required"
    assert result["model_profile"] == {}
    assert result["domains"] == {}
