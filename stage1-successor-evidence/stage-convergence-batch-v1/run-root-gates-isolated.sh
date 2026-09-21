#!/usr/bin/env bash
set -u -o pipefail

EXPECTED_IMAGE_SHA256="e40af59580fc6a9dd5ade567618a133027a4b9ab8a8cebc5dc76e779ad766dac"
EXPECTED_PREVIEW_COMMIT="3472d35004d7f50c14fb9fcdfb5ea801dd77f196"
EXPECTED_PREVIEW_TREE="f871c1b5939eb055bed191aceffe238d32694e88"
EXPECTED_MANIFEST_SHA256="1b4f9e5b6e56035da274ed962f2eda6379bd2c930faa1bd6902085fa763a9705"
SOURCE_ROOT="/code"
ARTIFACTS_ROOT="/artifacts"
KIT_REPO="/kit-repo"
MANIFEST_PATH="/admission/candidate-manifest-attempt3.json"

fail() {
  printf 'ROOT_GATES_RUNNER_ERROR:%s\n' "$1" >&2
  exit 2
}

required_env() {
  local name="$1"
  local value="${!name:-}"
  [[ -n "$value" ]] || fail "MISSING_REQUIRED_ENV:${name}"
  printf '%s' "$value"
}

sha256_file() {
  sha256sum "$1" | awk '{print $1}'
}

tracked_bytes_digest() {
  local root="$1"
  ROOT_FOR_DIGEST="$root" "$PYTHON_BIN" - <<'PY'
import hashlib
import os
import stat
import subprocess
from pathlib import Path

root = Path(os.environ["ROOT_FOR_DIGEST"])
required_initialized = {
    "reference-pool/oss/dify": "92bde3503b691b45ee47b1e9f5f7d586f04bd107",
    "reference-pool/oss/n8n": "2e35bb322ea4c885550f2a559f25b118b5189bc8",
    "reference-pool/oss/langflow": "902252ef01905ff5dce4a317004ffe006153c389",
    "reference-pool/oss/outline": "db19a5cf0de31c07a59b9a5bd0770fd54dd286da",
    "reference-pool/oss/silverbullet-ai": "bea4474e74a2a9ad4954f711feb302e24fcdbc2c",
    "reference-pool/oss/agent-cases/langgraph": "46fed9d16156ebdad49806bb65579b7d0756ef3f",
    "reference-pool/oss/temporal": "45617a882c4f403aade3490807b13a759e65a1c7",
}

git_env = {
    **os.environ,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_NO_REPLACE_OBJECTS": "1",
}

def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        (
            "git", "-c", "core.fsmonitor=false", "-c", "core.attributesFile=/dev/null",
            "-c", f"safe.directory={repo}", "-C", str(repo), *args,
        ),
        check=True,
        capture_output=True,
        env=git_env,
    ).stdout

