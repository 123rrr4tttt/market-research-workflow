#!/usr/bin/env bash
set -u

CANDIDATE=/Users/wangyiliang/.codex/release-rehearsals/mrw-stage2-20260910-v4-r13o/candidate
OUT=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13o/artifacts
SECURITY=/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13o/security
CANONICAL_BUILDER="mrw-r13o-canonical-${RANDOM}"
REBUILD_BUILDER="mrw-r13o-rebuild-${RANDOM}"
CREATED_CANONICAL=0
CREATED_REBUILD=0

cleanup() {
  if [[ "$CREATED_CANONICAL" == 1 ]]; then
    docker buildx rm "$CANONICAL_BUILDER" >/dev/null 2>&1 || true
  fi
  if [[ "$CREATED_REBUILD" == 1 ]]; then
    docker buildx rm "$REBUILD_BUILDER" >/dev/null 2>&1 || true
  fi
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

mkdir -p "$OUT/canonical" "$OUT/rebuild"

{
  printf 'candidate=%s\n' "$CANDIDATE"
  git -C "$CANDIDATE" rev-parse HEAD HEAD^{tree}
  git -C "$CANDIDATE" status --short --untracked-files=all
  printf 'canonical_builder=%s\nrebuild_builder=%s\n' "$CANONICAL_BUILDER" "$REBUILD_BUILDER"
  docker version
  docker buildx version
  syft version
  trivy version
  df -h /System/Volumes/Data
} > "$OUT/environment.log" 2>&1
printf '%s\n' "$?" > "$OUT/environment.exit.txt"

run_logged canonical-builder-create "$OUT" \
  docker buildx create --driver docker-container --name "$CANONICAL_BUILDER"
if [[ "$(<"$OUT/canonical-builder-create.exit.txt")" == 0 ]]; then
  CREATED_CANONICAL=1
  run_logged canonical-builder-bootstrap "$OUT" \
    docker buildx inspect --bootstrap "$CANONICAL_BUILDER"
else
  printf '%s\n' 125 > "$OUT/canonical-builder-bootstrap.exit.txt"
  printf '%s\n' 'not run because builder creation failed' > "$OUT/canonical-builder-bootstrap.log"
fi

run_logged rebuild-builder-create "$OUT" \
  docker buildx create --driver docker-container --name "$REBUILD_BUILDER"
if [[ "$(<"$OUT/rebuild-builder-create.exit.txt")" == 0 ]]; then
  CREATED_REBUILD=1
  run_logged rebuild-builder-bootstrap "$OUT" \
    docker buildx inspect --bootstrap "$REBUILD_BUILDER"
else
  printf '%s\n' 125 > "$OUT/rebuild-builder-bootstrap.exit.txt"
  printf '%s\n' 'not run because builder creation failed' > "$OUT/rebuild-builder-bootstrap.log"
fi

build_role() {
  local phase="$1"
  local role="$2"
  local builder="$3"
  local context="$4"
  local dockerfile="$5"
  local target="$6"
  local provenance="$7"
  local sbom="$8"
  local archive="$OUT/$phase/${role}.oci.tar"
  local metadata="$OUT/$phase/${role}.build-metadata.json"
  run_logged "$phase-$role-build" "$context" \
    docker buildx build --builder "$builder" --progress plain --no-cache \
    --platform linux/arm64 --provenance="$provenance" --sbom="$sbom" \
    --build-arg SOURCE_DATE_EPOCH=0 --file "$dockerfile" --target "$target" \
    --metadata-file "$metadata" --output "type=oci,dest=$archive" .
}

if [[ "$(<"$OUT/canonical-builder-bootstrap.exit.txt")" == 0 ]]; then
  build_role canonical backend "$CANONICAL_BUILDER" "$CANDIDATE" main/backend/Dockerfile backend-runtime true true
  build_role canonical frontend "$CANONICAL_BUILDER" "$CANDIDATE/main/frontend-modern" Dockerfile frontend-runtime true true
  build_role canonical migration-runner "$CANONICAL_BUILDER" "$CANDIDATE" main/backend/Dockerfile migration-runner true true
else
  for role in backend frontend migration-runner; do
    printf '%s\n' 125 > "$OUT/canonical-$role-build.exit.txt"
    printf '%s\n' 'not run because canonical builder unavailable' > "$OUT/canonical-$role-build.log"
  done
fi

if [[ "$(<"$OUT/rebuild-builder-bootstrap.exit.txt")" == 0 ]]; then
  build_role rebuild backend "$REBUILD_BUILDER" "$CANDIDATE" main/backend/Dockerfile backend-runtime false false
  build_role rebuild frontend "$REBUILD_BUILDER" "$CANDIDATE/main/frontend-modern" Dockerfile frontend-runtime false false
  build_role rebuild migration-runner "$REBUILD_BUILDER" "$CANDIDATE" main/backend/Dockerfile migration-runner false false
else
  for role in backend frontend migration-runner; do
    printf '%s\n' 125 > "$OUT/rebuild-$role-build.exit.txt"
    printf '%s\n' 'not run because rebuild builder unavailable' > "$OUT/rebuild-$role-build.log"
  done
fi

python3 - "$OUT" <<'PY'
import gzip
import hashlib
import json
import pathlib
import re
import sys
import tarfile

out = pathlib.Path(sys.argv[1])
digest_pattern = re.compile(r"sha256:[0-9a-f]{64}")
roles = ("backend", "frontend", "migration-runner")

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def blob(bundle, digest):
    if not digest_pattern.fullmatch(str(digest)):
        raise ValueError(f"invalid digest {digest!r}")
    payload = bundle.extractfile(f"blobs/sha256/{digest.removeprefix('sha256:')}").read()
    if hashlib.sha256(payload).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"blob digest mismatch {digest}")
    return payload

