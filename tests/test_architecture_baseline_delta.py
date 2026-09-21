from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_architecture_baseline_delta.py"
SPEC = importlib.util.spec_from_file_location("check_architecture_baseline_delta", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_INVARIANT__delta_is_exact_and_sorted() -> None:
    result = MODULE._delta(["b", "a"], ["c", "b"])
    assert result == {
        "new": ["c"],
        "removed": ["a"],
        "unchanged": ["b"],
        "present": ["b", "c"],
    }


def test_INVARIANT__removed_key_requires_packet_owned_accepted_evidence() -> None:
    packets = {"packets": [{"id": "W01", "expected_removed_keys": ["k"]}]}
    missing = {"entries": {}}
    assert MODULE._resolution_errors(["k"], packets, missing) == ["missing resolution: k"]

    accepted = {
        "entries": {
            "k": {
                "status": "ACCEPTED",
                "packet_id": "W01",
                "resolution_class": "TYPED_AUTHORITY_METADATA",
                "evidence": ["path.py:1"],
                "witnesses": ["test:test_contract"],
                "authority_ceiling": "IMPLEMENTATION_ONLY_NOT_PROMOTION_NOT_PRODUCTION_NOT_LIVE_NOT_CUTOVER",
            }
        }
    }
    assert MODULE._resolution_errors(["k"], packets, accepted) == []


def test_INVARIANT__atomic_write_emits_sorted_json_bytes(tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    MODULE._atomic_json_write(path, ["a", "b"])
    assert path.read_bytes() == b'[\n  "a",\n  "b"\n]\n'
    assert json.loads(path.read_text(encoding="utf-8")) == ["a", "b"]
