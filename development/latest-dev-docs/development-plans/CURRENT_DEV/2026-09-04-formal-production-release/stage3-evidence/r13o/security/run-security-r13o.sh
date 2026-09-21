#!/usr/bin/env bash
set -u

CANDIDATE=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13o/candidate
OUT=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13o/security
R13N_IMAGE_EVIDENCE=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13n/evidence/images
PINNED_KIT_COMMIT=785ff25e201c9eae84c862e68e786bc975e7a800
TMP_ROOT="$(mktemp -d /tmp/mrw-r13o-security.XXXXXX)"
KIT_CHECKOUT="$TMP_ROOT/functorial-kit"

cleanup() {
  rm -rf "$TMP_ROOT"
}
trap cleanup EXIT

run_logged() {
  local name="$1"
  local cwd="$2"
  shift 2
  printf '%q ' "$@" > "$OUT/${name}.command.txt"
  printf '\n' >> "$OUT/${name}.command.txt"
  (
    cd "$cwd" || exit 125
    "$@"
  ) > "$OUT/${name}.log" 2>&1
  local code=$?
  printf '%s\n' "$code" > "$OUT/${name}.exit.txt"
  return 0
}

{
  git -C "$CANDIDATE" rev-parse HEAD HEAD^{tree}
  git -C "$CANDIDATE" status --short --untracked-files=all
  git -C "$CANDIDATE" rev-parse \
    33a841f43cc80f4871119f017138f0cb87a966c6:main/backend \
    3669d4ddc19fb722058976b4e1f05e99eccfe96e:main/backend \
    33a841f43cc80f4871119f017138f0cb87a966c6:src \
    3669d4ddc19fb722058976b4e1f05e99eccfe96e:src \
    33a841f43cc80f4871119f017138f0cb87a966c6:main/frontend-modern \
    3669d4ddc19fb722058976b4e1f05e99eccfe96e:main/frontend-modern
} > "$OUT/identity-and-role-inputs.log" 2>&1
printf '%s\n' "$?" > "$OUT/identity-and-role-inputs.exit.txt"

{
  docker version
  syft version
  trivy version
  bandit --version
  pip-audit --version
  gitleaks version
  pnpm --version
  node --version
} > "$OUT/tool-versions.log" 2>&1
printfprintf=''
printf '%s\n' "$?" > "$OUT/tool-versions.exit.txt"

run_logged bandit "$CANDIDATE" \
  bandit -q -r main/backend/app -x main/backend/tests \
  --severity-level high --confidence-level high --format json \
  --output "$OUT/bandit.report.json"

run_logged functorial-kit-clone "$TMP_ROOT" \
  git clone --filter=blob:none --no-checkout \
  https://github.com/123rrr4tttt/functorial-kit.git "$KIT_CHECKOUT"
if [[ "$(<"$OUT/functorial-kit-clone.exit.txt")" == 0 ]]; then
  run_logged functorial-kit-checkout "$KIT_CHECKOUT" \
    git checkout --detach "$PINNED_KIT_COMMIT"
else
  printf '%s\n' 125 > "$OUT/functorial-kit-checkout.exit.txt"
  printf '%s\n' 'not run because clone failed' > "$OUT/functorial-kit-checkout.log"
fi

if [[ "$(<"$OUT/functorial-kit-checkout.exit.txt")" == 0 ]]; then
  printf '%q ' docker run --rm --network default \
    -v "$CANDIDATE:/candidate:ro" \
    -v "$KIT_CHECKOUT:/kit:ro" \
    -v "$OUT:/evidence" \
    --entrypoint sh sha256:66807fd419c59ebe7cac87756c1106ba1145908c2c1d9454622063fd462f0d9d \
    -c 'python -m pip install --quiet bandit==1.8.6 && python /candidate/scripts/formal_release/check_functorial_kit_dependency_audit.py --requirements /candidate/main/backend/requirements.txt --pyproject /candidate/pyproject.toml --manifest /candidate/tools/functorial-kit/consumer-gate.manifest.json --source-checkout /kit --public-requirements /evidence/public-pypi-requirements.txt --report /evidence/functorial-kit-audit.report.json --bandit bandit' \
    > "$OUT/functorial-kit-audit.command.txt"
  printf '\n' >> "$OUT/functorial-kit-audit.command.txt"
  docker run --rm --network default \
    -v "$CANDIDATE:/candidate:ro" \
    -v "$KIT_CHECKOUT:/kit:ro" \
    -v "$OUT:/evidence" \
    --entrypoint sh sha256:66807fd419c59ebe7cac87756c1106ba1145908c2c1d9454622063fd462f0d9d \
    -c 'python -m pip install --quiet bandit==1.8.6 && python /candidate/scripts/formal_release/check_functorial_kit_dependency_audit.py --requirements /candidate/main/backend/requirements.txt --pyproject /candidate/pyproject.toml --manifest /candidate/tools/functorial-kit/consumer-gate.manifest.json --source-checkout /kit --public-requirements /evidence/public-pypi-requirements.txt --report /evidence/functorial-kit-audit.report.json --bandit bandit' \
    > "$OUT/functorial-kit-audit.log" 2>&1
  printf '%s\n' "$?" > "$OUT/functorial-kit-audit.exit.txt"
