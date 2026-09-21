#!/usr/bin/env python3
"""Bounded Wave14 adapter with explicit fresh Wave10/Wave12 paths."""
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
    mod = load(ROOT / "main/backend/scripts/check_wave14_vectorization_provider_capability.py", "wave14_local")
    contract = mod.build_contract(
        wave10_path=OUT / "wave10/contract_summary.json",
        wave12_path=OUT / "wave12-skip-live/provider_readiness_summary.json",
    )
    mod.write_outputs(OUT / "wave14", contract)
    print(
        mod.json.dumps(
            {
                "status": contract["status"],
                "capability_state": contract["capability_state"],
                "closure_claim_allowed": contract["closure_claim_allowed"],
                "out_dir": str(OUT / "wave14"),
            },
            sort_keys=True,
        )
    )
    return 0 if contract["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
