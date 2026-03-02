#!/usr/bin/env bash
set -euo pipefail

# Run swarm bootstrap for multiple files with bounded concurrency and retries.

JOBS=4
RETRIES=1
LIST_FILE=""
TARGETS=()

usage() {
  cat <<'EOF'
usage: bash ./codex_settings/scripts/swarm.sh [options] <file1> [file2 ...]

options:
  -j, --jobs <n>        max parallel jobs (default: 4)
  -r, --retries <n>     retry count for each failed file (default: 1)
  -l, --list <file>     read file paths from a text file (one path per line)
  -h, --help            show this help

examples:
  bash ./codex_settings/scripts/swarm.sh -j 6 main/backend/app/api/crawler.py main/backend/app/services/crawlers_mgmt/service.py
  bash ./codex_settings/scripts/swarm.sh -j 4 -r 2 -l codex_settings/swarm_targets.txt
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -j|--jobs)
      JOBS="${2:-}"
      shift 2
      ;;
    -r|--retries)
      RETRIES="${2:-}"
      shift 2
      ;;
    -l|--list)
      LIST_FILE="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      while [[ $# -gt 0 ]]; do
        TARGETS+=("$1")
        shift
      done
      ;;
    -*)
      echo "[ERROR] unknown option: $1"
      usage
      exit 2
      ;;
    *)
      TARGETS+=("$1")
      shift
      ;;
  esac
done

if ! [[ "$JOBS" =~ ^[0-9]+$ ]] || [[ "$JOBS" -lt 1 ]]; then
  echo "[ERROR] --jobs must be a positive integer"
  exit 2
fi
if ! [[ "$RETRIES" =~ ^[0-9]+$ ]] || [[ "$RETRIES" -lt 0 ]]; then
  echo "[ERROR] --retries must be >= 0"
  exit 2
fi

if [[ -n "$LIST_FILE" ]]; then
  if [[ ! -f "$LIST_FILE" ]]; then
    echo "[ERROR] list file not found: $LIST_FILE"
    exit 2
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -z "$line" ]] && continue
    TARGETS+=("$line")
  done < "$LIST_FILE"
fi

if [[ "${#TARGETS[@]}" -eq 0 ]]; then
  echo "[ERROR] no target files provided"
  usage
  exit 2
fi

BOOTSTRAP="codex_settings/scripts/swarm_file_bootstrap.sh"
if [[ ! -f "$BOOTSTRAP" ]]; then
  echo "[ERROR] bootstrap script not found: $BOOTSTRAP"
  exit 2
fi

RUN_ID="swarm-$(date +%Y%m%d-%H%M%S)"
RUN_DIR="codex_settings/runs/${RUN_ID}"
mkdir -p "$RUN_DIR"

echo "== swarm run start =="
echo "run_id: $RUN_ID"
echo "jobs: $JOBS"
echo "retries: $RETRIES"
echo "targets: ${#TARGETS[@]}"
echo "run_dir: $RUN_DIR"
echo

sanitize_name() {
  echo "$1" | tr '/ :\\' '____' | tr -cd '[:alnum:]_.-'
}

run_one() {
  local target="$1"
  local name log status_file
  local attempt=0
  local max_attempts=$((RETRIES + 1))
  name="$(sanitize_name "$target")"
  log="$RUN_DIR/${name}.log"
  status_file="$RUN_DIR/${name}.status"

  : > "$log"
  while [[ "$attempt" -lt "$max_attempts" ]]; do
    attempt=$((attempt + 1))
    {
      echo "[INFO] target=$target attempt=$attempt/$max_attempts"
      bash "./$BOOTSTRAP" "$target"
    } >> "$log" 2>&1 && {
      echo "OK|$target|attempt=$attempt|log=$log" > "$status_file"
      return 0
    }
    if [[ "$attempt" -lt "$max_attempts" ]]; then
      sleep $((attempt * 2))
    fi
  done

  echo "FAIL|$target|attempt=$attempt|log=$log" > "$status_file"
  return 1
}

for target in "${TARGETS[@]}"; do
  while [[ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$JOBS" ]]; do
    sleep 0.2
  done
  run_one "$target" &
done

wait || true

ok_count=0
fail_count=0
echo "== swarm summary =="
for f in "$RUN_DIR"/*.status; do
  [[ -f "$f" ]] || continue
  line="$(cat "$f")"
  echo "$line"
  if [[ "$line" == OK* ]]; then
    ok_count=$((ok_count + 1))
  else
    fail_count=$((fail_count + 1))
  fi
done

echo
echo "ok: $ok_count"
echo "fail: $fail_count"
echo "run_dir: $RUN_DIR"

if [[ "$fail_count" -gt 0 ]]; then
  exit 1
fi
