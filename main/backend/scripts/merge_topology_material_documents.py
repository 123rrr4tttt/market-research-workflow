"""Explicitly migrate one local project's material placements to Documents."""
from __future__ import annotations

import argparse
import json

from functorial_kit import Failure

from app.services.project_retrieval.topology import build_topology_service
from app.services.projects.context import bind_project


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-key", required=True)
    args = parser.parse_args()
    with bind_project(args.project_key):
        result = build_topology_service().merge_material_documents(args.project_key)
    if isinstance(result, Failure):
        print(json.dumps({"code": result.code, "message": result.message, "context": dict(result.context or {})}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
