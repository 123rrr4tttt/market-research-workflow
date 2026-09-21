#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath


SOURCE = Path("/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13o/artifacts")
OUT = Path("/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13p/artifacts")
ROLES = ("backend", "frontend", "migration-runner")


def digest_stream(stream) -> str:
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def normalized(name: str) -> str:
    value = str(PurePosixPath("/" + name.lstrip("./")))
    return value if value != "/." else "/"


def read_blob(bundle: tarfile.TarFile, digest: str) -> bytes:
    handle = bundle.extractfile(f"blobs/sha256/{digest.removeprefix('sha256:')}")
    if handle is None:
        raise ValueError(f"missing blob {digest}")
    payload = handle.read()
    if hashlib.sha256(payload).hexdigest() != digest.removeprefix("sha256:"):
        raise ValueError(f"blob digest mismatch {digest}")
    return payload


def image_manifest(bundle: tarfile.TarFile) -> tuple[str, dict]:
    index_handle = bundle.extractfile("index.json")
    if index_handle is None:
        raise ValueError("missing index.json")
    index = json.load(index_handle)
    root_digest = index["manifests"][0]["digest"]
    root = json.loads(read_blob(bundle, root_digest))
    if "manifests" not in root:
        return root_digest, root
    images = [
        descriptor
        for descriptor in root["manifests"]
        if descriptor.get("platform", {}).get("os") == "linux"
        and descriptor.get("platform", {}).get("architecture") == "arm64"
        and descriptor.get("annotations", {}).get("vnd.docker.reference.type") != "attestation-manifest"
    ]
    if len(images) != 1:
        raise ValueError(f"expected one linux/arm64 image, got {len(images)}")
    digest = images[0]["digest"]
    return digest, json.loads(read_blob(bundle, digest))


def remove_path(inventory: dict[str, dict], path: str, descendants_only: bool = False) -> None:
    prefix = path.rstrip("/") + "/"
    for existing in list(inventory):
        if existing.startswith(prefix) or (not descendants_only and existing == path):
            del inventory[existing]


def inventory(archive: Path) -> tuple[dict[str, dict], dict, str]:
    final: dict[str, dict] = {}
    with tarfile.open(archive, "r") as bundle:
        manifest_digest, manifest = image_manifest(bundle)
        config_digest = manifest["config"]["digest"]
        config = json.loads(read_blob(bundle, config_digest))
        for descriptor in manifest.get("layers") or []:
            layer_handle = bundle.extractfile(f"blobs/sha256/{descriptor['digest'].removeprefix('sha256:')}")
            if layer_handle is None:
                raise ValueError(f"missing layer {descriptor['digest']}")
            with tarfile.open(fileobj=layer_handle, mode="r|*") as layer:
                for member in layer:
                    path = normalized(member.name)
                    basename = PurePosixPath(path).name
                    parent = str(PurePosixPath(path).parent)
                    if basename == ".wh..wh..opq":
                        remove_path(final, parent, descendants_only=True)
                        continue
                    if basename.startswith(".wh."):
                        target = str(PurePosixPath(parent) / basename.removeprefix(".wh."))
                        remove_path(final, target)
                        continue
                    entry = {
                        "type": (
                            "file" if member.isfile() else
                            "directory" if member.isdir() else
                            "symlink" if member.issym() else
                            "hardlink" if member.islnk() else
                            "other"
                        ),
                        "mode": member.mode,
                        "uid": member.uid,
                        "gid": member.gid,
                        "mtime": member.mtime,
                        "size": member.size,
                    }
                    if member.isfile():
                        handle = layer.extractfile(member)
                        if handle is None:
                            raise ValueError(f"cannot read regular file {path}")
                        entry["content_sha256"] = digest_stream(handle)
                    elif member.issym() or member.islnk():
                        entry["link_target"] = member.linkname
                    final[path] = entry
    return final, config, manifest_digest


def path_domain(path: str, entry: dict | None, kind: str) -> str:
    lowered = path.lower()
    if kind == "timestamp_only":
        return "timestamp_only"
    if any(marker in lowered for marker in ("/__pycache__/", "/.cache/", "/var/cache/", "/tmp/")) or lowered.endswith(".pyc"):
        return "cache_or_generated_bytecode"
    if (
        lowered.startswith("/var/lib/dpkg/")
        or lowered.startswith("/var/lib/apt/")
        or lowered.startswith("/lib/apk/db/")
        or lowered.startswith("/var/log/apt/")
        or lowered == "/var/log/dpkg.log"
        or lowered == "/var/log/alternatives.log"
        or ".dist-info/" in lowered
        or ".egg-info/" in lowered
    ):
        return "package_manager_metadata"
    if lowered.startswith("/usr/share/nginx/html/"):
        return "frontend_build_output"
    if entry and entry.get("type") == "file" and kind == "content_changed":
        return "actual_file_content"
    return "unknown"


