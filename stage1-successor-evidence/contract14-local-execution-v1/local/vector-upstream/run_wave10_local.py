#!/usr/bin/env python3
"""Bounded adapter for Wave10 with explicit local prerequisite paths."""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")  # noqa: TRY003
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    mod = load(ROOT / "ops/search-lab/scripts/wave10_vectorization_quality_gate.py", "wave10_local")
    mod.SEARCH_PROVIDER_TRACE = OUT / "search-provider-trace/search_provider_trace_contract.json"
    mod.LOCAL_INDEX_RUNTIME = OUT / "lancedb-runtime/runtime_smoke_results.json"
    mod.LOCAL_INDEX_BENCHMARK = OUT / "lancedb-benchmark/benchmark_quality_results.json"
    contract = mod.build_contract()
    mod.write_outputs(OUT / "wave10", contract)
    print(mod.json.dumps({"status": contract["status"], "out_dir": str(OUT / "wave10")}, sort_keys=True))
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
