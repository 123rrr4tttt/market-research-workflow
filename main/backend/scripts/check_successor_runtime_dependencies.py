from __future__ import annotations

import argparse
import ast
import json
from collections import deque
from pathlib import Path

LAYERS = ("research", "language", "capabilities", "runtime")
_LAYER_INDEX = {name: index for index, name in enumerate(LAYERS)}

# Explicitly public shared modules inside the capabilities layer.  Capability
# modules may import these contracts/profiles/catalog/codec helpers, but must
# not import another capability's owned implementation module.
CAPABILITY_SHARED_MODULES = frozenset(
    {
        "contracts",
        "profiles",
        "catalog",
        "checksum",
        "codecs",
        "agent_core_c6_common",
        "ingest_c7_common",
        "c8_common",
    }
)

PURE_FORBIDDEN = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "celery",
    "redis",
    "openai",
    "langchain",
    "app.settings",
    "app.api",
    "app.services",
    "app.models",
)
RUNTIME_FORBIDDEN = (
    "sqlalchemy",
    "celery",
    "redis",
    "app.successor_runtime.substrate",
    "app.successor_runtime.adapters",
    "app.services",
    "app.api",
)
SUCCESSOR_FORBIDDEN = (
    "app.services.workflow_graph",
    "app.services.source_library",
    "app.services.collect_runtime",
    "app.services.agent_batch",
    "app.services.agent_sessions",
    "app.services.agent_core",
    "app.services.ingest",
    "app.services.writing",
    "app.models",
)

# Effect facilities that runtime may reach only through runtime.ports.
EFFECT_FACILITY_PREFIXES = (
    "app.successor_runtime.substrate",
    "app.successor_runtime.adapters",
    "successor_runtime.substrate",
    "successor_runtime.adapters",
    "substrate",
    "adapters",
)

