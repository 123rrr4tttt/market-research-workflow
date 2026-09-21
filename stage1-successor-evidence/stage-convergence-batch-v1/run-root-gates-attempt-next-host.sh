#!/usr/bin/env bash
set -u -o pipefail

DOCKER_CONTEXT="default"
TARGET_PLATFORM="linux/amd64"
CONTAINER_CREATED=0
CONTAINER_NAME=""
HOST_RUN_ROOT=""

cleanup_created_container_on_exit() {
  local status=$?
  trap - EXIT
  if [[ $status -ne 0 && "$CONTAINER_CREATED" == 1 && -n "$CONTAINER_NAME" ]]; then
    if [[ -n "$HOST_RUN_ROOT" && -d "$HOST_RUN_ROOT" ]]; then
      docker --context "$DOCKER_CONTEXT" container inspect "$CONTAINER_NAME" > "$HOST_RUN_ROOT/container-abort.inspect.json" 2> "$HOST_RUN_ROOT/container-abort.inspect.stderr" || true
      docker --context "$DOCKER_CONTEXT" rm -f "$CONTAINER_NAME" > "$HOST_RUN_ROOT/container-abort-remove.stdout" 2> "$HOST_RUN_ROOT/container-abort-remove.stderr" || true
    else
      docker --context "$DOCKER_CONTEXT" rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    fi
  fi
  exit "$status"
}
trap cleanup_created_container_on_exit EXIT

usage() {
  cat <<'EOF'
usage: run-root-gates-attempt-next-host.sh \
  --run-id ID \
  --preview /absolute/path \
  --manifest /absolute/path.json \
  --preview-commit HEX40 \
  --preview-tree HEX40 \
  --manifest-sha256 HEX64 \
  --image-tag REPOSITORY:TAG \
  --image-id sha256:HEX64 \
  --kit-repo /absolute/path \
  --artifacts-root /absolute/existing/directory

Creates one isolated Linux/amd64 container with a read-only candidate source,
no network, no Docker socket, and create-only evidence beneath artifacts-root.
There are no candidate identity defaults.
EOF
}

fail() {
  printf 'ROOT_GATES_NEXT_HOST_ERROR:%s\n' "$1" >&2
  exit 2
}

require_option_value() {
  local option="$1"
  local value="${2:-}"
  [[ -n "$value" && "$value" != --* ]] || fail "MISSING_OPTION_VALUE:${option}"
}

RUN_ID=""
PREVIEW=""
MANIFEST=""
PREVIEW_COMMIT=""
PREVIEW_TREE=""
MANIFEST_SHA256=""
IMAGE_TAG=""
IMAGE_ID=""
KIT_REPO=""
ARTIFACTS_ROOT=""

while (($#)); do
  case "$1" in
    --run-id)
      require_option_value "$1" "${2:-}"
      RUN_ID="$2"
      shift 2
      ;;
    --preview)
      require_option_value "$1" "${2:-}"
      PREVIEW="$2"
      shift 2
      ;;
    --manifest)
      require_option_value "$1" "${2:-}"
      MANIFEST="$2"
      shift 2
      ;;
    --preview-commit)
      require_option_value "$1" "${2:-}"
      PREVIEW_COMMIT="$2"
      shift 2
      ;;
    --preview-tree)
      require_option_value "$1" "${2:-}"
      PREVIEW_TREE="$2"
      shift 2
      ;;
    --manifest-sha256)
      require_option_value "$1" "${2:-}"
      MANIFEST_SHA256="$2"
      shift 2
      ;;
    --image-tag)
      require_option_value "$1" "${2:-}"
      IMAGE_TAG="$2"
      shift 2
      ;;
    --image-id)
      require_option_value "$1" "${2:-}"
      IMAGE_ID="$2"
      shift 2
      ;;
    --kit-repo)
      require_option_value "$1" "${2:-}"
      KIT_REPO="$2"
      shift 2
      ;;
    --artifacts-root)
      require_option_value "$1" "${2:-}"
      ARTIFACTS_ROOT="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --*)
      fail "UNKNOWN_OPTION:$1"
      ;;
    *)
      fail "UNEXPECTED_POSITIONAL:$1"
      ;;
  esac