def digest_repo(
    repo: Path,
    expected_head: str | None = None,
    *,
    top_level: bool = False,
) -> tuple[str, int, int]:
    head = git(repo, "rev-parse", "HEAD").decode("ascii").strip()
    if expected_head is not None and head != expected_head:
        raise SystemExit(f"GITLINK_HEAD_MISMATCH:{repo}:{expected_head}:{head}")
    status = git(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise SystemExit(f"GITLINK_NOT_CLEAN:{repo}")
    rows = []
    for item in git(repo, "ls-files", "--stage", "-z").split(b"\0"):
        if not item:
            continue
        metadata, raw_path = item.split(b"\t", 1)
        mode, oid, stage = metadata.decode("ascii").split()
        if stage != "0":
            raise SystemExit(f"UNMERGED_TRACKED_ENTRY:{repo}:{os.fsdecode(raw_path)}")
        rows.append((raw_path, mode, oid))
    rows.sort(key=lambda item: item[0])

    digest = hashlib.sha256()
    gitlink_count = 0
    initialized_count = 0
    seen_required: set[str] = set()
    for raw_path, index_mode, oid in rows:
        relative = os.fsdecode(raw_path)
        path = repo / relative
        if index_mode == "160000":
            if not path.is_dir():
                raise SystemExit(f"GITLINK_DIRECTORY_ABSENT:{path}")
            required_oid = required_initialized.get(relative) if top_level else None
            if required_oid is not None:
                seen_required.add(relative)
                if oid != required_oid:
                    raise SystemExit(f"REQUIRED_GITLINK_INDEX_OID_MISMATCH:{relative}:{required_oid}:{oid}")
                if not (path / ".git").exists():
                    raise SystemExit(f"REQUIRED_GITLINK_NOT_MATERIALIZED:{path}")
                child_digest, child_count, child_initialized = digest_repo(path, oid)
                record = (
                    raw_path + b"\0initialized_gitlink\016000\0" + oid.encode("ascii") + b"\0"
                    + child_digest.encode("ascii") + b"\0"
                )
                initialized_count += 1 + child_initialized
                gitlink_count += 1 + child_count
            elif any(path.iterdir()) or (path / ".git").exists():
                raise SystemExit(f"UNDECLARED_GITLINK_MATERIALIZED_OR_NONEMPTY:{path}")
            else:
                record = raw_path + b"\0uninitialized_gitlink\016000\0" + oid.encode("ascii") + b"\0"
                gitlink_count += 1
        else:
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                kind = "symlink"
                payload = os.readlink(path).encode("utf-8")
            elif stat.S_ISREG(metadata.st_mode):
                kind = "file"
                payload = path.read_bytes()
            else:
                raise SystemExit(f"TRACKED_ENTRY_NOT_FILE_OR_SYMLINK:{path}")
            record = (
                raw_path + b"\0" + kind.encode() + b"\0" + index_mode.encode("ascii") + b"\0"
                + hashlib.sha256(payload).hexdigest().encode("ascii") + b"\0"
            )
        digest.update(record)
    if top_level and seen_required != set(required_initialized):
        missing = sorted(set(required_initialized) - seen_required)
        raise SystemExit(f"REQUIRED_GITLINK_SET_MISSING:{missing}")
    return digest.hexdigest(), gitlink_count, initialized_count

observed_digest, observed_gitlinks, observed_initialized = digest_repo(root, top_level=True)
print(f"{observed_digest} {observed_gitlinks} {observed_initialized}")
PY
}

run_logged() {
  local log_path="$1"
  shift
  "$@" >"$log_path" 2>&1
  return $?
}

RUN_ID="$(required_env MRW_RUN_ID)"
IMAGE_SHA256="$(required_env MRW_IMAGE_ID_SHA256)"
PREVIEW_COMMIT="$(required_env MRW_PREVIEW_COMMIT)"
PREVIEW_TREE="$(required_env MRW_PREVIEW_TREE)"
MANIFEST_SHA256="$(required_env MRW_CANDIDATE_MANIFEST_SHA256)"
PYTHON_BIN="$(required_env MRW_PYTHON_BIN)"

[[ "$RUN_ID" =~ ^[a-zA-Z0-9._-]{8,96}$ ]] || fail "INVALID_RUN_ID:${RUN_ID}"
[[ "$IMAGE_SHA256" == "$EXPECTED_IMAGE_SHA256" ]] || fail "IMAGE_ID_MISMATCH"
[[ "$PREVIEW_COMMIT" == "$EXPECTED_PREVIEW_COMMIT" ]] || fail "PREVIEW_COMMIT_ENV_MISMATCH"
[[ "$PREVIEW_TREE" == "$EXPECTED_PREVIEW_TREE" ]] || fail "PREVIEW_TREE_ENV_MISMATCH"
[[ "$MANIFEST_SHA256" == "$EXPECTED_MANIFEST_SHA256" ]] || fail "MANIFEST_ENV_HASH_MISMATCH"
[[ -x "$PYTHON_BIN" ]] || fail "PYTHON_NOT_EXECUTABLE:${PYTHON_BIN}"
[[ -d "$SOURCE_ROOT/.git" ]] || fail "SOURCE_GIT_METADATA_ABSENT"
[[ -d "$KIT_REPO/.git" ]] || fail "KIT_GIT_METADATA_ABSENT"
[[ -f "$MANIFEST_PATH" ]] || fail "CANDIDATE_MANIFEST_ABSENT"
[[ ! -e "$SOURCE_ROOT/.env" ]] || fail "FORBIDDEN_ENV_FILE:/code/.env"
[[ ! -e "$SOURCE_ROOT/main/backend/.env" ]] || fail "FORBIDDEN_ENV_FILE:/code/main/backend/.env"

