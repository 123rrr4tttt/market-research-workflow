#!/usr/bin/env python3
import gzip
import hashlib
import io
import json
import re
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ROLES = ("backend", "frontend", "migration-runner")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def read_blob(bundle: tarfile.TarFile, digest: str) -> bytes:
    if not DIGEST.fullmatch(digest):
        raise ValueError(f"invalid digest {digest!r}")
    payload = bundle.extractfile(f"blobs/sha256/{digest[7:]}").read()
    if sha(payload) != digest[7:]:
        raise ValueError(f"blob digest mismatch {digest}")
    return payload


def contract(flavor: str, role: str) -> dict[str, str]:
    output = {}
    for line in (ROOT / flavor / role / "build-contract.txt").read_text().splitlines():
        key, value = line.split("=", 1)
        output[key] = value
    return output


def inspect(flavor: str, role: str) -> dict:
    archive = ROOT / flavor / role / "image.oci.tar"
    metadata = json.loads((ROOT / flavor / role / "build-metadata.json").read_text())
    expected_root = metadata.get("containerimage.digest")
    with tarfile.open(archive, "r") as bundle:
        archive_index = json.load(bundle.extractfile("index.json"))
        roots = archive_index.get("manifests") or []
        if len(roots) != 1 or roots[0].get("digest") != expected_root:
            raise ValueError(f"{flavor}/{role}: metadata/archive root mismatch")
        root_doc = json.loads(read_blob(bundle, expected_root))
        descriptors = root_doc.get("manifests")
        if isinstance(descriptors, list):
            images = [
                d for d in descriptors
                if (d.get("annotations") or {}).get("vnd.docker.reference.type") is None
                and (d.get("annotations") or {}).get("vnd.docker.reference.digest") is None
                and d.get("platform", {}).get("os") == "linux"
                and d.get("platform", {}).get("architecture") == "amd64"
            ]
            attestations = [
                d for d in descriptors
                if (d.get("annotations") or {}).get("vnd.docker.reference.type") == "attestation-manifest"
                and d.get("platform", {}).get("os") == "unknown"
                and d.get("platform", {}).get("architecture") == "unknown"
            ]
            unexpected = [d for d in descriptors if d not in images and d not in attestations]
            if len(images) != 1 or unexpected:
                raise ValueError(f"{flavor}/{role}: ambiguous image or unexpected descriptor")
            image_digest = images[0]["digest"]
        else:
            images, attestations, unexpected = [], [], []
            image_digest = expected_root
        manifest = json.loads(read_blob(bundle, image_digest))
        config_digest = manifest.get("config", {}).get("digest", "")
        config = json.loads(read_blob(bundle, config_digest))
        layers = manifest.get("layers") or []
        if not layers or config.get("os") != "linux" or config.get("architecture") != "amd64":
            raise ValueError(f"{flavor}/{role}: incomplete or wrong-platform image")
        layer_digests = []
        for layer in layers:
            layer_digest = layer.get("digest", "")
            read_blob(bundle, layer_digest)
            layer_digests.append(layer_digest)

        statements = []
        for position, descriptor in enumerate(attestations):
            annotations = descriptor.get("annotations") or {}
            if annotations.get("vnd.docker.reference.digest") != image_digest:
                raise ValueError(f"{flavor}/{role}: detached attestation descriptor")
            att_digest = descriptor.get("digest", "")
            att_manifest_payload = read_blob(bundle, att_digest)
            (ROOT / flavor / role / f"attestation-manifest-{position}.json").write_bytes(att_manifest_payload)
            att_manifest = json.loads(att_manifest_payload)
            for layer in att_manifest.get("layers") or []:
                payload = read_blob(bundle, layer.get("digest", ""))
                if "gzip" in str(layer.get("mediaType", "")):
                    payload = gzip.decompress(payload)
                statements.append(json.loads(payload))

    result = {
        "flavor": flavor,
        "role": role,
        "oci_index_digest": expected_root,
        "artifact_digest": image_digest,
        "image_config_digest": config_digest,
        "image_layer_digests": layer_digests,
        "archive_sha256": sha(archive.read_bytes()),
        "platform": "linux/amd64",
        "descriptor_counts": {
            "image": len(images) if images else 1,
            "attestation": len(attestations),
            "unexpected": len(unexpected),
        },
    }
    if flavor == "candidate":
        if not attestations:
            raise ValueError(f"candidate/{role}: missing attestation descriptor")
        tag = contract(flavor, role)["tag"]
        repository, version = tag.rsplit(":", 1)
        expected_subject = [{
            "name": f"pkg:docker/{repository}@{version}?platform=linux%2Famd64",
            "digest": {"sha256": image_digest[7:]},
        }]
        matching = {}
        for label, prefix in (("provenance", "https://slsa.dev/provenance/"), ("sbom", "https://spdx.dev/Document")):
            matches = [
                s for s in statements
                if str(s.get("predicateType", "")).startswith(prefix)
                and s.get("subject") == expected_subject
                and isinstance(s.get("predicate"), dict)
            ]
            if len(matches) != 1:
                raise ValueError(f"candidate/{role}: missing unique exact {label} subject")
            matching[label] = matches[0]
            suffix = "provenance.intoto.json" if label == "provenance" else "sbom.spdx.intoto.json"
            (ROOT / flavor / role / suffix).write_text(json.dumps(matches[0], sort_keys=True) + "\n")
        if not (matching["provenance"]["predicate"].get("buildDefinition") or matching["provenance"]["predicate"].get("builder")):
            raise ValueError(f"candidate/{role}: empty provenance build content")
        spdx = matching["sbom"]["predicate"]
        if not str(spdx.get("spdxVersion", "")).startswith("SPDX-") or not isinstance(spdx.get("packages"), list):
            raise ValueError(f"candidate/{role}: malformed SPDX document")
        result["expected_statement_subject"] = expected_subject
        result["statement_binding"] = "PASS"
    elif attestations:
        raise ValueError(f"replay/{role}: unexpected attestation descriptors")
    (ROOT / flavor / role / "digest-inspection.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def extract_candidate(role: str) -> None:
    archive = ROOT / "candidate" / role / "image.oci.tar"
    destination = ROOT / "layouts" / role
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    with tarfile.open(archive, "r") as bundle:
        for member in bundle.getmembers():
            relative = Path(member.name)
            if relative.is_absolute() or ".." in relative.parts or not (member.isdir() or member.isfile()):
                raise ValueError(f"unsafe OCI archive member {role}: {member.name}")
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                source = bundle.extractfile(member)
                if source is None:
                    raise ValueError(f"unreadable OCI archive member {role}: {member.name}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read())
    if not (destination / "oci-layout").is_file() or not (destination / "index.json").is_file():
        raise ValueError(f"incomplete extracted OCI layout: {role}")


def apk_log_diff(candidate: dict, replay: dict, role: str) -> dict | None:
    differing = [i for i, pair in enumerate(zip(candidate["image_layer_digests"], replay["image_layer_digests"])) if pair[0] != pair[1]]
    if differing != [6] or role not in {"backend", "migration-runner"}:
        return None
    files = []
    for flavor, info in (("candidate", candidate), ("replay", replay)):
        archive = ROOT / flavor / role / "image.oci.tar"
        with tarfile.open(archive, "r") as bundle:
            manifest = json.loads(read_blob(bundle, info["artifact_digest"]))
            descriptor = manifest["layers"][6]
            payload = read_blob(bundle, descriptor["digest"])
            if "gzip" in descriptor["mediaType"]:
                payload = gzip.decompress(payload)
            layer = tarfile.open(fileobj=io.BytesIO(payload))
            members = {}
            for member in layer:
                if member.isfile():
                    members[member.name] = sha(layer.extractfile(member).read())
            files.append(members)
    changed = [name for name in sorted(set(files[0]) | set(files[1])) if files[0].get(name) != files[1].get(name)]
    return {"differing_layer_positions_zero_based": differing, "differing_files": changed}


def main() -> int:
    all_info = {flavor: {} for flavor in ("candidate", "replay")}
    for flavor in all_info:
        for role in ROLES:
            all_info[flavor][role] = inspect(flavor, role)
    comparisons = {}
    all_match = True
    for role in ROLES:
        left = all_info["candidate"][role]
        right = all_info["replay"][role]
        checks = {
            "manifest": left["artifact_digest"] == right["artifact_digest"],
            "config": left["image_config_digest"] == right["image_config_digest"],
            "ordered_layers": left["image_layer_digests"] == right["image_layer_digests"],
        }
        passed = all(checks.values())
        all_match &= passed
        comparisons[role] = {
            "status": "MATCH" if passed else "MISMATCH",
            "checks": checks,
            "candidate": {key: left[key] for key in ("artifact_digest", "image_config_digest", "image_layer_digests")},
            "replay": {key: right[key] for key in ("artifact_digest", "image_config_digest", "image_layer_digests")},
            "bounded_difference_analysis": apk_log_diff(left, right, role),
        }
        extract_candidate(role)
    output = {
        "schema_version": "mrw.stage3.fresh-artifact-comparison.v1",
        "source_commit": "6aa7518750f2c29229a443f73248c8133f192e4d",
        "source_tree": "9853f36db67a5b62c297f6266bc4d0861a28c396",
        "builders": {"candidate": "mrw-r13w-canonical-amd64", "replay": "mrw-r13w-replay-amd64"},
        "build_contract": {"platform": "linux/amd64", "no_cache": True, "source_date_epoch": 0, "optional_enhancements": False},
        "attestation_validation": "PASS",
        "reproducibility": "PASS" if all_match else "FAIL",
        "roles": comparisons,
    }
    (ROOT / "artifact-comparison.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"attestation_validation": "PASS", "reproducibility": output["reproducibility"]}, sort_keys=True))
    return 0 if all_match else 2


if __name__ == "__main__":
    raise SystemExit(main())
