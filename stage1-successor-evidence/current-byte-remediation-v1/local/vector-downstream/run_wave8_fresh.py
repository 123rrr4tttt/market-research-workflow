#!/usr/bin/env python3
"""Fresh offline Wave8 wrapper with explicit current input paths.

This wrapper deliberately does not read the historical claim-016 Wave8 output.
All evidence inputs are copied under the current-byte vector-downstream root.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
INPUTS = OUT / "inputs"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("wave8_fresh", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Wave8 generator module")  # noqa: TRY003
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    mod = _load(ROOT / "ops/search-lab/scripts/wave8_search_vectorization_contract.py")
    mod.SEARCH_PROVIDER_TRACE = INPUTS / "search_provider_trace_contract.json"
    mod.SEARCH_PROVIDER_CONTAINER_REPLAY = INPUTS / "provider_trace_replay_summary.json"
    mod.LOCAL_INDEX_RUNTIME = INPUTS / "runtime_smoke_results.json"
    mod.LOCAL_INDEX_BENCHMARK = INPUTS / "benchmark_quality_results.json"
    contract = mod.build_contract()
    mod.write_outputs(OUT / "wave8", contract)
    print(json.dumps({"status": contract["status"], "out_dir": str(OUT / "wave8")}, sort_keys=True))
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
