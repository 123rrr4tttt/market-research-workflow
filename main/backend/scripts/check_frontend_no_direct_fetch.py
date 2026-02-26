from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = ROOT / "frontend"
PATTERN = re.compile(r"\bfetch\s*\(")

# Transitional: first phase only migrated policies pages and client.
PERMITTED_FETCH_FILES = {
    "static/js/app-shell.js",
}
LEGACY_ALLOWLIST = {
    "templates/app.html",
    "templates/backend-dashboard.html",
    "templates/graph.html",
    "templates/data-dashboard.html",
    "templates/market-data-visualization.html",
    "templates/policy-dashboard.html",
    "templates/policy-graph.html",
    "templates/policy-visualization.html",
    "templates/project-management.html",
    "templates/social-media-graph.html",
    "templates/social-media-visualization.html",
    "templates/source-library-management.html",
    "templates/resource-pool-management.html",
}


def iter_targets() -> list[Path]:
    paths = list((FRONTEND_ROOT / "templates").rglob("*.html"))
    paths.extend((FRONTEND_ROOT / "static" / "js").rglob("*.js"))
    return sorted(paths)


def main() -> int:
    violations: list[str] = []
    legacy_hits: list[str] = []
    for path in iter_targets():
        rel = path.relative_to(FRONTEND_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not PATTERN.search(line):
                continue
            if rel in PERMITTED_FETCH_FILES:
                continue
            msg = f"{path.as_posix()}:{lineno}: {line.strip()}"
            if rel in LEGACY_ALLOWLIST:
                legacy_hits.append(msg)
                continue
            violations.append(msg)

    if legacy_hits:
        print("Legacy direct fetch usages (allowed temporarily):", file=sys.stderr)
        for item in legacy_hits:
            print(item, file=sys.stderr)

    if violations:
        print("Direct fetch is forbidden outside the API client.", file=sys.stderr)
        for item in violations:
            print(item, file=sys.stderr)
        return 1

    print("Frontend direct fetch guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

