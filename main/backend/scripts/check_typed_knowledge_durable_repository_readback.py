#!/usr/bin/env python3
"""Wave17 gate for typed-knowledge durable repository readback contracts."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.typed_knowledge.persistence_boundary import (  # noqa: E402
    DURABLE_REPOSITORY_READBACK_CONTRACT_VERSION,
    JsonlTypedKnowledgeRepository,
    check_durable_repository_readback_contract,
)


EVIDENCE_FILE = (
    REPO_ROOT
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-03-07-typed-knowledge-organization"
    / "08_wave17-typed-knowledge-durable-readback-2026-05-22.md"
)
REQUIRED_EVIDENCE_MARKERS = (
    "contract_version: typed_knowledge.durable_repository_readback.v1",
    "durable_readback: true",
    "live_db_write: false",
    "live_db_persistence: false",
    "production_db_closure: false",
)


def main() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="typed-knowledge-readback-") as tmp_dir:
        repository = JsonlTypedKnowledgeRepository(
            storage_dir=tmp_dir,
            repository_ref="jsonl://wave17-typed-knowledge-readback",
        )
        check = check_durable_repository_readback_contract(repository=repository)

    if check["status"] != "pass":
        failures.append(f"expected pass, got {check['status']}: {check['blockers']}")
    if check["contract_version"] != DURABLE_REPOSITORY_READBACK_CONTRACT_VERSION:
        failures.append("durable repository readback contract version drifted")
    if check["durable_readback"] is not True:
        failures.append("durable readback was not validated")
    if check["live_db_write"] is not False:
        failures.append("durable readback must not claim live DB writes")
    if check["live_db_persistence"] is not False:
        failures.append("durable readback must keep live DB persistence open")
    if check["repository_ref"] != "jsonl://wave17-typed-knowledge-readback":
        failures.append("repository ref drifted from durable JSONL contract ref")
    if check["storage_kind"] != "jsonl":
        failures.append("storage kind must stay jsonl for this contract slice")
    if len(check["readback_identity_refs"]) != 4:
        failures.append(f"expected four typed knowledge readback records, got {check['readback_identity_refs']}")
    if "demo_proj:knowledge_item:ki:robotics-policy" not in check["readback_identity_refs"]:
        failures.append("knowledge item identity was not read back from durable repository")
    if "live_db_backed_typed_knowledge_readback_not_verified" not in check["remaining_live_gaps"]:
        failures.append("remaining gaps must preserve live DB-backed readback boundary")

    if not EVIDENCE_FILE.is_file():
        failures.append(f"missing evidence file: {EVIDENCE_FILE.relative_to(REPO_ROOT)}")
    else:
        evidence_text = EVIDENCE_FILE.read_text(encoding="utf-8")
        for marker in REQUIRED_EVIDENCE_MARKERS:
            if marker not in evidence_text:
                failures.append(f"evidence file missing marker {marker!r}")

    payload = {
        "status": "fail" if failures else "pass",
        "contract_status": (
            "closed_narrow_typed_knowledge_durable_repository_readback_contract"
            if not failures
            else "open_typed_knowledge_durable_repository_readback_gap"
        ),
        "failures": failures,
        "check": check,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