else
  printf '%s\n' 125 > "$OUT/functorial-kit-audit.exit.txt"
  printf '%s\n' 'not run because pinned source checkout failed' > "$OUT/functorial-kit-audit.log"
fi

if [[ -s "$OUT/public-pypi-requirements.txt" ]]; then
  run_logged pip-audit "$CANDIDATE" \
    pip-audit -r "$OUT/public-pypi-requirements.txt" --strict \
    --format json --output "$OUT/pip-audit.report.json"
else
  printf '%s\n' 125 > "$OUT/pip-audit.exit.txt"
  printf '%s\n' 'not run because the validated public PyPI projection is missing' > "$OUT/pip-audit.log"
fi

run_logged frontend-audit "$CANDIDATE/main/frontend-modern" \
  pnpm audit --prod --audit-level high --json

printf '%q ' gitleaks git --redact=100 --no-banner --no-color \
  --report-format json --report-path "$OUT/gitleaks.report.json" "$CANDIDATE" \
  > "$OUT/gitleaks.command.txt"
printf '\n' >> "$OUT/gitleaks.command.txt"
gitleaks git --redact=100 --no-banner --no-color \
  --report-format json --report-path "$OUT/gitleaks.report.json" "$CANDIDATE" \
  > "$OUT/gitleaks.log" 2>&1
printf '%s\n' "$?" > "$OUT/gitleaks.exit.txt"

python3 - "$OUT" "$R13N_IMAGE_EVIDENCE" <<'PY'
import hashlib
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
r13n = pathlib.Path(sys.argv[2])

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def exit_code(name):
    path = out / f"{name}.exit.txt"
    return int(path.read_text().strip()) if path.is_file() else None

reuse_files = [
    "result.json",
    "backend-image-inspect.json",
    "backend.sbom.spdx.json",
    "backend.trivy.json",
    "migration-image-inspect.json",
    "migration.sbom.spdx.json",
    "migration.trivy.json",
    "tool-versions.json",
]
payload = {
    "schema": "mrw.stage3.security-evidence.r13o.v1",
    "authoritative": False,
    "candidate": {
        "commit": "3669d4ddc19fb722058976b4e1f05e99eccfe96e",
        "tree": "ce4e4b9ce1b633276192e809fa72007176224e0c",
    },
    "results": {
        name: {
            "exit_code": exit_code(name),
            "command_sha256": sha(out / f"{name}.command.txt"),
            "log_sha256": sha(out / f"{name}.log"),
        }
        for name in ["bandit", "functorial-kit-clone", "functorial-kit-checkout", "functorial-kit-audit", "pip-audit", "frontend-audit", "gitleaks"]
    },
    "reports": {
        path.name: {"sha256": sha(path), "bytes": path.stat().st_size}
        for path in sorted(out.glob("*.report.json")) if path.is_file()
    },
    "reused_r13n_image_evidence": {
        "scope": "backend and migration role inputs only; main/backend and src Git trees are byte-identical between r13n and r13o. This does not rebind the old execution to r13o candidate SHA and does not cover frontend, independent rebuild, signing, registry, or release authority.",
        "source": str(r13n),
        "files": {name: {"sha256": sha(r13n / name)} for name in reuse_files},
    },
    "fixed_git_dependency_limitation": "Public vulnerability databases do not cover the pinned Git commit as a PyPI release; the project checker verifies declaration/source/installed bytes and Bandit, while pip-audit covers the validated public-PyPI projection.",
    "authority_ceiling": "LOCAL_SECURITY_EVIDENCE_NOT_RELEASE_AUTHORITY",
}
payload["status"] = "PASS_LOCAL_SCOPED" if all(
    payload["results"][name]["exit_code"] == 0
    for name in ["bandit", "functorial-kit-audit", "pip-audit", "frontend-audit", "gitleaks"]
) else "FAILED_OR_INCOMPLETE"
(out / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY

find "$OUT" -maxdepth 1 -type f -print0 | sort -z | xargs -0 shasum -a 256 > "$OUT/SHA256SUMS"
