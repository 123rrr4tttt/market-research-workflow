# Local Index Runtime Contract Evidence

日期：2026-05-22 PST  
分支：`codex/devdocs-local-index-runtime-artifacts`  
工作树：`/Users/wangyiliang/market-research-workflow.worktrees/local-index-runtime-artifacts`

## Scope

本证据包收口 `local_index` 的 `mode=keyword|vector|hybrid` 文档证据和 CURRENT_DEV 状态。并行 A 线已在同一集成批次补上 canonical runtime smoke：[`../local-index-lancedb-runtime-smoke/2026-05-22/README.md`](../../local-index-lancedb-runtime-smoke/2026-05-22/README.md)。

输入：

- [`CURRENT_DEV/2026-05-14-global-vectorization-general-foundation`](../../../development-plans/CURRENT_DEV/2026-05-14-global-vectorization-general-foundation/INDEX.md)
- [`backend-core/main/MERGED_BACKEND_CORE.md`](../../../backend-core/main/MERGED_BACKEND_CORE.md)
- [`dev-docs-folder-audit-2026-05-22/README.md`](../../dev-docs-folder-audit-2026-05-22/README.md)
- `main/backend/app/services/local_index/`

## Current Contract Snapshot

| Layer | Current fact | Evidence |
|---|---|---|
| schema | `LocalIndexQuery.mode` accepts `keyword`, `vector`, `hybrid`; unknown values normalize to `keyword`. | `main/backend/app/services/local_index/schema.py`; `tests/unit/test_local_index_service_unittest.py::test_query_mode_contract_is_exported_and_normalized` |
| service | `LocalIndexService.search()` normalizes supported modes before adapter dispatch and short-circuits empty query/project input. | `main/backend/app/services/local_index/service.py`; `tests/unit/test_local_index_service_unittest.py::test_service_preserves_supported_modes_and_normalizes_unknown_mode` |
| adapter | `LanceDBLocalIndexAdapter.search()` dispatches keyword to FTS, vector to vector search, and hybrid to LanceDB hybrid when supported; non-keyword runtime errors fall back to keyword with trace fields. | `main/backend/app/services/local_index/adapters/lancedb_adapter.py`; `tests/unit/test_local_index_service_unittest.py::test_lancedb_adapter_dispatches_keyword_vector_and_hybrid_modes` |
| result | `LocalIndexSearchResult.to_dict()` exposes `retrieval_mode`, `retrieval_family`, and `trace`. | `main/backend/app/services/local_index/schema.py`; `tests/unit/test_local_index_service_unittest.py::test_service_indexes_material_chunks_without_source_library_schema` |

## Runtime Smoke

The local optional dependency is currently importable in this worktree:

```text
lancedb_available=True
```

Smoke command, from `main/backend`:

```bash
.venv311/bin/python - <<'PY'
from __future__ import annotations

import json
import tempfile

from app.services.local_index import LocalIndexChunk, LocalIndexQuery
from app.services.local_index.adapters import LanceDBLocalIndexAdapter, is_lancedb_available

summary: dict[str, object] = {"lancedb_available": is_lancedb_available()}
chunks = [
    LocalIndexChunk(chunk_id="c_robotics", document_id="d_robotics", project_id="demo_proj", source_id="source_a", title="Robotics policy", content="Embodied AI robotics policy material chunk with safety evidence."),
    LocalIndexChunk(chunk_id="c_energy", document_id="d_energy", project_id="demo_proj", source_id="source_b", title="Energy policy", content="Energy market benchmark material outside robotics."),
]
with tempfile.TemporaryDirectory(prefix="mrw-local-index-smoke-") as tmpdir:
    adapter = LanceDBLocalIndexAdapter(db_path=tmpdir, table_name="chunks")
    summary["upsert"] = adapter.upsert_chunks(chunks)
    modes: dict[str, object] = {}
    for mode in ["keyword", "vector", "hybrid"]:
        try:
            results = adapter.search(LocalIndexQuery(query="robotics policy", project_id="demo_proj", mode=mode, top_k=2))
            modes[mode] = {
                "count": len(results),
                "ids": [r.chunk_id for r in results],
                "retrieval_modes": [r.retrieval_mode for r in results],
                "trace": results[0].trace if results else {},
                "scores_present": [r.score is not None for r in results],
            }
        except Exception as exc:
            modes[mode] = {"error": exc.__class__.__name__, "message": str(exc)}
    summary["modes"] = modes
print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
PY
```

Observed result before the Wave2 A runtime fix:

```json
{
  "lancedb_available": true,
  "modes": {
    "hybrid": {
      "count": 2,
      "ids": ["c_energy", "c_robotics"],
      "retrieval_modes": ["keyword", "keyword"],
      "scores_present": [true, true],
      "trace": {
        "adapter": "lancedb",
        "executed_mode": "keyword",
        "fallback_from": "hybrid",
        "fallback_reason": "ValueError",
        "query_family": "local_material",
        "requested_mode": "hybrid"
      }
    },
    "keyword": {
      "count": 2,
      "ids": ["c_energy", "c_robotics"],
      "retrieval_modes": ["keyword", "keyword"],
      "scores_present": [true, true],
      "trace": {
        "adapter": "lancedb",
        "executed_mode": "keyword",
        "query_family": "local_material",
        "requested_mode": "keyword"
      }
    },
    "vector": {
      "count": 2,
      "ids": ["c_energy", "c_robotics"],
      "retrieval_modes": ["vector", "vector"],
      "scores_present": [false, false],
      "trace": {
        "adapter": "lancedb",
        "executed_mode": "vector",
        "query_family": "local_material",
        "requested_mode": "vector"
      }
    }
  },
  "upsert": {
    "adapter": "lancedb",
    "chunk_count": 2,
    "created_table": true,
    "ok": true
  }
}
```

Interpretation:

- `keyword` runtime smoke passes as FTS dispatch with result trace.
- `vector` runtime smoke dispatches and returns `retrieval_mode=vector`; this proves runtime reachability, not semantic quality or stable ranking.
- This local B-lane observation is superseded by Wave2 A's canonical runtime smoke, where `keyword`, `vector`, and `hybrid` all return the expected top row without fallback.

## Closure State

| Item | State | Reason |
|---|---|---|
| `mode=keyword|vector|hybrid` schema/service/result contract | closed for current unit/runtime evidence | Contract fields are exported, normalized, serialized, and covered by unit tests. |
| Optional LanceDB dependency boundary | closed for current evidence | `is_lancedb_available()` is explicit and constructor raises when dependency is absent; this worktree also proves dependency-present runtime construction. |
| Keyword runtime smoke | closed for current evidence | Existing adapter can upsert and execute FTS against LanceDB. |
| Vector runtime smoke | closed for current smoke | Wave2 A proves the runtime path dispatches and returns the expected top row; score/ranking quality and embedding semantics still need benchmark coverage. |
| Hybrid runtime smoke | closed for current smoke | Wave2 A proves true hybrid execution without keyword fallback in the optional dependency environment. |
| Full vectorization foundation topic | not closed | Unified vector object schema, `project_id`/`project_key` mapping, Qdrant/pgvector/evidence contract alignment, embedding/ranking benchmark, and Agent/WritingWorkbench integration remain open. |

## Repeat Commands

From repository root:

```bash
git diff --check
python3 - <<'PY'
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

root = Path.cwd()
tracked = subprocess.check_output(["git", "diff", "--name-only", "HEAD", "--", "development/latest-dev-docs"], text=True).splitlines()
untracked = subprocess.check_output(["git", "ls-files", "--others", "--exclude-standard", "--", "development/latest-dev-docs"], text=True).splitlines()
files = [root / line for line in tracked + untracked if line.endswith(".md")]
link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
errors: list[str] = []
for path in files:
    text = path.read_text(encoding="utf-8")
    for match in link_re.finditer(text):
        raw = match.group(1).split("#", 1)[0].strip()
        if not raw or raw.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = (path.parent / raw).resolve()
        if not target.exists():
            errors.append(f"{path.relative_to(root)} -> {raw}")
if errors:
    print("BROKEN_DOC_LINKS")
    print("\n".join(errors))
    raise SystemExit(1)
print(f"ALL_CHANGED_DOC_LINKS_OK checked={len(files)}")
PY
cd main/backend && .venv311/bin/python -m pytest tests/unit/test_local_index_service_unittest.py
```

## Validation

```text
git diff --check
PASS

changed-doc link check
ALL_CHANGED_DOC_LINKS_OK checked=9

cd main/backend && .venv311/bin/python -m pytest tests/unit/test_local_index_service_unittest.py
7 passed in 0.07s
```

## Follow-up Handoff

- A runtime lane now supports true LanceDB hybrid smoke for the installed version; next work should extend it into embedding/ranking benchmark evidence.
- Runtime cleanup can remove duplicate `LOCAL_INDEX_QUERY_MODES` / `normalize_local_index_mode` definitions in `schema.py`; this B lane did not edit runtime code to avoid cross-lane conflicts.
- CURRENT_DEV should remain `partial`, not archived, until full vectorization foundation contracts, benchmark quality, and Agent/WritingWorkbench evidence alignment are closed.
