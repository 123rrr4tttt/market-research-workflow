#!/usr/bin/env python3
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent.parent / "r13w" / "artifacts" / "finalize-evidence.py"
spec = importlib.util.spec_from_file_location("r13w_finalizer", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.ROOT = ROOT
module.COMMIT = "8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2"
module.TREE = "ce7c67c831b51f9d64b4c2f1a470a724a50b19df"
original_command = module.command


def r13x_command(*args: str) -> str:
    return original_command(*(arg.replace("r13w", "r13x") for arg in args))


module.command = r13x_command
module.main()


def replace_release_name(value):
    if isinstance(value, str):
        return value.replace("r13w", "r13x").replace("R13W", "R13X")
    if isinstance(value, list):
        return [replace_release_name(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_release_name(item) for key, item in value.items()}
    return value


for path in [
    ROOT / "execution-record.json",
    ROOT / "tool-versions.json",
    *(ROOT / "candidate" / role / "docker-load-receipt.json" for role in ("backend", "frontend", "migration-runner")),
    *(ROOT / "candidate" / role / "trivy-summary.json" for role in ("backend", "frontend", "migration-runner")),
]:
    record = replace_release_name(json.loads(path.read_text()))
    record["authoritative"] = False
    if path == ROOT / "execution-record.json":
        record["cleanup"] = {
            "status": "COMPLETED_WITH_RELEASE_INPUTS_RETAINED",
            "removed_builders": ["mrw-r13x-canonical-amd64", "mrw-r13x-replay-amd64"],
            "removed_temporary_outputs": ["trivy-cache"],
            "retained_tags": [f"mrw-local/r13x-candidate-{role}:{module.COMMIT}" for role in ("backend", "frontend", "migration-runner")],
            "retained_archives": [f"candidate/{role}/image.oci.tar" for role in ("backend", "frontend", "migration-runner")] + [f"replay/{role}/image.oci.tar" for role in ("backend", "frontend", "migration-runner")],
            "retained_layouts": [f"layouts/{role}" for role in ("backend", "frontend", "migration-runner")],
            "reason": "exact canonical inputs retained for downstream runtime/full-stack smoke",
        }
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


excluded = {
    ROOT / "SHA256SUMS",
    ROOT / "logs/finalize-evidence.log",
    ROOT / "logs/checksums-verify.log",
    ROOT / "metadata/checksums-verify.exit",
}
paths = sorted(path for path in ROOT.rglob("*") if path.is_file() and path not in excluded and (ROOT / "trivy-cache") not in path.parents)
(ROOT / "SHA256SUMS").write_text("\n".join(f"{digest(path)}  {path.relative_to(ROOT).as_posix()}" for path in paths) + "\n")