for name in \
  OPENAI_API_KEY AZURE_API_KEY LITELLM_API_KEY SERPAPI_KEY SERPER_API_KEY \
  GOOGLE_SEARCH_API_KEY NEWS_API_KEY DATABASE_URL REDIS_URL ES_URL \
  CODEX_AUTH_TOKENS CODEX_OAUTH_CLIENT_SECRET CODEX_OAUTH_ID_TOKEN_SHARED_KEY
do
  [[ -z "${!name:-}" ]] || fail "FORBIDDEN_AMBIENT_INPUT:${name}"
done

OBSERVED_MANIFEST_SHA256="$(sha256_file "$MANIFEST_PATH")"
[[ "$OBSERVED_MANIFEST_SHA256" == "$EXPECTED_MANIFEST_SHA256" ]] || fail "MANIFEST_FILE_HASH_MISMATCH"
"$PYTHON_BIN" - "$MANIFEST_PATH" <<'PY' || fail "MANIFEST_SEMANTIC_ADMISSION_FAILED"
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if value.get("schema_version") != "mrw.stage2.exact-candidate-manifest.v3":
    raise SystemExit("candidate manifest schema mismatch")
if value.get("status") != "EXACT_CANDIDATE_INTAKE_NOT_AUTHORITY":
    raise SystemExit("candidate manifest status mismatch")
if value.get("authoritative") is not False:
    raise SystemExit("candidate manifest expands authority")
if not isinstance(value.get("entries"), list) or not value["entries"]:
    raise SystemExit("candidate manifest has no entries")
PY

GITLINK_DIRECTORIES=(
  "$SOURCE_ROOT/reference-pool/oss/dify"
  "$SOURCE_ROOT/reference-pool/oss/n8n"
  "$SOURCE_ROOT/reference-pool/oss/langflow"
  "$SOURCE_ROOT/reference-pool/oss/outline"
  "$SOURCE_ROOT/reference-pool/oss/silverbullet-ai"
  "$SOURCE_ROOT/reference-pool/oss/agent-cases/langgraph"
  "$SOURCE_ROOT/reference-pool/oss/temporal"
)
SAFE_DIRECTORIES=("$SOURCE_ROOT" "$KIT_REPO" "${GITLINK_DIRECTORIES[@]}")
SAFE_GIT_ENV=(
  env
  GIT_CONFIG_NOSYSTEM=1
  GIT_CONFIG_GLOBAL=/dev/null
  GIT_NO_REPLACE_OBJECTS=1
  "GIT_CONFIG_COUNT=${#SAFE_DIRECTORIES[@]}"
)
for index in "${!SAFE_DIRECTORIES[@]}"; do
  SAFE_GIT_ENV+=("GIT_CONFIG_KEY_${index}=safe.directory")
  SAFE_GIT_ENV+=("GIT_CONFIG_VALUE_${index}=${SAFE_DIRECTORIES[$index]}")
done

