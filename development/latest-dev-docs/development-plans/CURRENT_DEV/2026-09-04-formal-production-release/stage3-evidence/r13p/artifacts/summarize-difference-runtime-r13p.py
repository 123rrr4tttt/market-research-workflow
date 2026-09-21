#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


OUT = Path("/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/r13p/artifacts")


def sha(name: str) -> str:
    return hashlib.sha256((OUT / name).read_bytes()).hexdigest()


def code(name: str) -> int:
    return int((OUT / name).read_text().strip())


rootfs = json.loads((OUT / "rootfs-difference-domain.json").read_text())
role_differences = {}
for role, record in rootfs["roles"].items():
    actual = [
        {
            "path": item["path"],
            "canonical_sha256": (item.get("canonical") or {}).get("content_sha256"),
            "rebuild_sha256": (item.get("rebuild") or {}).get("content_sha256"),
            "cause_assessment": item["cause_assessment"],
        }
        for item in record["differences"]
        if item["domain"] == "actual_file_content"
    ]
    role_differences[role] = {
        "canonical_image_manifest_digest": record["canonical_image_manifest_digest"],
        "rebuild_image_manifest_digest": record["rebuild_image_manifest_digest"],
        "runtime_config_equal": record["runtime_config_equal"],
        "canonical_inventory_paths": record["inventory"]["canonical_paths"],
        "rebuild_inventory_paths": record["inventory"]["rebuild_paths"],
        "difference_count": record["inventory"]["difference_count"],
        "by_kind": record["inventory"]["by_kind"],
        "by_domain": record["inventory"]["by_domain"],
        "actual_file_content_differences": actual,
    }

backend_boundary_equal = sha("runtime-backend-canonical-entrypoint-boundary.log") == sha("runtime-backend-rebuild-entrypoint-boundary.log")
backend_import_equal = sha("runtime-backend-canonical-import.log") == sha("runtime-backend-rebuild-import.log")
migration_help_equal = sha("runtime-migration-runner-canonical-help.log") == sha("runtime-migration-runner-rebuild-help.log")
frontend_nginx_equal = sha("runtime-frontend-canonical-nginx-test.log") == sha("runtime-frontend-rebuild-nginx-test.log")
frontend_body_equal = sha("runtime-frontend-canonical-body.html") == sha("runtime-frontend-rebuild-body.html")

runtime = {
    "backend": {
        "status": "LIMITED_OBSERVATIONAL_EQUIVALENCE",
        "application_import": {
            "canonical_exit": code("runtime-backend-canonical-import.exit.txt"),
            "rebuild_exit": code("runtime-backend-rebuild-import.exit.txt"),
            "output_equal": backend_import_equal,
            "output_sha256": sha("runtime-backend-canonical-import.log") if backend_import_equal else None,
        },
        "default_entrypoint_dependency_boundary": {
            "canonical_exit": code("runtime-backend-canonical-entrypoint-boundary.exit.txt"),
            "rebuild_exit": code("runtime-backend-rebuild-entrypoint-boundary.exit.txt"),
            "output_equal": backend_boundary_equal,
            "output_sha256": sha("runtime-backend-canonical-entrypoint-boundary.log") if backend_boundary_equal else None,
            "expected_observation": "Both default entrypoints reach PostgreSQL readiness and fail after the configured single retry against an intentionally unreachable task-local endpoint.",
        },
        "success_path_blocker": "A role-complete default startup requires task-owned PostgreSQL, Elasticsearch, and Redis services. Those services were outside this bounded smoke and were not created.",
    },
    "migration-runner": {
        "status": "LIMITED_ENTRYPOINT_EQUIVALENCE",
        "alembic_help": {
            "canonical_exit": code("runtime-migration-runner-canonical-help.exit.txt"),
            "rebuild_exit": code("runtime-migration-runner-rebuild-help.exit.txt"),
            "output_equal": migration_help_equal,
            "output_sha256": sha("runtime-migration-runner-canonical-help.log") if migration_help_equal else None,
        },
        "upgrade_path_blocker": "Running the default `alembic upgrade head` requires a task-owned database and was not included in this bounded smoke.",
    },
    "frontend": {
        "status": "PASS_MINIMAL_RUNTIME_EQUIVALENCE",
        "nginx_config_test": {
            "canonical_exit": code("runtime-frontend-canonical-nginx-test.exit.txt"),
            "rebuild_exit": code("runtime-frontend-rebuild-nginx-test.exit.txt"),
            "output_equal": frontend_nginx_equal,
            "output_sha256": sha("runtime-frontend-canonical-nginx-test.log") if frontend_nginx_equal else None,
        },
        "default_http_root": {
            "canonical_exit": code("runtime-frontend-canonical-http.exit.txt"),
            "rebuild_exit": code("runtime-frontend-rebuild-http.exit.txt"),
            "body_equal": frontend_body_equal,
            "body_sha256": sha("runtime-frontend-canonical-body.html") if frontend_body_equal else None,
        },
    },
}

summary = {
    "schema": "mrw.stage3.difference-domain-runtime-equivalence.r13p.v1",
    "authoritative": False,
    "candidate": {
        "commit": "342d3b3c35ad987c47990da6ac550dfe936d4818",
        "tree": "3f87e85dce02b312e445c657c238c11c6809850e",
    },
    "source_artifacts": {
        "candidate_commit": "3669d4ddc19fb722058976b4e1f05e99eccfe96e",
        "reuse_basis": "Exact Git-tree equality for main/backend, src, and main/frontend-modern between r13o and r13p.",
        "platform": "linux/arm64",
    },
    "difference_domain": role_differences,
    "runtime_equivalence": runtime,
    "conclusion": {
        "status": "LIMITED_NOT_STAGE3_NON_BIT_FOR_BIT_EXCEPTION",
        "reason": "Observed entrypoint behavior is equal within the bounded smokes, but backend and migration success paths were not exercised, two psutil shared-object files differ byte-for-byte for an unknown build cause, and no r13p-bound signed provenance exists.",
        "reproducibility_claim": False,
        "full_runtime_equivalence_claim": False,
    },
    "resource_cleanup": {
        "task_container_names": "removed",
        "task_image_tags": "removed",
        "builders": "not created or restored",
    },
}
(OUT / "difference-domain-runtime-equivalence.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

members = sorted(
    path
    for path in OUT.iterdir()
    if path.is_file()
    and (
        path.name.startswith("runtime-")
        or path.name.startswith("rootfs-difference-domain")
        or path.name in {"difference-domain-runtime-equivalence.json", "compare-oci-rootfs-r13p.py", "run-runtime-smokes-r13p.sh", "summarize-difference-runtime-r13p.py"}
    )
    and path.name != "SHA256SUMS.difference-runtime"
)
(OUT / "SHA256SUMS.difference-runtime").write_text(
    "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in members)
)
