#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


BASE_RUNNER = Path(
    "/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/"
    "development-plans/CURRENT_DEV/2026-09-04-formal-production-release/"
    "stage3-evidence/r13v/artifacts/backend-migration-amd64-candidate-replay/"
    "run_r13v_backend_migration.py"
)
RETRY_OUT = Path(__file__).resolve().parent

spec = importlib.util.spec_from_file_location("r13v_backend_migration_runner", BASE_RUNNER)
if spec is None or spec.loader is None:
    raise SystemExit("cannot load base r13v runner")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
runner.OUT = RETRY_OUT

raise SystemExit(runner.main())
