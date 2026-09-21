#!/usr/bin/env bash
set -u

SOURCE=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13o/artifacts
OUT=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13p/artifacts
declare -a TAGS=()
declare -a CONTAINERS=()

cleanup() {
  for container in "${CONTAINERS[@]}"; do
    docker stop "$container" >/dev/null 2>&1 || true
  done
  for tag in "${TAGS[@]}"; do
    docker image rm "$tag" >> "$OUT/runtime-image-cleanup.log" 2>&1 || true
  done
}
trap cleanup EXIT

run_logged() {
  local name="$1"
  shift
  printf '%q ' "$@" > "$OUT/${name}.command.txt"
  printf '\n' >> "$OUT/${name}.command.txt"
  "$@" > "$OUT/${name}.log" 2>&1
  local code=$?
  printf '%s\n' "$code" > "$OUT/${name}.exit.txt"
  return 0
}

load_role() {
  local phase="$1"
  local role="$2"
  local archive="$SOURCE/$phase/${role}.oci.tar"
  local name="runtime-load-${phase}-${role}"
  run_logged "$name" docker load -i "$archive"
  if [[ "$(<"$OUT/${name}.exit.txt")" != 0 ]]; then
    return 1
  fi
  local image_id
  image_id=$(sed -n 's/^Loaded image ID: //p' "$OUT/${name}.log" | tail -n 1)
  if [[ -z "$image_id" ]]; then
    printf '%s\n' 'docker load did not return an image ID' >> "$OUT/${name}.log"
    printf '%s\n' 125 > "$OUT/${name}.exit.txt"
    return 1
  fi
  local tag="mrw-r13p-runtime-${role}-${phase}:local"
  run_logged "runtime-tag-${phase}-${role}" docker tag "$image_id" "$tag"
  if [[ "$(<"$OUT/runtime-tag-${phase}-${role}.exit.txt")" != 0 ]]; then
    return 1
  fi
  TAGS+=("$tag")
  printf '%s\n' "$tag" > "$OUT/runtime-tag-${phase}-${role}.value.txt"
}

for phase in canonical rebuild; do
  for role in backend frontend migration-runner; do
    load_role "$phase" "$role" || true
  done
done

for phase in canonical rebuild; do
  backend="mrw-r13p-runtime-backend-${phase}:local"
  migration="mrw-r13p-runtime-migration-runner-${phase}:local"
  frontend="mrw-r13p-runtime-frontend-${phase}:local"

  run_logged "runtime-backend-${phase}-entrypoint-boundary" \
    docker run --rm --name "mrw-r13p-backend-${phase}-boundary" \
    -e STARTUP_MAX_RETRIES=1 -e STARTUP_RETRY_DELAY=0 \
    -e DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:9/postgres \
    "$backend"
  run_logged "runtime-backend-${phase}-import" \
    docker run --rm --entrypoint python "$backend" -c \
    'from app.main import app; print(app.title)'

  run_logged "runtime-migration-runner-${phase}-help" \
    docker run --rm "$migration" --help

  run_logged "runtime-frontend-${phase}-nginx-test" \
    docker run --rm "$frontend" nginx -t

  container="mrw-r13p-frontend-${phase}-http"
  CONTAINERS+=("$container")
  run_logged "runtime-frontend-${phase}-start" \
    docker run -d --rm --name "$container" -p 127.0.0.1::80 "$frontend"
  if [[ "$(<"$OUT/runtime-frontend-${phase}-start.exit.txt")" == 0 ]]; then
    port=$(docker port "$container" 80/tcp | sed -n 's/.*://p' | tail -n 1)
    printf '%s\n' "$port" > "$OUT/runtime-frontend-${phase}-port.txt"
    code=1
    : > "$OUT/runtime-frontend-${phase}-http.log"
    for _ in $(seq 1 20); do
      curl -fsS -D "$OUT/runtime-frontend-${phase}-headers.txt" \
        -o "$OUT/runtime-frontend-${phase}-body.html" \
        "http://127.0.0.1:${port}/" \
        >> "$OUT/runtime-frontend-${phase}-http.log" 2>&1
      code=$?
      [[ "$code" == 0 ]] && break
      sleep 0.25
    done
    printf '%s\n' "$code" > "$OUT/runtime-frontend-${phase}-http.exit.txt"
    printf '%s\n' "curl -fsS -D runtime-frontend-${phase}-headers.txt -o runtime-frontend-${phase}-body.html http://127.0.0.1:<ephemeral>/" \
      > "$OUT/runtime-frontend-${phase}-http.command.txt"
    docker stop "$container" > "$OUT/runtime-frontend-${phase}-stop.log" 2>&1
    printf '%s\n' "$?" > "$OUT/runtime-frontend-${phase}-stop.exit.txt"
  else
    printf '%s\n' 125 > "$OUT/runtime-frontend-${phase}-http.exit.txt"
    printf '%s\n' 'not run because container start failed' > "$OUT/runtime-frontend-${phase}-http.log"
  fi
done
