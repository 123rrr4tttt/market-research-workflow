#!/usr/bin/env bash
set -euo pipefail

candidate=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260912-v4-r13x/candidate
replay=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260912-v4-r13x/replay
evidence=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13x/artifacts
expected_commit=8c965dd2dcdc5d3e0883c3d7f65fb720dc2d87a2
expected_tree=ce7c67c831b51f9d64b4c2f1a470a724a50b19df
canonical_builder=mrw-r13x-canonical-amd64
replay_builder=mrw-r13x-replay-amd64

mkdir -p "$evidence/candidate" "$evidence/replay" "$evidence/logs" "$evidence/metadata"
for source in "$candidate" "$replay"; do
  test "$(git -C "$source" rev-parse HEAD)" = "$expected_commit"
  test "$(git -C "$source" rev-parse 'HEAD^{tree}')" = "$expected_tree"
  test -z "$(git -C "$source" status --porcelain)"
  test "$(git -C "$source" rev-parse --is-shallow-repository)" = false
done
docker buildx inspect "$canonical_builder" >/dev/null 2>&1 || docker buildx create --name "$canonical_builder" --driver docker-container --bootstrap
docker buildx inspect --bootstrap "$canonical_builder"
docker buildx inspect "$replay_builder" >/dev/null 2>&1 || docker buildx create --name "$replay_builder" --driver docker-container --bootstrap
docker buildx inspect --bootstrap "$replay_builder"

build_role() {
  local source=$1 builder=$2 flavor=$3 role=$4 attest=$5 context dockerfile target tag
  if [ "$role" = frontend ]; then
    context="$source/main/frontend-modern"; dockerfile="$source/main/frontend-modern/Dockerfile"; target=frontend-runtime
  else
    context="$source"; dockerfile="$source/main/backend/Dockerfile"
    if [ "$role" = backend ]; then target=backend-runtime; else target=migration-runner; fi
  fi
  tag="mrw-local/r13x-${flavor}-${role}:${expected_commit}"
  mkdir -p "$evidence/$flavor/$role"
  {
    printf 'source=%s\nbuilder=%s\n' "$source" "$builder"
    printf 'platform=linux/amd64\nno_cache=true\nsource_date_epoch=0\noptional_enhancements=false\n'
    printf 'tag=%s\ntarget=%s\nprovenance=%s\nsbom=%s\n' "$tag" "$target" "$attest" "$attest"
  } > "$evidence/$flavor/$role/build-contract.txt"
  docker buildx build --builder "$builder" --platform linux/amd64 --no-cache \
    --provenance="$attest" --sbom="$attest" --build-arg SOURCE_DATE_EPOCH=0 \
    --tag "$tag" --target "$target" --file "$dockerfile" \
    --output "type=oci,dest=$evidence/$flavor/$role/image.oci.tar,rewrite-timestamp=true" \
    --metadata-file "$evidence/$flavor/$role/build-metadata.json" --progress plain "$context" \
    2>&1 | tee "$evidence/logs/${flavor}-${role}.log"
}

build_role "$candidate" "$canonical_builder" candidate backend true
build_role "$candidate" "$canonical_builder" candidate frontend true
build_role "$candidate" "$canonical_builder" candidate migration-runner true
build_role "$replay" "$replay_builder" replay backend false
build_role "$replay" "$replay_builder" replay frontend false
build_role "$replay" "$replay_builder" replay migration-runner false
printf 'fresh builds complete\n'