OBSERVED_COMMIT="$("${SAFE_GIT_ENV[@]}" git -c core.fsmonitor=false -C "$SOURCE_ROOT" rev-parse HEAD)" || fail "SOURCE_COMMIT_UNREADABLE"
OBSERVED_TREE="$("${SAFE_GIT_ENV[@]}" git -c core.fsmonitor=false -C "$SOURCE_ROOT" rev-parse 'HEAD^{tree}')" || fail "SOURCE_TREE_UNREADABLE"
[[ "$OBSERVED_COMMIT" == "$EXPECTED_PREVIEW_COMMIT" ]] || fail "SOURCE_COMMIT_MISMATCH"
[[ "$OBSERVED_TREE" == "$EXPECTED_PREVIEW_TREE" ]] || fail "SOURCE_TREE_MISMATCH"
SOURCE_STATUS_BEFORE="$("${SAFE_GIT_ENV[@]}" git -c core.fsmonitor=false -C "$SOURCE_ROOT" status --porcelain=v1 --untracked-files=all)" || fail "SOURCE_STATUS_UNREADABLE"
[[ -z "$SOURCE_STATUS_BEFORE" ]] || fail "SOURCE_NOT_CLEAN_BEFORE_TESTS"
read -r SOURCE_TRACKED_BEFORE GITLINK_COUNT_BEFORE INITIALIZED_GITLINK_COUNT_BEFORE \
  <<<"$(tracked_bytes_digest "$SOURCE_ROOT")" || fail "SOURCE_TRACKED_DIGEST_FAILED_BEFORE"

RUN_ROOT="$ARTIFACTS_ROOT/root-gates-${RUN_ID}"
[[ ! -e "$RUN_ROOT" && ! -L "$RUN_ROOT" ]] || fail "RUN_ARTIFACT_ROOT_EXISTS:${RUN_ROOT}"
mkdir "$RUN_ROOT" || fail "RUN_ARTIFACT_ROOT_CREATE_FAILED"
mkdir \
  "$RUN_ROOT/xdg-cache" "$RUN_ROOT/xdg-config" "$RUN_ROOT/xdg-data" \
  "$RUN_ROOT/pytest-cache-architecture" "$RUN_ROOT/pytest-cache-root"
KIT_OUTPUT="$RUN_ROOT/kit"

MATERIALIZER_LOG="$RUN_ROOT/materialize-functorial-kit.log"
run_logged "$MATERIALIZER_LOG" \
  env \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_NO_REPLACE_OBJECTS=1 \
  GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0="$KIT_REPO" \
  "$PYTHON_BIN" "$SOURCE_ROOT/scripts/materialize_functorial_kit_consumer_gate.py" \
  --kit-repo "$KIT_REPO" --output "$KIT_OUTPUT"
MATERIALIZER_EXIT=$?
[[ $MATERIALIZER_EXIT -eq 0 ]] || fail "KIT_MATERIALIZATION_FAILED:${MATERIALIZER_EXIT}"

CHILD_PATH="${PATH:-/usr/local/bin:/usr/bin:/bin}"
CHILD_PYTHONPATH="$KIT_OUTPUT/python:$SOURCE_ROOT/src:$SOURCE_ROOT/main/backend"
COMMON_ENV=(
  env -i
  "PATH=$CHILD_PATH"
  "LANG=C.UTF-8"
  "LC_ALL=C.UTF-8"
  "TZ=UTC"
  "TMPDIR=/tmp"
  "XDG_CACHE_HOME=$RUN_ROOT/xdg-cache"
  "XDG_CONFIG_HOME=$RUN_ROOT/xdg-config"
  "XDG_DATA_HOME=$RUN_ROOT/xdg-data"
  "PYTHONPATH=$CHILD_PYTHONPATH"
  "PYTHONDONTWRITEBYTECODE=1"
  "PYTHONUNBUFFERED=1"
  "GIT_CONFIG_NOSYSTEM=1"
  "GIT_CONFIG_GLOBAL=/dev/null"
  "GIT_NO_REPLACE_OBJECTS=1"
  "DOCKER_CONFIG=$RUN_ROOT/empty-docker-config"
)
mkdir "$RUN_ROOT/empty-docker-config"

