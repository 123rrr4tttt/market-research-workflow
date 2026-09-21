"""Create-only, version-only environment observations; never start/connect DB services."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent
COMMANDS = {
    "docker-context": ["docker", "context", "show"],
    "docker-version": ["docker", "version"],
    "compose-version": ["docker", "compose", "version"],
    "buildx-version": ["docker", "buildx", "version"],
    "node-version": ["node", "--version"],
    "node22-homebrew-version": ["/opt/homebrew/opt/node@22/bin/node", "--version"],
    "python-version": ["python3", "--version"],
    "python311-version": ["python3.11", "--version"],
    "backend-python311-version": ["/Users/wangyiliang/market-research-workflow/main/backend/.venv311/bin/python", "--version"],
    "psql-version": ["psql", "--version"],
    "pg-isready-version": ["pg_isready", "--version"],
    "initdb-version": ["initdb", "--version"],
    "pg-ctl-version": ["pg_ctl", "--version"],
    "cosign-version": ["cosign", "version"],
    "syft-version": ["syft", "version"],
    "trivy-version": ["trivy", "--version"],
}

def main():
    targets = [ROOT / (key + ".raw.log") for key in COMMANDS] + [ROOT / "observations.v1.json"]
    if any(path.exists() for path in targets):
        raise SystemExit("CREATE_ONLY_TARGET_EXISTS")
    records = []
    for key, command in COMMANDS.items():
        start = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30, check=False)
            raw, code = result.stdout, result.returncode
        except FileNotFoundError as error:
            raw, code = str(error).encode() + b"\n", 127
        except subprocess.TimeoutExpired as error:
            raw, code = (error.stdout or b"") + b"\nTIMEOUT_30_SECONDS\n", 124
        path = ROOT / (key + ".raw.log")
        with path.open("xb") as stream:
            stream.write(raw)
        records.append({"id": key, "command": command, "cwd": str(Path.cwd()), "started_at": start, "exit_code": code, "raw": path.name, "sha256": hashlib.sha256(raw).hexdigest(), "available_for_version_query": code == 0})
    report = {"schema_version": "mrw.amendment16.environment-preparation.v1", "authoritative": False, "candidate_bound": False, "services_started": [], "databases_contacted": [], "installations": [], "records": records}
    with (ROOT / "observations.v1.json").open("x") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
