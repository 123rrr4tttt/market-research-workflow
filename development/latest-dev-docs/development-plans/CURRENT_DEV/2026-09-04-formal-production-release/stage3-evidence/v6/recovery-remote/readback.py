"""Create-only public GitHub observations; never sends credentials or mutations."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent / (sys.argv[1] if len(sys.argv) > 1 else ".")
SHA = "909eb608e538b6427bcbacca974f1efb05fef611"
TREE = "a60b795e509aa5dc479904a321fba32ed0ab9ab2"
BASE = "https://api.github.com/repos/123rrr4tttt/market-research-workflow"
ENDPOINTS = {
    "commit": f"/commits/{SHA}",
    "runs": f"/actions/runs?head_sha={SHA}",
    "checks": f"/commits/{SHA}/check-runs",
    "main": "/branches/main",
    "rulesets": "/rulesets?includes_parents=true",
    "effective-rules": "/rules/branches/main",
}

def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    records = []
    for name, endpoint in ENDPOINTS.items():
        target = ROOT / (name + ".response")
        if target.exists():
            raise RuntimeError(f"Refusing overwrite: {target}")
        command = ["curl", "--silent", "--show-error", "--max-time", "25", "--include", "--header", "Accept: application/vnd.github+json", BASE + endpoint]
        result = subprocess.run(command, capture_output=True)
        with target.open("xb") as output:
            output.write(result.stdout)
        stderr = ROOT / (name + ".stderr")
        with stderr.open("xb") as output:
            output.write(result.stderr)
        records.append({"id": name, "command": command, "cwd": str(Path.cwd()), "exit_code": result.returncode, "response": {"path": str(target), "sha256": hashlib.sha256(result.stdout).hexdigest()}, "stderr": {"path": str(stderr), "sha256": hashlib.sha256(result.stderr).hexdigest()}})
    payload = {"schema_version": "mrw.stage3.remote-observations.v1", "record_id": "v6-recovery-remote", "candidate_commit": SHA, "candidate_tree": TREE, "authoritative": False, "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "attempts": records, "external_mutations": [], "authentication": "ANONYMOUS_PUBLIC_API"}
    with (ROOT / "observations.json").open("x") as output:
        json.dump(payload, output, indent=2)
        output.write("\n")

if __name__ == "__main__":
    main()