def inspect_archive(archive, phase, role):
    with tarfile.open(archive, "r") as bundle:
        archive_index = json.load(bundle.extractfile("index.json"))
        roots = archive_index.get("manifests") or []
        if len(roots) != 1:
            raise ValueError("expected exactly one OCI root")
        root_digest = roots[0].get("digest", "")
        root_document = json.loads(blob(bundle, root_digest))
        if isinstance(root_document.get("manifests"), list):
            images = [
                d for d in root_document["manifests"]
                if d.get("platform", {}).get("os") == "linux"
                and d.get("platform", {}).get("architecture") == "arm64"
                and d.get("annotations", {}).get("vnd.docker.reference.type") != "attestation-manifest"
            ]
            attestations = [d for d in root_document["manifests"] if d not in images]
            if len(images) != 1:
                raise ValueError("linux/arm64 image manifest is ambiguous")
            artifact_digest = images[0]["digest"]
            manifest = json.loads(blob(bundle, artifact_digest))
        else:
            artifact_digest = root_digest
            manifest = root_document
            attestations = []
        config_descriptor = manifest.get("config") or {}
        layers = manifest.get("layers") or []
        config = json.loads(blob(bundle, config_descriptor["digest"]))
        for layer in layers:
            blob(bundle, layer["digest"])
        statements = []
        for descriptor in attestations:
            attestation_manifest = json.loads(blob(bundle, descriptor["digest"]))
            for layer in attestation_manifest.get("layers") or []:
                payload = blob(bundle, layer["digest"])
                if "gzip" in str(layer.get("mediaType", "")):
                    payload = gzip.decompress(payload)
                statements.append(json.loads(payload))
        inspection = {
            "phase": phase,
            "role": role,
            "platform": f"{config.get('os')}/{config.get('architecture')}",
            "oci_root_digest": root_digest,
            "artifact_digest": artifact_digest,
            "image_config_digest": config_descriptor["digest"],
            "image_layer_digests": [layer["digest"] for layer in layers],
            "archive_sha256": sha(archive),
            "archive_bytes": archive.stat().st_size,
            "attestation_manifest_count": len(attestations),
        }
        phase_root = out / phase
        (phase_root / f"{role}.digest-inspection.json").write_text(json.dumps(inspection, indent=2, sort_keys=True) + "\n")
        if phase == "canonical":
            provenance = [s for s in statements if str(s.get("predicateType", "")).startswith("https://slsa.dev/provenance/")]
            sboms = [s for s in statements if str(s.get("predicateType", "")).startswith("https://spdx.dev/Document")]
            if len(provenance) == 1:
                (phase_root / f"{role}.provenance.intoto.json").write_text(json.dumps(provenance[0], indent=2, sort_keys=True) + "\n")
            if len(sboms) == 1:
                (phase_root / f"{role}.sbom.spdx.intoto.json").write_text(json.dumps(sboms[0], indent=2, sort_keys=True) + "\n")
            inspection["slsa_provenance_count"] = len(provenance)
            inspection["spdx_sbom_count"] = len(sboms)
            (phase_root / f"{role}.digest-inspection.json").write_text(json.dumps(inspection, indent=2, sort_keys=True) + "\n")
        return inspection

inspections = {"canonical": {}, "rebuild": {}}
errors = {}
for phase in inspections:
    for role in roles:
        archive = out / phase / f"{role}.oci.tar"
        if not archive.is_file():
            errors[f"{phase}/{role}"] = "archive missing"
            continue
        try:
            inspections[phase][role] = inspect_archive(archive, phase, role)
        except Exception as exc:
            errors[f"{phase}/{role}"] = str(exc)