COMMON_ENV+=("GIT_CONFIG_COUNT=${#SAFE_DIRECTORIES[@]}")
for index in "${!SAFE_DIRECTORIES[@]}"; do
  COMMON_ENV+=("GIT_CONFIG_KEY_${index}=safe.directory")
  COMMON_ENV+=("GIT_CONFIG_VALUE_${index}=${SAFE_DIRECTORIES[$index]}")
done

ARCH_JUNIT="$RUN_ROOT/architecture-gates.junit.xml"
ARCH_LOG="$RUN_ROOT/architecture-gates.log"
run_logged "$ARCH_LOG" \
  "${COMMON_ENV[@]}" "$PYTHON_BIN" -m pytest \
  tests/test_architecture.py -q -ra \
  --junitxml="$ARCH_JUNIT" -o "cache_dir=$RUN_ROOT/pytest-cache-architecture"
ARCH_EXIT=$?

DELTA_LOG="$RUN_ROOT/architecture-baseline-delta.json"
run_logged "$DELTA_LOG" \
  "${COMMON_ENV[@]}" "$PYTHON_BIN" scripts/check_architecture_baseline_delta.py --root "$SOURCE_ROOT"
DELTA_EXIT=$?

ROOT_JUNIT="$RUN_ROOT/root-tests.junit.xml"
ROOT_LOG="$RUN_ROOT/root-tests.log"
run_logged "$ROOT_LOG" \
  "${COMMON_ENV[@]}" "$PYTHON_BIN" -m pytest \
  tests -q -ra \
  --junitxml="$ROOT_JUNIT" -o "cache_dir=$RUN_ROOT/pytest-cache-root"
ROOT_EXIT=$?

SOURCE_STATUS_AFTER="$("${SAFE_GIT_ENV[@]}" git -c core.fsmonitor=false -C "$SOURCE_ROOT" status --porcelain=v1 --untracked-files=all)" || fail "SOURCE_STATUS_UNREADABLE_AFTER"
read -r SOURCE_TRACKED_AFTER GITLINK_COUNT_AFTER INITIALIZED_GITLINK_COUNT_AFTER \
  <<<"$(tracked_bytes_digest "$SOURCE_ROOT")" || fail "SOURCE_TRACKED_DIGEST_FAILED_AFTER"
[[ "$SOURCE_STATUS_AFTER" == "$SOURCE_STATUS_BEFORE" ]] || fail "SOURCE_STATUS_CHANGED_BY_TESTS"
[[ "$SOURCE_TRACKED_AFTER" == "$SOURCE_TRACKED_BEFORE" ]] || fail "SOURCE_TRACKED_BYTES_CHANGED_BY_TESTS"
[[ "$GITLINK_COUNT_AFTER" == "$GITLINK_COUNT_BEFORE" ]] || fail "SOURCE_GITLINK_COUNT_CHANGED_BY_TESTS"
[[ "$INITIALIZED_GITLINK_COUNT_AFTER" == "$INITIALIZED_GITLINK_COUNT_BEFORE" ]] || fail "INITIALIZED_GITLINK_COUNT_CHANGED_BY_TESTS"

export RUN_ROOT EXPECTED_IMAGE_SHA256 EXPECTED_PREVIEW_COMMIT EXPECTED_PREVIEW_TREE
export EXPECTED_MANIFEST_SHA256 SOURCE_TRACKED_BEFORE SOURCE_TRACKED_AFTER
export GITLINK_COUNT_BEFORE GITLINK_COUNT_AFTER
export INITIALIZED_GITLINK_COUNT_BEFORE INITIALIZED_GITLINK_COUNT_AFTER
export MATERIALIZER_EXIT ARCH_EXIT DELTA_EXIT ROOT_EXIT ARCH_JUNIT ROOT_JUNIT
"$PYTHON_BIN" - <<'PY'
import hashlib
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

root = Path(os.environ["RUN_ROOT"])

def digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def junit(path: Path) -> dict[str, int | str | None]:
    result: dict[str, int | str | None] = {"path": str(path), "sha256": digest(path)}
    if not path.is_file():
        result.update({"tests": 0, "failures": 0, "errors": 0, "skipped": 0})
        return result
    document = ET.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
    for field in ("tests", "failures", "errors", "skipped"):
        result[field] = sum(int(suite.attrib.get(field, "0")) for suite in suites)
    return result