done

for pair in \
  "--run-id:$RUN_ID" \
  "--preview:$PREVIEW" \
  "--manifest:$MANIFEST" \
  "--preview-commit:$PREVIEW_COMMIT" \
  "--preview-tree:$PREVIEW_TREE" \
  "--manifest-sha256:$MANIFEST_SHA256" \
  "--image-tag:$IMAGE_TAG" \
  "--image-id:$IMAGE_ID" \
  "--kit-repo:$KIT_REPO" \
  "--artifacts-root:$ARTIFACTS_ROOT"
do
  option="${pair%%:*}"
  value="${pair#*:}"
  [[ -n "$value" ]] || fail "MISSING_REQUIRED_OPTION:${option}"
done

[[ "$RUN_ID" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]{7,63}$ ]] || fail "INVALID_RUN_ID:${RUN_ID}"
[[ "$PREVIEW_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail "INVALID_PREVIEW_COMMIT"
[[ "$PREVIEW_TREE" =~ ^[0-9a-f]{40}$ ]] || fail "INVALID_PREVIEW_TREE"
[[ "$MANIFEST_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail "INVALID_MANIFEST_SHA256"
[[ "$IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "INVALID_IMAGE_ID"
[[ "$IMAGE_TAG" =~ ^[a-zA-Z0-9._/-]+:[a-zA-Z0-9._-]+$ ]] || fail "INVALID_IMAGE_TAG"

for path in "$PREVIEW" "$MANIFEST" "$KIT_REPO" "$ARTIFACTS_ROOT"; do
  [[ "$path" == /* ]] || fail "PATH_NOT_ABSOLUTE:${path}"
  [[ "$path" != *','* && "$path" != *$'\n'* ]] || fail "UNSAFE_MOUNT_PATH:${path}"
done
[[ -d "$PREVIEW/.git" ]] || fail "PREVIEW_GIT_METADATA_ABSENT:${PREVIEW}"
[[ -f "$MANIFEST" ]] || fail "MANIFEST_ABSENT:${MANIFEST}"
[[ -d "$KIT_REPO/.git" ]] || fail "KIT_GIT_METADATA_ABSENT:${KIT_REPO}"
[[ -d "$ARTIFACTS_ROOT" ]] || fail "ARTIFACTS_ROOT_ABSENT:${ARTIFACTS_ROOT}"

PREVIEW="$(cd "$PREVIEW" && pwd -P)" || fail "PREVIEW_CANONICALIZATION_FAILED"
MANIFEST_DIR="$(cd "$(dirname "$MANIFEST")" && pwd -P)" || fail "MANIFEST_CANONICALIZATION_FAILED"
MANIFEST="$MANIFEST_DIR/$(basename "$MANIFEST")"
KIT_REPO="$(cd "$KIT_REPO" && pwd -P)" || fail "KIT_REPO_CANONICALIZATION_FAILED"
ARTIFACTS_ROOT="$(cd "$ARTIFACTS_ROOT" && pwd -P)" || fail "ARTIFACTS_ROOT_CANONICALIZATION_FAILED"
case "$ARTIFACTS_ROOT/" in
  "$PREVIEW/"*) fail "ARTIFACTS_ROOT_INSIDE_PREVIEW" ;;
esac
case "$PREVIEW/" in
  "$ARTIFACTS_ROOT/"*) fail "PREVIEW_INSIDE_ARTIFACTS_ROOT" ;;
esac
case "$ARTIFACTS_ROOT/" in
  "$KIT_REPO/"*) fail "ARTIFACTS_ROOT_INSIDE_KIT_REPO" ;;
esac
case "$KIT_REPO/" in
  "$ARTIFACTS_ROOT/"*) fail "KIT_REPO_INSIDE_ARTIFACTS_ROOT" ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)" || fail "SCRIPT_DIR_UNREADABLE"
RUNNER_PATH="$SCRIPT_DIR/run-root-gates-attempt-next.sh"
[[ -f "$RUNNER_PATH" ]] || fail "INNER_RUNNER_ABSENT:${RUNNER_PATH}"

SAFE_GIT_ENV=(env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_NO_REPLACE_OBJECTS=1)
OBSERVED_COMMIT="$("${SAFE_GIT_ENV[@]}" git -c core.fsmonitor=false -c "safe.directory=$PREVIEW" -C "$PREVIEW" rev-parse HEAD)" || fail "PREVIEW_COMMIT_UNREADABLE"
OBSERVED_TREE="$("${SAFE_GIT_ENV[@]}" git -c core.fsmonitor=false -c "safe.directory=$PREVIEW" -C "$PREVIEW" rev-parse 'HEAD^{tree}')" || fail "PREVIEW_TREE_UNREADABLE"
OBSERVED_STATUS="$("${SAFE_GIT_ENV[@]}" git -c core.fsmonitor=false -c "safe.directory=$PREVIEW" -C "$PREVIEW" status --porcelain=v1 --untracked-files=all)" || fail "PREVIEW_STATUS_UNREADABLE"
[[ "$OBSERVED_COMMIT" == "$PREVIEW_COMMIT" ]] || fail "PREVIEW_COMMIT_MISMATCH"
[[ "$OBSERVED_TREE" == "$PREVIEW_TREE" ]] || fail "PREVIEW_TREE_MISMATCH"
[[ -z "$OBSERVED_STATUS" ]] || fail "PREVIEW_NOT_CLEAN"
OBSERVED_MANIFEST_SHA256="$(sha256sum "$MANIFEST" | awk '{print $1}')" || fail "MANIFEST_HASH_UNREADABLE"
[[ "$OBSERVED_MANIFEST_SHA256" == "$MANIFEST_SHA256" ]] || fail "MANIFEST_SHA256_MISMATCH"

CONTAINER_NAME="mrw-root-gates-${RUN_ID}"
if docker --context "$DOCKER_CONTEXT" container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  fail "CONTAINER_ALREADY_EXISTS:${CONTAINER_NAME}"
fi

HOST_RUN_ROOT="$ARTIFACTS_ROOT/root-gates-host-${RUN_ID}"
[[ ! -e "$HOST_RUN_ROOT" && ! -L "$HOST_RUN_ROOT" ]] || fail "HOST_RUN_ROOT_EXISTS:${HOST_RUN_ROOT}"
mkdir "$HOST_RUN_ROOT" || fail "HOST_RUN_ROOT_CREATE_FAILED"

docker --context "$DOCKER_CONTEXT" image inspect "$IMAGE_TAG" > "$HOST_RUN_ROOT/tag-pre.inspect.json" || fail "IMAGE_TAG_PRE_INSPECT_FAILED"
TAG_PRE_ID="$(jq -r '.[0].Id' "$HOST_RUN_ROOT/tag-pre.inspect.json")"
TAG_PRE_OS="$(jq -r '.[0].Os' "$HOST_RUN_ROOT/tag-pre.inspect.json")"
TAG_PRE_ARCH="$(jq -r '.[0].Architecture' "$HOST_RUN_ROOT/tag-pre.inspect.json")"
[[ "$TAG_PRE_ID" == "$IMAGE_ID" ]] || fail "IMAGE_TAG_PRE_ID_MISMATCH"
[[ "$TAG_PRE_OS/$TAG_PRE_ARCH" == "$TARGET_PLATFORM" ]] || fail "IMAGE_PLATFORM_MISMATCH:${TAG_PRE_OS}/${TAG_PRE_ARCH}"

RUNNER_SHA256="$(sha256sum "$RUNNER_PATH" | awk '{print $1}')"
printf '%s\n' "$RUNNER_SHA256" > "$HOST_RUN_ROOT/inner-runner.sha256"

docker --context "$DOCKER_CONTEXT" create \
  --pull never \
  --platform "$TARGET_PLATFORM" \
  --network none \
  --read-only \
  --restart no \
  --cap-drop ALL \
  --security-opt no-new-privileges=true \
  --tmpfs /tmp:rw,nosuid,nodev \
  --tmpfs /private/tmp:rw,nosuid,nodev \
  --name "$CONTAINER_NAME" \
  --mount "type=bind,src=$PREVIEW,dst=/code,readonly" \
  --mount "type=bind,src=$HOST_RUN_ROOT,dst=/artifacts" \
  --mount "type=bind,src=$KIT_REPO,dst=/kit-repo,readonly" \
  --mount "type=bind,src=$MANIFEST,dst=/admission/candidate-manifest.json,readonly" \
  --mount "type=bind,src=$RUNNER_PATH,dst=/runner/run-root-gates-attempt-next.sh,readonly" \
  --workdir /code \
  --entrypoint /bin/bash \
  "$IMAGE_TAG" \
  /runner/run-root-gates-attempt-next.sh \
  --run-id "$RUN_ID" \
  --expected-image-id "$IMAGE_ID" \
  --expected-preview-commit "$PREVIEW_COMMIT" \
  --expected-preview-tree "$PREVIEW_TREE" \
  --expected-manifest-sha256 "$MANIFEST_SHA256" \
  > "$HOST_RUN_ROOT/container-create.stdout" \
  2> "$HOST_RUN_ROOT/container-create.stderr"
CREATE_EXIT=$?
[[ $CREATE_EXIT -eq 0 ]] || fail "CONTAINER_CREATE_FAILED:${CREATE_EXIT}"
CONTAINER_CREATED=1

docker --context "$DOCKER_CONTEXT" container inspect "$CONTAINER_NAME" > "$HOST_RUN_ROOT/container-pre.inspect.json" || fail "CONTAINER_PRE_INSPECT_FAILED"
CONTAINER_PRE_IMAGE_ID="$(jq -r '.[0].Image' "$HOST_RUN_ROOT/container-pre.inspect.json")"
CONTAINER_PRE_CONFIG_IMAGE="$(jq -r '.[0].Config.Image' "$HOST_RUN_ROOT/container-pre.inspect.json")"
CONTAINER_PRE_NETWORK="$(jq -r '.[0].HostConfig.NetworkMode' "$HOST_RUN_ROOT/container-pre.inspect.json")"
CONTAINER_PRE_BIND_MOUNTS="$(jq -r '[.[0].Mounts[] | select(.Type == "bind")] | length' "$HOST_RUN_ROOT/container-pre.inspect.json")"
CONTAINER_PRE_BIND_DESTINATIONS="$(jq -c '[.[0].Mounts[] | select(.Type == "bind") | .Destination] | sort' "$HOST_RUN_ROOT/container-pre.inspect.json")"
CONTAINER_PRE_RW_SOURCE="$(jq -r '[.[0].Mounts[] | select(.Destination == "/code") | .RW][0]' "$HOST_RUN_ROOT/container-pre.inspect.json")"
CONTAINER_PRE_RO_INPUTS="$(jq -r '[.[0].Mounts[] | select(.Destination == "/code" or .Destination == "/kit-repo" or .Destination == "/admission/candidate-manifest.json" or .Destination == "/runner/run-root-gates-attempt-next.sh") | (.RW == false)] | all' "$HOST_RUN_ROOT/container-pre.inspect.json")"
CONTAINER_PRE_RW_ARTIFACTS="$(jq -r '[.[0].Mounts[] | select(.Destination == "/artifacts") | .RW][0]' "$HOST_RUN_ROOT/container-pre.inspect.json")"
CONTAINER_PRE_SOCKET_MOUNTS="$(jq -r '[.[0].Mounts[] | select(.Destination == "/var/run/docker.sock" or .Source == "/var/run/docker.sock")] | length' "$HOST_RUN_ROOT/container-pre.inspect.json")"
CONTAINER_PRE_WORKDIR="$(jq -r '.[0].Config.WorkingDir' "$HOST_RUN_ROOT/container-pre.inspect.json")"
[[ "$CONTAINER_PRE_IMAGE_ID" == "$IMAGE_ID" ]] || fail "CONTAINER_PRE_IMAGE_ID_MISMATCH"
[[ "$CONTAINER_PRE_CONFIG_IMAGE" == "$IMAGE_TAG" ]] || fail "CONTAINER_PRE_TAG_MISMATCH"
[[ "$CONTAINER_PRE_NETWORK" == "none" ]] || fail "CONTAINER_NETWORK_NOT_NONE"
[[ "$CONTAINER_PRE_BIND_MOUNTS" == 5 ]] || fail "CONTAINER_BIND_MOUNT_COUNT_MISMATCH:${CONTAINER_PRE_BIND_MOUNTS}"
[[ "$CONTAINER_PRE_BIND_DESTINATIONS" == '["/admission/candidate-manifest.json","/artifacts","/code","/kit-repo","/runner/run-root-gates-attempt-next.sh"]' ]] || fail "CONTAINER_BIND_DESTINATIONS_MISMATCH"
[[ "$CONTAINER_PRE_RW_SOURCE" == "false" ]] || fail "SOURCE_MOUNT_NOT_READ_ONLY"
[[ "$CONTAINER_PRE_RO_INPUTS" == "true" ]] || fail "INPUT_MOUNT_NOT_READ_ONLY"
[[ "$CONTAINER_PRE_RW_ARTIFACTS" == "true" ]] || fail "ARTIFACTS_MOUNT_NOT_WRITABLE"
[[ "$CONTAINER_PRE_SOCKET_MOUNTS" == 0 ]] || fail "DOCKER_SOCKET_MOUNT_PRESENT"
[[ "$CONTAINER_PRE_WORKDIR" == "/code" ]] || fail "CONTAINER_WORKDIR_MISMATCH:${CONTAINER_PRE_WORKDIR}"
[[ "$(jq -r '.[0].HostConfig.ReadonlyRootfs' "$HOST_RUN_ROOT/container-pre.inspect.json")" == "true" ]] || fail "ROOT_FILESYSTEM_NOT_READ_ONLY"
[[ "$(jq -r '.[0].HostConfig.Privileged' "$HOST_RUN_ROOT/container-pre.inspect.json")" == "false" ]] || fail "CONTAINER_PRIVILEGED"
[[ "$(jq -c '.[0].HostConfig.CapDrop' "$HOST_RUN_ROOT/container-pre.inspect.json")" == '["ALL"]' ]] || fail "CAP_DROP_CONTRACT_MISMATCH"
[[ "$(jq -r '.[0].HostConfig.SecurityOpt | index("no-new-privileges=true") != null' "$HOST_RUN_ROOT/container-pre.inspect.json")" == "true" ]] || fail "NO_NEW_PRIVILEGES_ABSENT"

START_EPOCH="$(date +%s)"
START_COMMAND_EXIT=0
TIMEOUT_REASON=""
docker --context "$DOCKER_CONTEXT" start "$CONTAINER_NAME" \
  > "$HOST_RUN_ROOT/container-start.stdout" \
  2> "$HOST_RUN_ROOT/container-start.stderr" &
START_COMMAND_PID=$!

while true; do
  STATE_LINE="$(docker --context "$DOCKER_CONTEXT" container inspect "$CONTAINER_NAME" --format '{{.State.Status}} {{.State.Pid}} {{.State.ExitCode}}' 2>> "$HOST_RUN_ROOT/container-monitor.stderr")" || {
    TIMEOUT_REASON="CONTAINER_STATE_UNREADABLE"
    break
  }
  read -r CURRENT_STATUS CURRENT_PID CURRENT_EXIT <<<"$STATE_LINE"
  NOW_EPOCH="$(date +%s)"
  ELAPSED=$((NOW_EPOCH - START_EPOCH))
  printf '%s status=%s pid=%s exit=%s elapsed=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$CURRENT_STATUS" "$CURRENT_PID" "$CURRENT_EXIT" "$ELAPSED" >> "$HOST_RUN_ROOT/container-monitor.log"
  if [[ "$CURRENT_STATUS" == "exited" || "$CURRENT_STATUS" == "dead" ]]; then
    break
  fi
  if [[ "$CURRENT_STATUS" == "created" && "$CURRENT_PID" == 0 && $ELAPSED -ge 60 ]]; then
    TIMEOUT_REASON="CREATED_PID0_OVER_60_SECONDS"
    docker --context "$DOCKER_CONTEXT" stop --time 10 "$CONTAINER_NAME" > "$HOST_RUN_ROOT/container-timeout-stop.stdout" 2> "$HOST_RUN_ROOT/container-timeout-stop.stderr" || true
    break
  fi
  if [[ $ELAPSED -ge 900 ]]; then
    TIMEOUT_REASON="OVERALL_RUNTIME_OVER_900_SECONDS"
    docker --context "$DOCKER_CONTEXT" stop --time 10 "$CONTAINER_NAME" > "$HOST_RUN_ROOT/container-timeout-stop.stdout" 2> "$HOST_RUN_ROOT/container-timeout-stop.stderr" || true
    break
  fi
  sleep 2
done

if kill -0 "$START_COMMAND_PID" >/dev/null 2>&1; then
  kill "$START_COMMAND_PID" >/dev/null 2>&1 || true
fi
wait "$START_COMMAND_PID" || START_COMMAND_EXIT=$?
docker --context "$DOCKER_CONTEXT" logs "$CONTAINER_NAME" > "$HOST_RUN_ROOT/container-run.log" 2> "$HOST_RUN_ROOT/container-run.stderr" || true

docker --context "$DOCKER_CONTEXT" container inspect "$CONTAINER_NAME" > "$HOST_RUN_ROOT/container-post.inspect.json"
POST_INSPECT_EXIT=$?
docker --context "$DOCKER_CONTEXT" image inspect "$IMAGE_TAG" > "$HOST_RUN_ROOT/tag-post.inspect.json"
TAG_POST_INSPECT_EXIT=$?
[[ $POST_INSPECT_EXIT -eq 0 ]] || fail "CONTAINER_POST_INSPECT_FAILED:${POST_INSPECT_EXIT}"
[[ $TAG_POST_INSPECT_EXIT -eq 0 ]] || fail "IMAGE_TAG_POST_INSPECT_FAILED:${TAG_POST_INSPECT_EXIT}"

CONTAINER_POST_IMAGE_ID="$(jq -r '.[0].Image' "$HOST_RUN_ROOT/container-post.inspect.json")"
CONTAINER_EXIT_CODE="$(jq -r '.[0].State.ExitCode' "$HOST_RUN_ROOT/container-post.inspect.json")"
CONTAINER_POST_STATUS="$(jq -r '.[0].State.Status' "$HOST_RUN_ROOT/container-post.inspect.json")"
TAG_POST_ID="$(jq -r '.[0].Id' "$HOST_RUN_ROOT/tag-post.inspect.json")"
BINDING_STATUS="PASS"
[[ "$CONTAINER_POST_IMAGE_ID" == "$IMAGE_ID" ]] || BINDING_STATUS="FAIL"
[[ "$TAG_POST_ID" == "$IMAGE_ID" ]] || BINDING_STATUS="FAIL"
if [[ -n "$TIMEOUT_REASON" ]]; then
  RUNNER_EXIT=124
elif [[ "$CONTAINER_POST_STATUS" == "exited" ]]; then
  RUNNER_EXIT="$CONTAINER_EXIT_CODE"
else
  RUNNER_EXIT=125
fi

docker --context "$DOCKER_CONTEXT" rm "$CONTAINER_NAME" > "$HOST_RUN_ROOT/container-remove.stdout" 2> "$HOST_RUN_ROOT/container-remove.stderr"
REMOVE_EXIT=$?
if [[ $REMOVE_EXIT -eq 0 ]]; then
  CONTAINER_CREATED=0
fi

export HOST_RUN_ROOT RUN_ID PREVIEW MANIFEST PREVIEW_COMMIT PREVIEW_TREE MANIFEST_SHA256
export IMAGE_TAG IMAGE_ID TARGET_PLATFORM RUNNER_PATH RUNNER_SHA256
export TAG_PRE_ID TAG_POST_ID CONTAINER_PRE_IMAGE_ID CONTAINER_POST_IMAGE_ID
export CONTAINER_NAME CONTAINER_EXIT_CODE CONTAINER_POST_STATUS RUNNER_EXIT BINDING_STATUS REMOVE_EXIT
export START_COMMAND_EXIT TIMEOUT_REASON
python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["HOST_RUN_ROOT"])

def digest(name: str) -> str | None:
    path = root / name
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

binding_ids = {
    "tag_pre": os.environ["TAG_PRE_ID"],
    "container_pre": os.environ["CONTAINER_PRE_IMAGE_ID"],
    "container_post": os.environ["CONTAINER_POST_IMAGE_ID"],
    "tag_post": os.environ["TAG_POST_ID"],
}
runner_exit = int(os.environ["RUNNER_EXIT"])
remove_exit = int(os.environ["REMOVE_EXIT"])
status = "PASS" if runner_exit == 0 and remove_exit == 0 and os.environ["BINDING_STATUS"] == "PASS" else "FAIL"
receipt = {
    "schema": "mrw.stage1.root-gates-next-host-run.v1",
    "status": status,
    "authoritative": False,
    "run_id": os.environ["RUN_ID"],
    "inputs": {
        "preview": os.environ["PREVIEW"],
        "manifest": os.environ["MANIFEST"],
        "preview_commit": os.environ["PREVIEW_COMMIT"],
        "preview_tree": os.environ["PREVIEW_TREE"],
        "manifest_sha256": os.environ["MANIFEST_SHA256"],
        "image_tag": os.environ["IMAGE_TAG"],
        "image_id": os.environ["IMAGE_ID"],
        "platform": os.environ["TARGET_PLATFORM"],
        "inner_runner": os.environ["RUNNER_PATH"],
        "inner_runner_sha256": os.environ["RUNNER_SHA256"],
    },
    "image_binding": {
        **binding_ids,
        "all_equal_expected": all(value == os.environ["IMAGE_ID"] for value in binding_ids.values()),
    },
    "container": {
        "name": os.environ["CONTAINER_NAME"],
        "runner_exit": runner_exit,
        "reported_exit_code": int(os.environ["CONTAINER_EXIT_CODE"]),
        "post_status": os.environ["CONTAINER_POST_STATUS"],
        "start_command_exit": int(os.environ["START_COMMAND_EXIT"]),
        "timeout_reason": os.environ["TIMEOUT_REASON"] or None,
        "created_pid0_timeout_seconds": 60,
        "overall_timeout_seconds": 900,
        "remove_exit": remove_exit,
        "removed": remove_exit == 0,
    },
    "isolation": {
        "pull_policy": "never",
        "network": "none",
        "root_filesystem": "read_only",
        "source_mount": "read_only",
        "capabilities": "all_dropped",
        "no_new_privileges": True,
        "docker_socket_mounted": False,
        "host_docker_config_mounted": False,
        "home_rewritten": False,
        "host_ports": [],
    },
    "evidence": {
        name: digest(name)
        for name in (
            "tag-pre.inspect.json",
            "container-create.stdout",
            "container-create.stderr",
            "container-pre.inspect.json",
            "container-start.stdout",
            "container-start.stderr",
            "container-monitor.log",
            "container-monitor.stderr",
            "container-run.log",
            "container-run.stderr",
            "container-post.inspect.json",
            "tag-post.inspect.json",
            "container-remove.stdout",
            "container-remove.stderr",
        )
    },
    "authority": {
        "candidate_promotion": False,
        "production_release": False,
        "deployment": False,
        "cutover": False,
        "live_provider": False,
        "external_delivery": False,
    },
}
path = root / "host-controller-receipt.v1.json"
with path.open("x", encoding="utf-8") as stream:
    json.dump(receipt, stream, ensure_ascii=True, indent=2, sort_keys=True)
    stream.write("\n")
print(json.dumps({"receipt": str(path), "status": status, "runner_exit": runner_exit}, sort_keys=True))
raise SystemExit(0 if status == "PASS" else 1)
PY
RECEIPT_EXIT=$?
[[ $RECEIPT_EXIT -eq 0 ]] || exit 1
exit 0