comparisons = {}
for role in roles:
    canonical = inspections["canonical"].get(role)
    rebuild = inspections["rebuild"].get(role)
    if canonical and rebuild:
        match = canonical["artifact_digest"] == rebuild["artifact_digest"]
        comparison = {
            "role": role,
            "status": "MATCH" if match else "MISMATCH",
            "comparison_scope": "linux/arm64-image-manifest-digest",
            "canonical_digest": canonical["artifact_digest"],
            "rebuild_digest": rebuild["artifact_digest"],
            "canonical_oci_root_digest": canonical["oci_root_digest"],
            "rebuild_oci_root_digest": rebuild["oci_root_digest"],
            "builders": {"relationship": "separate-task-owned-docker-container-builder-instances"},
        }
        comparisons[role] = comparison
        (out / f"{role}.reproducibility.json").write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n")

payload = {
    "schema": "mrw.stage3.local-artifact-evidence.r13o.v1",
    "authoritative": False,
    "candidate": {"commit": "3669d4ddc19fb722058976b4e1f05e99eccfe96e", "tree": "ce4e4b9ce1b633276192e809fa72007176224e0c"},
    "platform": "linux/arm64",
    "canonical": inspections["canonical"],
    "rebuild": inspections["rebuild"],
    "comparisons": comparisons,
    "errors": errors,
    "scope": "Two separate task-owned docker-container Buildx builders, no-cache builds, local OCI output only. No registry push/promotion, signing, transparency log, deployment, or authority transfer. linux/arm64 is local evidence and does not satisfy the required CI linux/amd64 run.",
    "authority_ceiling": "LOCAL_ARTIFACT_EVIDENCE_NOT_RELEASE_AUTHORITY",
}
payload["status"] = "PASS_LOCAL_REPRODUCIBLE" if len(comparisons) == 3 and all(v["status"] == "MATCH" for v in comparisons.values()) and not errors else "FAILED_OR_INCOMPLETE"
(out / "summary.pre-scan.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
printf '%s\n' "$?" > "$OUT/archive-inspection.exit.txt"

for role in backend frontend migration-runner; do
  archive="$OUT/canonical/${role}.oci.tar"
  if [[ -s "$archive" ]]; then
    printf '%q ' trivy image --input "$archive" --exit-code 1 \
      --severity HIGH,CRITICAL --vuln-type os,library --format json \
      --output "$SECURITY/${role}.trivy.canonical.json" \
      > "$SECURITY/${role}-trivy-canonical.command.txt"
    printf '\n' >> "$SECURITY/${role}-trivy-canonical.command.txt"
    trivy image --input "$archive" --exit-code 1 \
      --severity HIGH,CRITICAL --vuln-type os,library --format json \
      --output "$SECURITY/${role}.trivy.canonical.json" \
      > "$SECURITY/${role}-trivy-canonical.log" 2>&1
    printf '%s\n' "$?" > "$SECURITY/${role}-trivy-canonical.exit.txt"
  else
    printf '%s\n' 125 > "$SECURITY/${role}-trivy-canonical.exit.txt"
    printf '%s\n' 'not run because canonical OCI archive is missing' > "$SECURITY/${role}-trivy-canonical.log"
  fi
done

python3 - "$OUT" "$SECURITY" <<'PY'
import hashlib
import json
import pathlib
import sys

out = pathlib.Path(sys.argv[1])
security = pathlib.Path(sys.argv[2])
payload = json.loads((out / "summary.pre-scan.json").read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def exit_code(path):
    return int(path.read_text().strip()) if path.is_file() else None

payload["build_commands"] = {}
for phase in ("canonical", "rebuild"):
    for role in ("backend", "frontend", "migration-runner"):
        name = f"{phase}-{role}-build"
        payload["build_commands"][name] = {
            "exit_code": exit_code(out / f"{name}.exit.txt"),
            "command_sha256": sha(out / f"{name}.command.txt"),
            "log_sha256": sha(out / f"{name}.log"),
            "metadata_sha256": sha(out / phase / f"{role}.build-metadata.json"),
        }
payload["image_scans"] = {}
for role in ("backend", "frontend", "migration-runner"):
    payload["image_scans"][role] = {
        "exit_code": exit_code(security / f"{role}-trivy-canonical.exit.txt"),
        "command_sha256": sha(security / f"{role}-trivy-canonical.command.txt"),
        "log_sha256": sha(security / f"{role}-trivy-canonical.log"),
        "report_sha256": sha(security / f"{role}.trivy.canonical.json"),
    }
if payload["status"] == "PASS_LOCAL_REPRODUCIBLE" and not all(v["exit_code"] == 0 for v in payload["image_scans"].values()):
    payload["status"] = "FAILED_SECURITY_SCAN"
(out / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY
printf '%s\n' "$?" > "$OUT/summary-generation.exit.txt"