exits = {
    "kit_materialization": int(os.environ["MATERIALIZER_EXIT"]),
    "architecture_gates": int(os.environ["ARCH_EXIT"]),
    "architecture_baseline_delta": int(os.environ["DELTA_EXIT"]),
    "root_tests": int(os.environ["ROOT_EXIT"]),
}
receipt = {
    "schema": "mrw.stage1.root-gates-run.v1",
    "status": "PASS" if all(value == 0 for value in exits.values()) else "FAIL",
    "authoritative": False,
    "authority": {
        "candidate_promotion": False,
        "production_release": False,
        "deployment": False,
        "cutover": False,
        "live_provider": False,
        "external_delivery": False,
    },
    "image_sha256": os.environ["EXPECTED_IMAGE_SHA256"],
    "preview": {
        "commit": os.environ["EXPECTED_PREVIEW_COMMIT"],
        "tree": os.environ["EXPECTED_PREVIEW_TREE"],
        "candidate_manifest_sha256": os.environ["EXPECTED_MANIFEST_SHA256"],
    },
    "isolation": {
        "network": "none",
        "source_mount": "read_only",
        "docker_socket_mounted": False,
        "host_ports_published": False,
        "credentials_supplied": False,
        "services_started": False,
    },
    "commands": {
        "architecture_gates": "python -m pytest tests/test_architecture.py -q -ra --junitxml=...",
        "architecture_baseline_delta": "python scripts/check_architecture_baseline_delta.py --root /code",
        "root_tests": "python -m pytest tests -q -ra --junitxml=...",
    },
    "exit_codes": exits,
    "junit": {
        "architecture": junit(Path(os.environ["ARCH_JUNIT"])),
        "root": junit(Path(os.environ["ROOT_JUNIT"])),
    },
    "logs": {
        name: {"path": str(path), "sha256": digest(path)}
        for name, path in {
            "materializer": root / "materialize-functorial-kit.log",
            "architecture": root / "architecture-gates.log",
            "architecture_baseline_delta": root / "architecture-baseline-delta.json",
            "root": root / "root-tests.log",
        }.items()
    },
    "source_integrity": {
        "tracked_bytes_before_sha256": os.environ["SOURCE_TRACKED_BEFORE"],
        "tracked_bytes_after_sha256": os.environ["SOURCE_TRACKED_AFTER"],
        "unchanged": os.environ["SOURCE_TRACKED_BEFORE"] == os.environ["SOURCE_TRACKED_AFTER"],
        "gitlink_count_before": int(os.environ["GITLINK_COUNT_BEFORE"]),
        "gitlink_count_after": int(os.environ["GITLINK_COUNT_AFTER"]),
        "initialized_gitlink_count_before": int(os.environ["INITIALIZED_GITLINK_COUNT_BEFORE"]),
        "initialized_gitlink_count_after": int(os.environ["INITIALIZED_GITLINK_COUNT_AFTER"]),
        "uninitialized_gitlink_count": int(os.environ["GITLINK_COUNT_BEFORE"]) - int(os.environ["INITIALIZED_GITLINK_COUNT_BEFORE"]),
        "git_status_before": "",
        "git_status_after": "",
    },
    "limits": [
        "Root tests do not include the separate main/backend test tree.",
        "No baseline write, candidate mutation, service connection, candidate promotion, or production authority is granted.",
    ],
}
path = root / "root-gates-receipt.v1.json"
with path.open("x", encoding="utf-8") as stream:
    json.dump(receipt, stream, ensure_ascii=True, indent=2, sort_keys=True)
    stream.write("\n")
print(json.dumps({"receipt": str(path), "status": receipt["status"], "exit_codes": exits}, sort_keys=True))
raise SystemExit(0 if receipt["status"] == "PASS" else 1)
PY
