#!/usr/bin/env python3
"""Check the typed-knowledge persistence/API boundary contract."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "main" / "backend"
if sys.version_info < (3, 10):
    candidates = (
        os.environ.get("PYTHON311"),
        shutil.which("python3.11"),
        "/Users/wangyiliang/.local/bin/python3.11",
    )
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and Path(candidate) != Path(sys.executable):
            os.execv(candidate, [candidate, *sys.argv])

sys.path.insert(0, str(BACKEND))

from app.services.typed_knowledge import persistence_boundary as boundary  # noqa: E402


EVIDENCE_FILES = (
    ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-typed-knowledge-organization"
    / "05_wave12-worker7-persistence-api-boundary-evidence-2026-05-22.md",
    ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-writing-workbench-evolution"
    / "06_wave12-worker7-typed-knowledge-persistence-boundary-evidence-2026-05-22.md",
)
REQUIRED_EVIDENCE_MARKERS = (
    "contract_readiness: ready",
    "live_db_persistence: false",
    "public_api_route: false",
    "governance_ui: false",
    "remaining_live_gaps",
)


def main() -> int:
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    envelope = boundary.build_sample_boundary_envelope()
    boundary.validate_persistence_api_envelope(envelope)
    records = envelope["data"]["records"]
    item_records = [record for record in records if record["object_type"] == "knowledge_item"]
    writing_refs = envelope["data"]["writing_handoff_refs"]
    readiness = envelope["meta"]["readiness"]

    check(envelope["status"] == "ok", "envelope status must be ok")
    check(len(records) == 4, "sample envelope must include four typed knowledge object records")
    check(len(item_records) == 1, "sample envelope must include one knowledge item")
    check(item_records[0]["identity_ref"] == "demo_proj:knowledge_item:ki:robotics-policy", "lost item identity ref")
    check(item_records[0]["visibility_scope"] == "downstream_ready", "knowledge item must be downstream ready")
    check(item_records[0]["lifecycle_state"] == "active", "knowledge item lifecycle must be active")
    check(len(writing_refs) == 1, "sample envelope must preserve one writing handoff ref")
    check(writing_refs[0]["consumer"] == "writing.keyword_card", "writing handoff ref consumer mismatch")
    check(writing_refs[0]["card_source_type"] == "resource", "writing handoff ref must remain resource card")
    check(readiness.get("repository_contract") is True, "repository contract readiness missing")
    check(readiness.get("api_envelope") is True, "api envelope readiness missing")
    check(readiness.get("live_db_persistence") is False, "checker must not claim live DB persistence")
    check(readiness.get("public_api_route") is False, "checker must not claim public API route completion")
    check(readiness.get("governance_ui") is False, "checker must not claim governance UI completion")
    check(
        "live_db_persistence_not_implemented" in envelope["meta"]["remaining_live_gaps"],
        "remaining gaps must include live DB persistence",
    )
    check(
        all(write["live_db_write"] is False for write in envelope["data"]["writes"]),
        "all persistence writes must stay in-memory/contract-only",
    )

    for evidence_file in EVIDENCE_FILES:
        if not evidence_file.is_file():
            failures.append(f"missing evidence file: {evidence_file.relative_to(ROOT)}")
            continue
        text = evidence_file.read_text(encoding="utf-8")
        for marker in REQUIRED_EVIDENCE_MARKERS:
            if marker not in text:
                failures.append(f"{evidence_file.relative_to(ROOT)} missing marker {marker!r}")

    summary = {
        "status": "ok" if not failures else "failed",
        "contract_version": boundary.PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION,
        "fingerprint": boundary.boundary_fingerprint(envelope),
        "records": len(records),
        "writing_handoff_refs": len(writing_refs),
        "repository_ref": envelope["data"]["repository"]["repository_ref"],
        "contract_readiness": envelope["meta"]["contract_readiness"],
        "readiness": readiness,
        "remaining_live_gaps": envelope["meta"]["remaining_live_gaps"],
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
