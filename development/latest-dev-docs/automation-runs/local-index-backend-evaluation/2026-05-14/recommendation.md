# Local Index Backend Recommendation

## Boundary

`source_library` remains the specific source database. Local index backends are downstream indexes over fetched documents/material chunks.

## First Run Evidence

- Dataset benchmarked with the same 30 queries across available local candidates.
- sqlite_fts_baseline: queries=30, ok=30, p50_ms=0.15, max_ms=0.97, median_top_k=10.0
- lancedb_fts: queries=30, ok=30, p50_ms=1.83, max_ms=26.25, median_top_k=10.0

## Recommendation

1. First implementation candidate: LanceDB, because the isolated client can build a local table, create an FTS index, apply `project_id` filters, and run the same query set without changing project dependencies.
2. Second implementation candidate: Qdrant, because it is the strongest AI-native retrieval backend for dense/sparse hybrid search once embedding and sparse-model pipelines are available.
3. Keep YaCy local as a baseline only. It proved local push/search, but it is not the best long-term AI-agent retrieval architecture.
4. Defer OpenSearch and Vespa until the project needs larger-scale ranking infrastructure.

## Current Environment

- LanceDB: installed=True, entered_benchmark=True
- Qdrant: installed=False, entered_benchmark=False
- Meilisearch: installed=False, entered_benchmark=False
- Typesense: installed=False, entered_benchmark=False
- Weaviate: installed=False, entered_benchmark=False
- SQLite FTS5 baseline: installed=True, entered_benchmark=True
- YaCy local: installed=None, entered_benchmark=False
