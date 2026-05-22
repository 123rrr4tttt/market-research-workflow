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


TYPED_TOPIC = ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-typed-knowledge-organization"
WRITING_TOPIC = ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-writing-workbench-evolution"

LEGACY_REQUIRED_EVIDENCE_MARKERS = (
    "contract_readiness: ready",
    "live_db_persistence: false",
    "public_api_route: false",
    "governance_ui: false",
    "remaining_live_gaps",
)
WAVE19_REQUIRED_EVIDENCE_MARKERS = (
    "contract_version: typed_knowledge.persisted_card_request_response_readback.v1",
    "persisted_card_request_response_readback: true",
    "deterministic_persisted_ui_api_boundary: true",
    "live_db_closure: false",
    "live_api_closure: false",
    "live_ui_closure: false",
    "shared_indexes_edited: false",
)
EVIDENCE_REQUIREMENTS = {
    TYPED_TOPIC / "05_wave12-worker7-persistence-api-boundary-evidence-2026-05-22.md": LEGACY_REQUIRED_EVIDENCE_MARKERS,
    WRITING_TOPIC / "06_wave12-worker7-typed-knowledge-persistence-boundary-evidence-2026-05-22.md": (
        LEGACY_REQUIRED_EVIDENCE_MARKERS
    ),
    TYPED_TOPIC / "09_wave19-persisted-card-api-boundary-readback-2026-05-22.md": WAVE19_REQUIRED_EVIDENCE_MARKERS,
    WRITING_TOPIC / "10_wave19-persisted-card-ui-api-boundary-readback-2026-05-22.md": (
        WAVE19_REQUIRED_EVIDENCE_MARKERS
    ),
}


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
    route_envelope = boundary.build_public_api_route_contract_envelope(project_key="demo_proj")
    boundary.validate_public_api_route_contract_envelope(route_envelope)
    persisted_readback = route_envelope["data"]["persisted_card_request_response_readback"]
    boundary.validate_persisted_card_request_response_readback(persisted_readback)
    request_body = persisted_readback["keyword_card_request"]["body"]
    response_body = persisted_readback["keyword_card_response"]["body"]
    persisted_doc = persisted_readback["persisted_document"]

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
    check(
        persisted_readback["contract_version"] == boundary.PERSISTED_CARD_REQUEST_RESPONSE_READBACK_CONTRACT_VERSION,
        "persisted card readback contract version mismatch",
    )
    check(
        persisted_readback["typed_knowledge_api_boundary"]["route_path"] == boundary.PUBLIC_API_ROUTE_PATH,
        "persisted card readback must identify typed-knowledge API boundary route",
    )
    check(
        persisted_readback["typed_knowledge_api_boundary"]["live_db_backed"] is False,
        "persisted card readback must not claim live DB-backed API",
    )
    check(
        persisted_doc["metadata_json"]["typed_knowledge_context"]
        == request_body["context"]["typed_knowledge_context"],
        "persisted document typed context must read back into keyword-card request body",
    )
    check(
        request_body["sources"] == ["document", "resource", "graph"],
        "persisted UI request must preserve Writing Workbench default sources",
    )
    check(response_body["cards"][0]["publisher"] == "typed_knowledge", "response card publisher mismatch")
    check(response_body["cards"][0]["source_type"] == "resource", "response card must stay resource")
    check(
        response_body["cards"][0]["extra"]["knowledge_item_key"] == "ki:robotics-policy",
        "response card lost typed knowledge identity",
    )
    check(
        persisted_readback["meta"]["readiness"]["repo_local_persisted_card_readback"] is True,
        "repo-local persisted card readback readiness missing",
    )
    check(
        persisted_readback["meta"]["readiness"]["live_db_persistence"] is False,
        "persisted card readback must not claim live DB closure",
    )
    check(
        persisted_readback["meta"]["readiness"]["live_api_closure"] is False,
        "persisted card readback must not claim live API closure",
    )
    check(
        persisted_readback["meta"]["readiness"]["live_ui_closure"] is False,
        "persisted card readback must not claim live UI closure",
    )

    for evidence_file, markers in EVIDENCE_REQUIREMENTS.items():
        if not evidence_file.is_file():
            failures.append(f"missing evidence file: {evidence_file.relative_to(ROOT)}")
            continue
        text = evidence_file.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                failures.append(f"{evidence_file.relative_to(ROOT)} missing marker {marker!r}")

    summary = {
        "status": "ok" if not failures else "failed",
        "contract_version": boundary.PERSISTENCE_API_BOUNDARY_CONTRACT_VERSION,
        "fingerprint": boundary.boundary_fingerprint(envelope),
        "records": len(records),
        "writing_handoff_refs": len(writing_refs),
        "repository_ref": envelope["data"]["repository"]["repository_ref"],
        "public_api_route": route_envelope["data"]["route"]["path"],
        "persisted_card_readback": {
            "contract_version": persisted_readback["contract_version"],
            "card_id": persisted_readback["readback"]["card_id"],
            "publisher": persisted_readback["readback"]["publisher"],
            "card_source_type": persisted_readback["readback"]["card_source_type"],
            "live_db_persistence": persisted_readback["meta"]["readiness"]["live_db_persistence"],
            "live_api_closure": persisted_readback["meta"]["readiness"]["live_api_closure"],
            "live_ui_closure": persisted_readback["meta"]["readiness"]["live_ui_closure"],
        },
        "contract_readiness": envelope["meta"]["contract_readiness"],
        "readiness": readiness,
        "remaining_live_gaps": envelope["meta"]["remaining_live_gaps"],
        "failures": failures,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
