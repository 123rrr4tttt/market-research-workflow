#!/usr/bin/env bash
set -u

ids=(
  fbe51a32acf6074207bdc2a1e71dc9e73b17a9a37096a51d5a4c7fd32570e35d
  4d5bc00f6e17a808ced8ae7bd1b30ec6df12570c9cdb0615f9ca540f35f3a25b
  7d195b06f8f3c568aecca001c588309e66c8be07a8bc4ab5d7f0186000d82b2b
  425a5be56b83fed64c0d85398656804e06853a56a4d643339f7a1615451495fc
  792d16b97838d2c079dc8ae9a9656b019be9b7149b11e330af10dc3b4a1d9b08
  ec9ae4788f9e1a2064064c7de82f2c1e098a20179d757166edf0a99f0a5958d9
)

status=0
for id in "${ids[@]}"; do
  if docker image inspect "sha256:$id" >/dev/null 2>&1; then
    printf 'REMAINS sha256:%s\n' "$id"
    status=1
  else
    printf 'ABSENT sha256:%s\n' "$id"
  fi
done

containers=$(docker ps -a --format '{{.Names}}' | grep '^mrw-r13p-' || true)
tags=$(docker images --format '{{.Repository}}:{{.Tag}}' | grep '^mrw-r13p-runtime-' || true)
builders=$(docker buildx ls | grep 'mrw-r13[op]' || true)
printf 'containers=%s\n' "${containers:-NONE}"
printf 'tags=%s\n' "${tags:-NONE}"
printf 'builders=%s\n' "${builders:-NONE}"
[[ -z "$containers" && -z "$tags" && -z "$builders" ]] || status=1
exit "$status"
