"""Shared fail-closed contract for checker evidence inputs.

The helpers in this module only classify repository paths.  They never recover
deleted files, consult Git history, or turn a recorded artifact into live
authority.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any


EVIDENCE_SOURCE_UNAVAILABLE = "EVIDENCE_SOURCE_UNAVAILABLE"
NOT_LIVE = "NOT_LIVE"
NON_AUTHORITATIVE = "non_authoritative"


def evidence_source(
    path: Path,
    *,
    repo_root: Path,
    label: str,
) -> dict[str, Any]:
    """Return a stable, non-authoritative source classification row."""

    try:
        display_path = str(path.relative_to(repo_root))
    except ValueError:
        display_path = str(path)
    exists = path.is_file()
    return {
        "label": label,
        "path": display_path,
        "exists": exists,
        "status": "available" if exists else "unavailable",
        "failure_code": None if exists else EVIDENCE_SOURCE_UNAVAILABLE,
        "execution_status": NOT_LIVE,
        "authority": NON_AUTHORITATIVE,
        "closure_claim_allowed": False,
    }


def unavailable_evidence_sources(sources: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        source
        for source in sources
        if source.get("failure_code") == EVIDENCE_SOURCE_UNAVAILABLE
    ]


def apply_evidence_source_contract(
    contract: dict[str, Any],
    sources: Iterable[dict[str, Any]],
    *,
    claim_fields: Iterable[str] = (),
    clear_fields: Iterable[str] = (),
) -> dict[str, Any]:
    """Attach evidence rows and force unavailable inputs to fail closed."""

    source_rows = list(sources)
    unavailable = unavailable_evidence_sources(source_rows)
    contract["evidence_sources"] = source_rows
    contract["failure_codes"] = (
        [EVIDENCE_SOURCE_UNAVAILABLE] if unavailable else []
    )
    contract["execution_status"] = NOT_LIVE
    contract["authority"] = NON_AUTHORITATIVE

    if not unavailable:
        return contract

    contract["status"] = "failed"
    contract["closure_claim_allowed"] = False
    for field in claim_fields:
        contract[field] = False
    for field in clear_fields:
        contract[field] = []

    failures = contract.setdefault("failures", [])
    for source in unavailable:
        failure = (
            f"{EVIDENCE_SOURCE_UNAVAILABLE}: "
            f"{source.get('label')}: {source.get('path')}"
        )
        if failure not in failures:
            failures.append(failure)
    return contract