_PACKAGE_PREFIXES = ("app.successor_runtime.", "successor_runtime.")


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    parts = list(relative.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _layer_of(module: str) -> str | None:
    if not module:
        return None
    head = module.split(".", 1)[0]
    return head if head in _LAYER_INDEX else None


def _normalize_target(module: str) -> str:
    for prefix in _PACKAGE_PREFIXES:
        if module.startswith(prefix):
            return module[len(prefix) :]
    return module


def _resolve_target(importer: str, imported: str) -> str | None:
    if not imported.startswith("."):
        return imported
    level = len(imported) - len(imported.lstrip("."))
    tail = imported[level:]
    parts = importer.split(".") if importer else []
    if level > len(parts):
        return None
    base = parts[: len(parts) - level]
    target = ".".join(base + ([tail] if tail else []))
    return target or None


def _imports(path: Path) -> list[tuple[int, str, bool]]:
    """Return ``(lineno, imported, deferred)`` for every import statement.

    ``deferred`` marks imports lexically nested inside function bodies.
    Deferred imports still participate in boundary and capability-isolation
    rules; only eager (module/class-level) imports can create import-time
    cycles, so cycle edges are built from eager imports only.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str, bool]] = []

    def visit(node: ast.AST, deferred: bool) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            deferred = True
        if isinstance(node, ast.Import):
            found.extend((alias.lineno, alias.name, deferred) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            prefix = "." * node.level
            if node.level == 0:
                found.append((node.lineno, base, deferred))
            elif base:
                found.append((node.lineno, prefix + base, deferred))
            else:
                found.extend(
                    (alias.lineno, prefix + alias.name, deferred)
                    for alias in node.names
                )
        for child in ast.iter_child_nodes(node):
            visit(child, deferred)

    visit(tree, False)
    return found


def _matches(imported: str, prefixes: tuple[str, ...]) -> bool:
    return any(
        imported == prefix or imported.startswith(prefix + ".") for prefix in prefixes
    )


def _owner_claims(path: Path) -> list[tuple[str, str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    claims: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords or []:
            if keyword.arg not in ("canonical_owner", "owner_capability_id"):
                continue
            value = keyword.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                claims.append((keyword.arg, value.value, node.lineno))
    return claims


def _find_cycles(
    edges: dict[str, frozenset[str]],
) -> list[tuple[str, ...]]:
    indegree = {node: 0 for node in edges}
    for targets in edges.values():
        for target in targets:
            if target in indegree:
                indegree[target] += 1
    queue = deque(node for node, count in indegree.items() if count == 0)
    removed: set[str] = set()
    while queue:
        node = queue.popleft()
        removed.add(node)
        for target in edges[node]:
            if target in removed:
                continue
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    remaining = [node for node in edges if node not in removed]
    cycles: list[tuple[str, ...]] = []
    visited: set[str] = set()
    for start in remaining:
        if start in visited:
            continue
        path: list[str] = []
        current = start
        while True:
            if current in path:
                cycle = tuple(path[path.index(current) :] + [current])
                cycles.append(cycle)
                visited.update(cycle)
                break
            path.append(current)
            candidates = [
                n for n in edges[current] if n in remaining and n not in visited
            ]
            if not candidates:
                break
            current = candidates[0]
    return cycles


def _is_capability_direct_import(
    importer: str,
    target: str,
    nodes: set[str],
) -> bool:
    """True when one capability module imports another's owned implementation."""
    if importer == "capabilities":
        # The package facade is the canonical public aggregator.
        return False
    if target == "capabilities":
        # Importing the package surface (re-exports) is the public facade.
        return False
    if target not in nodes:
        return False
    target_head = target.split(".", 1)[1] if "." in target else target
    return target_head not in CAPABILITY_SHARED_MODULES


def check(root: Path) -> dict[str, object]:
    violations: list[dict[str, object]] = []
    deferred_imports_scanned = 0
    files = sorted(path for path in root.rglob("*.py"))
    nodes = {_module_name(path, root) for path in files}

    for path in files:
        relative = path.relative_to(root)
        importer = _module_name(path, root)
        source_layer = _layer_of(importer)
        for lineno, imported, deferred in _imports(path):
            if deferred:
                deferred_imports_scanned += 1
            target = _resolve_target(importer, imported)
            if target is None:
                continue
            normalized = _normalize_target(target)
            target_layer = _layer_of(normalized)

            if source_layer is not None and target_layer is not None:
                if _LAYER_INDEX[target_layer] > _LAYER_INDEX[source_layer]:
                    violations.append(
                        {
                            "path": str(relative),
                            "line": lineno,
                            "code": "LAYER_DIRECTION",
                            "import": imported,
                            "message": (
                                f"{source_layer} must not import outer layer "
                                f"{target_layer}"
                            ),
                        }
                    )
                elif (
                    source_layer == "capabilities"
                    and target_layer == "capabilities"
                    and _is_capability_direct_import(importer, normalized, nodes)
                ):
                    violations.append(
                        {
                            "path": str(relative),
                            "line": lineno,
                            "code": "CAPABILITY_DIRECT_IMPORT",
                            "import": imported,
                            "message": (
                                "capabilities must not import another capability "
                                "implementation; only shared public "
                                f"{sorted(CAPABILITY_SHARED_MODULES)} modules are allowed"
                            ),
                        }
                    )
                continue

            if source_layer == "runtime" and _matches(
                normalized, EFFECT_FACILITY_PREFIXES
            ):
                violations.append(
                    {
                        "path": str(relative),
                        "line": lineno,
                        "code": "RUNTIME_ONLY_PORTS",
                        "import": imported,
                        "message": (
                            "runtime must reach substrate/adapters only through "
                            "runtime.ports"
                        ),
                    }
                )
                continue

            forbidden = SUCCESSOR_FORBIDDEN
            if source_layer in ("research", "language", "capabilities"):
                forbidden += PURE_FORBIDDEN
            elif source_layer == "runtime":
                forbidden += RUNTIME_FORBIDDEN
            if _matches(target, forbidden):
                violations.append(
                    {
                        "path": str(relative),
                        "line": lineno,
                        "code": "FORBIDDEN_IMPORT",
                        "import": imported,
                        "message": f"forbidden dependency: {imported}",
                    }
                )

    edges: dict[str, frozenset[str]] = {}
    for path in files:
        importer = _module_name(path, root)
        targets: set[str] = set()
        for _, imported, deferred in _imports(path):
            if deferred:
                continue
            target = _resolve_target(importer, imported)
            if target is None:
                continue
            normalized = _normalize_target(target)
            if _layer_of(normalized) is not None and normalized in nodes:
                targets.add(normalized)
        edges[importer] = frozenset(targets)

    for cycle in _find_cycles(edges):
        path = cycle[0].replace(".", "/") + ".py"
        violations.append(
            {
                "path": path,
                "line": None,
                "code": "IMPORT_CYCLE",
                "import": None,
                "message": "module import cycle: " + " -> ".join(cycle),
            }
        )

    claims_by_owner: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for path in files:
        relative = path.relative_to(root)
        if relative.parts[0] != "capabilities":
            continue
        for field, value, lineno in _owner_claims(path):
            claims_by_owner.setdefault((field, value), []).append(
                (str(relative), lineno)
            )
    for (field, value), occurrences in sorted(claims_by_owner.items()):
        files_with_claim = {occurrence[0] for occurrence in occurrences}
        if len(files_with_claim) <= 1:
            continue
        violations.append(
            {
                "path": min(files_with_claim),
                "line": None,
                "code": "DUPLICATE_CANONICAL_CLASS_OWNER",
                "import": None,
                "message": (
                    f"canonical class owner {field}={value!r} claimed by multiple "
                    f"capability files: {', '.join(sorted(files_with_claim))}"
                ),
            }
        )

    return {
        "schema": "mrw.successor_runtime.dependency_lint.v1",
        "ok": not violations,
        "files_checked": len(files),
        "function_local_imports_scanned": deferred_imports_scanned,
        "capability_shared_modules_allowed": sorted(CAPABILITY_SHARED_MODULES),
        "violations": violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "app/successor_runtime",
    )
    args = parser.parse_args()
    report = check(args.root.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
