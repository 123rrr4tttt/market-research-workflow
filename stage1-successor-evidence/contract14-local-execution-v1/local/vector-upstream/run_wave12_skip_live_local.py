#!/usr/bin/env python3
"""Bounded Wave12 --skip-live-probes adapter using the fresh local Wave10 receipt."""
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
    wave10 = load(ROOT / "ops/search-lab/scripts/wave10_vectorization_quality_gate.py", "wave10_for_wave12")
    wave10.SEARCH_PROVIDER_TRACE = OUT / "search-provider-trace/search_provider_trace_contract.json"
    wave10.LOCAL_INDEX_RUNTIME = OUT / "lancedb-runtime/runtime_smoke_results.json"
    wave10.LOCAL_INDEX_BENCHMARK = OUT / "lancedb-benchmark/benchmark_quality_results.json"
    wave12 = load(ROOT / "ops/search-lab/scripts/wave12_provider_readiness_gate.py", "wave12_local")
    wave12._load_wave10_gate_module = lambda: wave10
    contract = wave12.build_contract(enable_live_probes=False)
    wave12.write_outputs(OUT / "wave12-skip-live", contract)
    print(
        wave12.json.dumps(
            {
                "status": contract["status"],
                "readiness_state": contract["readiness_state"],
                "out_dir": str(OUT / "wave12-skip-live"),
            },
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
