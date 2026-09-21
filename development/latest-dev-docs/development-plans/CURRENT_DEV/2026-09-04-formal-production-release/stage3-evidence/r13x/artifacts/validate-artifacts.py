#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent.parent / "r13w" / "artifacts" / "validate-artifacts.py"
spec = importlib.util.spec_from_file_location("r13w_validator", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ROOT = ROOT
exit_code = module.main()
path = ROOT / "artifact-comparison.json"
record = json.loads(path.read_text())
record["authoritative"] = False
record["source_commit"] = "8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2"
record["source_tree"] = "ce7c67c831b51f9d64b4c2f1a470a724a50b19df"
record["builders"] = {"candidate": "mrw-r13x-canonical-amd64", "replay": "mrw-r13x-replay-amd64"}
path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
for flavor in ("candidate", "replay"):
    for role in ("backend", "frontend", "migration-runner"):
        inspection_path = ROOT / flavor / role / "digest-inspection.json"
        inspection = json.loads(inspection_path.read_text())
        inspection["authoritative"] = False
        inspection_path.write_text(json.dumps(inspection, indent=2, sort_keys=True) + "\n")
raise SystemExit(exit_code)