def cause_assessment(domain: str) -> str:
    if domain == "timestamp_only":
        return "CONFIRMED_SAME_CONTENT_ONLY_MTIME_DIFFERS"
    if domain == "cache_or_generated_bytecode":
        return "PATH_CLASSIFIED_CACHE_OR_BYTECODE_EXACT_CAUSE_UNKNOWN"
    if domain == "package_manager_metadata":
        return "PATH_CLASSIFIED_PACKAGE_METADATA_OR_LOG"
    if domain == "frontend_build_output":
        return "FRONTEND_OUTPUT_BYTES_DIFFER"
    if domain == "actual_file_content":
        return "ACTUAL_BYTES_DIFFER_EXACT_CAUSE_UNKNOWN"
    return "UNKNOWN"


def compare(role: str) -> dict:
    canonical_path = SOURCE / "canonical" / f"{role}.oci.tar"
    rebuild_path = SOURCE / "rebuild" / f"{role}.oci.tar"
    canonical, canonical_config, canonical_digest = inventory(canonical_path)
    rebuild, rebuild_config, rebuild_digest = inventory(rebuild_path)

    runtime_config_keys = ("Entrypoint", "Cmd", "Env", "WorkingDir", "User", "ExposedPorts", "Healthcheck")
    canonical_runtime = {key: canonical_config.get("config", {}).get(key) for key in runtime_config_keys}
    rebuild_runtime = {key: rebuild_config.get("config", {}).get(key) for key in runtime_config_keys}

    differences = []
    for path in sorted(set(canonical) | set(rebuild)):
        left = canonical.get(path)
        right = rebuild.get(path)
        if left is None:
            kind = "inventory_added"
        elif right is None:
            kind = "inventory_removed"
        elif left == right:
            continue
        else:
            left_content = left.get("content_sha256")
            right_content = right.get("content_sha256")
            if left_content != right_content or left.get("type") != right.get("type") or left.get("link_target") != right.get("link_target"):
                kind = "content_changed"
            else:
                changed_fields = sorted(key for key in set(left) | set(right) if left.get(key) != right.get(key))
                kind = "timestamp_only" if changed_fields == ["mtime"] else "metadata_changed"
        entry = right or left
        domain = path_domain(path, entry, kind)
        differences.append(
            {
                "path": path,
                "kind": kind,
                "domain": domain,
                "cause_assessment": cause_assessment(domain),
                "canonical": left,
                "rebuild": right,
            }
        )

    counts: dict[str, int] = {}
    domains: dict[str, int] = {}
    for difference in differences:
        counts[difference["kind"]] = counts.get(difference["kind"], 0) + 1
        domains[difference["domain"]] = domains.get(difference["domain"], 0) + 1
    output = {
        "role": role,
        "canonical_image_manifest_digest": canonical_digest,
        "rebuild_image_manifest_digest": rebuild_digest,
        "runtime_config_equal": canonical_runtime == rebuild_runtime,
        "canonical_runtime_config": canonical_runtime,
        "rebuild_runtime_config": rebuild_runtime,
        "inventory": {
            "canonical_paths": len(canonical),
            "rebuild_paths": len(rebuild),
            "difference_count": len(differences),
            "by_kind": dict(sorted(counts.items())),
            "by_domain": dict(sorted(domains.items())),
        },
        "differences": differences,
        "classification_note": "Domains are path/content based. actual_file_content means bytes differ outside known cache/package-metadata paths; it does not identify semantic cause. unknown is intentionally retained where the evidence is insufficient.",
    }
    (OUT / f"{role}.rootfs-difference.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"role": role, "runtime_config_equal": output["runtime_config_equal"], **output["inventory"]}, sort_keys=True))
    return output


summary = {
    "schema": "mrw.stage3.rootfs-difference-domain.r13p.v1",
    "source_candidate": {"commit": "3669d4ddc19fb722058976b4e1f05e99eccfe96e", "tree": "ce4e4b9ce1b633276192e809fa72007176224e0c"},
    "target_candidate": {"commit": "342d3b3c35ad987c47990da6ac550dfe936d4818", "tree": "3f87e85dce02b312e445c657c238c11c6809850e"},
    "role_input_reuse": "main/backend, src, and main/frontend-modern Git trees are identical between source and target candidates; embedded provenance remains bound to r13o.",
    "roles": {role: compare(role) for role in ROLES},
    "status": "ROOTFS_MISMATCH_CLASSIFIED_NOT_EQUIVALENCE",
}
(OUT / "rootfs-difference-domain.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
