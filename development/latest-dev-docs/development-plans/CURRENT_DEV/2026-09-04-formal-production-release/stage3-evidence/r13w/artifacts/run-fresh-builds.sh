#!/usr/bin/env bash
set -euo pipefail

candidate=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260912-v4-r13w/candidate
replay=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260912-v4-r13w/replay
evidence=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13w/artifacts
expected_commit=6aa7518750f2c29229a443f73248c8133f192e4d
expected_tree=9853f36db67a5b62c297f6266bc4d0861a28c396
canonical_builder=mrw-r13w-canonical-amd64
replay_builder=mrw-r13w-replay-amd64

mkdir -p "$evidence/candidate" "$evidence/replay" "$evidence/logs" "$evidence/metadata"

for source in "$candidate" "$replay"; do
  test "$(git -C "$source" rev-parse HEAD)" = "$expected_commit"
  test "$(git -C "$source" rev-parse 'HEAD^{tree}')" = "$expected_tree"
  test -z "$(git -C "$source" status --porcelain)"
  test "$(git -C "$source" rev-parse --is-shallow-repository)" = false
done

docker buildx inspect "$canonical_builder" >/dev/null 2>&1 || \
  docker buildx create --name "$canonical_builder" --driver docker-container --bootstrap
docker buildx inspect --bootstrap "$canonical_builder"
docker buildx inspect "$replay_builder" >/dev/null 2>&1 || \
  docker buildx create --name "$replay_builder" --driver docker-container --bootstrap
docker buildx inspect --bootstrap "$replay_builder"

build_role() {
  local source=$1
  local builder=$2
  local flavor=$3
  local role=$4
  local attest=$5
  local context dockerfile target tag
  if [ "$role" = frontend ]; then
    context="$source/main/frontend-modern"
    dockerfile="$source/main/frontend-modern/Dockerfile"
    target=frontend-runtime
  else
    context="$source"
    dockerfile="$source/main/backend/Dockerfile"
    if [ "$role" = backend ]; then target=backend-runtime; else target=migration-runner; fi
  fi
  tag="mrw-local/r13w-${flavor}-${role}:${expected_commit}"
  mkdir -p "$evidence/$flavor/$role"
  {
    printf 'source=%s\n' "$source"
    printf 'builder=%s\n' "$builder"
    printf 'platform=linux/amd64\nno_cache=true\nsource_date_epoch=0\noptional_enhancements=false\n'
    printf 'tag=%s\ntarget=%s\n' "$tag" "$target"
    printf 'provenance=%s\nsbom=%s\n' "$attest" "$attest"
  } > "$evidence/$flavor/$role/build-contract.txt"
  docker buildx build \
    --builder "$builder" \
    --platform linux/amd64 \
    --no-cache \
    --provenance="$attest" \
    --sbom="$attest" \
    --build-arg SOURCE_DATE_EPOCH=0 \
    --tag "$tag" \
    --target "$target" \
    --file "$dockerfile" \
    --output "type=oci,dest=$evidence/$flavor/$role/image.oci.tar,rewrite-timestamp=true" \
    --metadata-file "$evidence/$flavor/$role/build-metadata.json" \
    --progress plain \
    "$context" 2>&1 | tee "$evidence/logs/${flavor}-${role}.log"
}

build_role "$candidate" "$canonical_builder" candidate backend true
build_role "$candidate" "$canonical_builder" candidate frontend true
build_role "$candidate" "$canonical_builder" candidate migration-runner true
build_role "$replay" "$replay_builder" replay backend false
build_role "$replay" "$replay_builder" replay frontend false
build_role "$replay" "$replay_builder" replay migration-runner false

printf 'fresh builds complete\n'
