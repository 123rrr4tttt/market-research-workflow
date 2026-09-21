#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


OUT = Path("/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13p/artifacts")
SOURCE = Path("/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13o/artifacts")
ROLES = ("backend", "migration-runner")
PHASES = ("canonical", "rebuild")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_elf_log(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    current: dict | None = None
    for line in path.read_text().splitlines():
        if line.startswith("FILE="):
            file_path = line.removeprefix("FILE=")
            current = {"path": file_path, "sections": {}}
            records[Path(file_path).name] = current
        elif current is not None and re.fullmatch(r"[0-9a-f]{64}  /usr/local/lib/.*", line):
            current["file_sha256"] = line.split()[0]
        elif current is not None and "Build ID:" in line:
            current["gnu_build_id"] = line.rsplit("Build ID:", 1)[1].strip()
        elif current is not None and line.startswith("SECTION="):
            match = re.match(r"SECTION=(\S+) (ABSENT|[0-9a-f]{64})", line)
            if match:
                current["sections"][match.group(1)] = None if match.group(2) == "ABSENT" else match.group(2)
        elif current is not None and line.startswith("/tmp/pip-install-"):
            current["embedded_pip_build_path"] = line
    return records


def wheel_observation(role: str, phase: str) -> dict:
    log_path = SOURCE / f"{phase}-{role}-build.log"
    matches = re.findall(
        r"Created wheel for psutil: filename=(\S+) size=(\d+) sha256=([0-9a-f]{64})",
        log_path.read_text(errors="replace"),
    )
    if not matches:
        return {"found": False, "build_log_sha256": sha(log_path)}
    filename, size, digest = matches[-1]
    return {
        "found": True,
        "filename": filename,
        "bytes": int(size),
        "sha256": digest,
        "build_log_sha256": sha(log_path),
    }


archive_hashes = {
    "backend": {
        "canonical": "89d18f8e22399646306207867037fc5297ca732e10838b7a7e744a6ab20303df",
        "rebuild": "aa2ba679edbc1ede9515ffbb5544b5a680ed7b62cd6aee6cabe27cd85cd49f45",
    },
    "migration-runner": {
        "canonical": "2c94ffbca65c6f4492d1691f56924c1de19f71f2ef162ba07cf982f1930282a8",
        "rebuild": "5771697fd4dd65ac1b372352b694af1c0c22c2a284aff06fef27fec19de946b1",
    },
}

roles = {}
for role in ROLES:
    parsed = {
        phase: parse_elf_log(OUT / f"psutil-elf-{role}-{phase}.log")
        for phase in PHASES
    }
    binaries = {}
    for binary in sorted(parsed["canonical"]):
        canonical = parsed["canonical"][binary]
        rebuild = parsed["rebuild"][binary]
        sections = sorted(set(canonical["sections"]) | set(rebuild["sections"]))
        equal_sections = [
            section
            for section in sections
            if canonical["sections"].get(section) == rebuild["sections"].get(section)
            and canonical["sections"].get(section) is not None
        ]
        different_sections = [
            section
            for section in sections
            if canonical["sections"].get(section) != rebuild["sections"].get(section)
        ]
        binaries[binary] = {
            "canonical": canonical,
            "rebuild": rebuild,
            "full_file_equal": canonical.get("file_sha256") == rebuild.get("file_sha256"),
            "equal_inspected_sections": equal_sections,
            "different_inspected_sections": different_sections,
            "classification": "EPHEMERAL_PIP_BUILD_PATH_IN_DWARF_AND_DERIVED_GNU_BUILD_ID",
            "evidence_boundary": "Inspected runtime code/data/symbol/unwind sections match; .debug_line_str, embedded pip build path, and GNU build-id differ. No claim is made about sections not inspected by this bounded check.",
        }
    roles[role] = {
        "input_archives": {
            phase: {
                "path": str(SOURCE / phase / f"{role}.oci.tar"),
                "sha256": archive_hashes[role][phase],
                "load_exit_code": int((OUT / f"psutil-elf-{role}-{phase}-load.exit.txt").read_text()),
                "inspection_exit_code": int((OUT / f"psutil-elf-{role}-{phase}.exit.txt").read_text()),
            }
            for phase in PHASES
        },
        "psutil_wheel_build_log_observation": {
            phase: wheel_observation(role, phase) for phase in PHASES
        },
        "binaries": binaries,
    }

payload = {
    "schema": "mrw.stage3.psutil-elf-difference-supplement.r13p.v1",
    "authoritative": False,
    "candidate": {
        "commit": "342d3b3c35ad987c47990da6ac550dfe936d4818",
        "tree": "3f87e85dce02b312e445c657c238c11c6809850e",
    },
    "source_artifact_candidate": {
        "commit": "3669d4ddc19fb722058976b4e1f05e99eccfe96e",
        "reuse_basis": "main/backend and src Git trees are byte-identical between r13o and r13p",
    },
    "package": {
        "requirement": "psutil==5.9.8",
        "source_observation": "pip downloaded psutil-5.9.8.tar.gz and independently built cp311-abi3-linux_aarch64 wheels in each no-cache build",
        "compiler_comment": "GCC: (Debian 14.2.0-19) 14.2.0",
    },
    "roles": roles,
    "assessment": {
        "result": "ROOT_CAUSE_BOUNDED",
        "runtime_section_observation": "All inspected .text, .rodata, .data, unwind, dynamic symbol/string, and main DWARF sections match for each canonical/rebuild pair.",
        "byte_difference_observation": "Each pair has a distinct ephemeral /tmp/pip-install-* source path in .debug_line_str and a distinct derived GNU build-id; full ELF hashes and wheel hashes differ.",
        "stage3_status": "REBUILD_REQUIRED",
        "still_blocks_stage3": True,
        "reason": "The images remain non-bit-for-bit reproducible. Bounded runtime-section equality does not replace the contract requirement for a signed provenance plus complete runtime-equivalence exception, and r13p-bound signed provenance is absent.",
    },
    "bounded_repair_package": {
        "owner": "Stage1/2 repair owner",
        "surface": "main/backend/Dockerfile:23 and main/backend/requirements.txt:31",
        "required_change": "Make the linux/arm64 psutil artifact deterministic before both role image builds: preferably consume one hash-pinned prebuilt wheel, or build one wheel in a deterministic fixed path with compiler debug/file prefix mapping and reuse that exact wheel. Do not strip or mutate the already-built Stage3 artifacts.",
        "acceptance": [
            "canonical and rebuild psutil wheel SHA256 values match",
            "both psutil shared-object SHA256 values match for backend and migration-runner",
            "backend and migration-runner image manifest digests match across clean builders",
            "SBOM, provenance, scan, and role-specific runtime checks are regenerated for the successor candidate",
        ],
    },
    "collection_limitations": [
        "The r13o evidence lane previously observed a duplicate writer; archive content hashes and OCI validation are used as inputs, while build-log-to-archive attribution retains that limitation.",
        "The ELF inspection reads existing images only and does not rebuild, strip sections, or alter candidate bytes.",
    ],
}

summary_path = OUT / "psutil-elf-difference-supplement.json"
summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

members = sorted(
    path
    for path in OUT.iterdir()
    if path.is_file()
    and (
        path.name.startswith("psutil-elf-")
        or path.name in {"inspect-psutil-elf-r13p.sh", "summarize-psutil-elf-r13p.py"}
    )
    and path.name != "SHA256SUMS.psutil-elf-supplement"
)
(OUT / "SHA256SUMS.psutil-elf-supplement").write_text(
    "".join(f"{sha(path)}  {path.name}\n" for path in members)
)
