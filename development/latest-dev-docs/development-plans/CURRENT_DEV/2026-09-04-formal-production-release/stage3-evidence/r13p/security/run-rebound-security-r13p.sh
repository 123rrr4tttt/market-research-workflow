#!/usr/bin/env bash
set -u

CANDIDATE=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13p/candidate
OUT=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13p/security
R13O_ARTIFACTS=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13o/artifacts

run_logged() {
  local name="$1"
  shift
  printf '%q ' "$@" > "$OUT/${name}.command.txt"
  printf '\n' >> "$OUT/${name}.command.txt"
  "$@" > "$OUT/${name}.log" 2>&1
  local code=$?
  printf '%s\n' "$code" > "$OUT/${name}.exit.txt"
}

run_logged gitleaks-current-tree \
  gitleaks dir --redact=100 --no-banner --no-color --report-format json \
  --report-path "$OUT/gitleaks-current-tree.report.json" "$CANDIDATE"

for role in backend frontend migration-runner; do
  archive="$R13O_ARTIFACTS/canonical/${role}.oci.tar"
  layout="$(mktemp -d "/private/tmp/mrw-r13p-${role}-oci.XXXXXX")"
  printf '%q ' tar -xf "$archive" -C "$layout" > "$OUT/${role}-oci-extract.command.txt"
  printf '\n' >> "$OUT/${role}-oci-extract.command.txt"
  tar -xf "$archive" -C "$layout" > "$OUT/${role}-oci-extract.log" 2>&1
  printf '%s\n' "$?" > "$OUT/${role}-oci-extract.exit.txt"

  printf '%q ' trivy image --input "$layout" --scanners vuln --exit-code 1 \
    --severity HIGH,CRITICAL --pkg-types os,library --format json \
    --output "$OUT/${role}.trivy.r13o-role-input.json" \
    > "$OUT/${role}-trivy-r13o-role-input.command.txt"
  printf '\n' >> "$OUT/${role}-trivy-r13o-role-input.command.txt"
  trivy image --input "$layout" --scanners vuln --exit-code 1 \
    --severity HIGH,CRITICAL --pkg-types os,library --format json \
    --output "$OUT/${role}.trivy.r13o-role-input.json" \
    > "$OUT/${role}-trivy-r13o-role-input.log" 2>&1
  printf '%s\n' "$?" > "$OUT/${role}-trivy-r13o-role-input.exit.txt"

  rm -rf -- "$layout"
done
