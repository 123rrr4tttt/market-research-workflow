"""Policy channel adapter: wrap ingest.policy.ingest_policy_documents."""

from __future__ import annotations

from typing import Any, Dict


def handle_policy(params: Dict[str, Any], _project_key: str | None) -> Dict[str, Any]:
    """Ingest policy documents by state."""
    from ...ingest.policy import ingest_policy_documents

    state = str(params.get("state") or "")
    source_hint = params.get("source_hint")
    return ingest_policy_documents(state=state, source_hint=source_hint)
