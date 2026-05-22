# Clue Chain Investigation Tool Plan

Date: 2026-05-22
Status: `not_closed` / `executing` / Wave5 implementation in progress

## 1. Goal

Build a mechanical clue-tracing tool that starts from structured graph data, expands selected nodes into new searches, records every pivot, and feeds the resulting evidence back into the project graph.

The new domain object is `链条` / `Chain`: a durable investigation path that connects seed nodes, search actions, returned evidence, derived nodes, and stop decisions.

This plan is grounded in external best practices rather than invented from scratch:

- OSINT methodology: plan, collect, analyse, report; preserve provenance and chain back to sources.
- Maltego-style graph work: represent clues as entities, use transforms to pivot from one entity to related entities, and automate repeated transform sequences with machines.
- GraphRAG-style retrieval: combine structured graph entities with raw text, expand through related entities/relationships, rank and filter candidate context, and generate follow-up questions for deeper exploration.

## 2. Source-Derived Design Rules

| Rule | Implementation meaning | External basis |
|---|---|---|
| Preserve origin before pivoting | Every URL/document/result used by a chain hop stores original URL, capture time, provider, archive/hash when available, and query/action parameters. | Bellingcat stresses original-source transparency and reproducible working; OSINT Academy emphasizes provenance, timestamps, hashes, and chain of custody. |
| Treat search results as leads, not facts | External search and source-library hits enter as `lead` evidence until corroborated or promoted. | OSINT collection guidance distinguishes secondary reporting from primary evidence and requires tracing claims back to origin. |
| Model each clue as a typed entity | Graph nodes must have type, value, properties, aliases, confidence, and source refs before they can be expanded. | Maltego defines entities as graph nodes with type/value/properties and transforms as entity-in, entity-out expansion. |
| Make expansion explicit and replayable | Each hop records transform kind, input node, query, provider, result set, filters, dedupe decisions, and produced nodes/edges. | Maltego transforms and machines provide the reference pattern for repeatable graph pivots and automated transform sequences. |
| Use graph-local context first, then broaden | Start from selected graph entities and adjacent relationships, then call source-library or external search only when novelty/coverage requires it. | Microsoft GraphRAG local search uses extracted entities as access points into graph neighborhoods, linked text units, relationships, covariates, and reports. |
| Use iterative follow-up questions | Chain expansion can generate candidate follow-up questions/searches, but each candidate must be budgeted and inspectable. | GraphRAG exposes question generation and DRIFT-style local search broadened with community context. |
| Dedupe and canonicalize aggressively | Same entity from graph, source-library, and web search must merge through alias/entity-resolution before creating more hops. | GraphRAG pattern guidance highlights entity disambiguation and schema-defined extraction to keep the graph clean. |
| Keep ethics and harm gates in runtime | Sensitive entities, private-person data, leaked data, and potentially harmful publication paths require explicit operator approval. | Bellingcat data-collection principles require verification, harm minimization, correction paths, and protection of vulnerable people. |

## 3. Core Object: Chain

`Chain` is not just a tag on graph nodes. It is the audit object that makes the investigation path replayable.

```json
{
  "chain_id": "chain_20260522_001",
  "project_key": "demo_proj",
  "title": "EV policy supplier trace",
  "status": "draft|running|paused|blocked|closed",
  "objective": "Trace companies, policies, and sources connected to seed node X",
  "seed_node_ids": ["graph_node_123"],
  "frontier_node_ids": ["graph_node_456"],
  "max_depth": 3,
  "max_hops": 25,
  "confidence_threshold": 0.62,
  "created_by": "user|agent|workflow_graph",
  "provenance_policy": "archive_before_pivot",
  "privacy_policy": "public_sources_only",
  "created_at": "2026-05-22T00:00:00Z",
  "updated_at": "2026-05-22T00:00:00Z"
}
```

Related records:

- `ChainHop`: one expansion action from a node or subgraph.
- `ChainEvidence`: raw result, archived URL, local source row, or document chunk cited by a hop.
- `ChainCandidate`: proposed next search or node expansion before it is accepted into the frontier.
- `ChainDecision`: human or agent decision to promote, reject, pause, merge, or close a candidate.
- `ChainEdge`: typed relation created or strengthened by a hop.

## 4. Three Runtime Links

### 4.1 Agent Tool Link

Purpose:

- Let project agents call a controlled `chain.expand` tool rather than improvising search loops.
- Preserve the same event trail used by `agent_batch` and `agent_sessions`.

Required tool shape:

```json
{
  "tool": "chain.expand",
  "chain_id": "chain_20260522_001",
  "input_node_id": "graph_node_123",
  "expansion_mode": "graph_neighbors|external_search|source_library_search|agent_subtask",
  "budget": {"depth_remaining": 2, "max_results": 12},
  "operator_policy": {"require_approval_for_sensitive": true}
}
```

Implementation notes:

- `agent_batch` should enqueue chain hops as first-class items.
- `agent_sessions` should stream hop events: `planned`, `search_started`, `evidence_collected`, `node_promoted`, `blocked`, `closed`.
- Agent output must not directly mutate graph nodes without passing through `ChainDecision`.

### 4.2 External Search Link

Purpose:

- Use external providers as controlled clue discovery, not as unbounded browsing.
- Support SearXNG / YaCy / provider adapters already being isolated in the project.

Expansion flow:

1. Build a search brief from the current node: entity type, aliases, time window, geography, source preference, exclusion terms.
2. Run external provider query with trace fields: provider, query, params, result rank, title, snippet, URL.
3. Store every result as `ChainEvidence(status=lead)`.
4. Extract candidate entities and relationships from selected results.
5. Rank by novelty, provenance quality, source diversity, and relationship usefulness.
6. Promote only reviewed candidates into graph nodes or chain frontier.

Stop conditions:

- no new canonical entities after dedupe,
- provider quality below threshold after retry,
- source volatility or privacy policy requires operator decision,
- max depth / max hops reached.

### 4.3 Source-Library Search Link

Purpose:

- Search already curated project/source-library material before expanding to the public web.
- Reuse local index, source entries, search templates, and source-library capability profiles.

Expansion flow:

1. Query source-library materials by canonical entity value and aliases.
2. Query pinned search contracts for relevant source entries.
3. Use local index hits as evidence candidates with source refs and document/chunk IDs.
4. Promote relationships only when source-library evidence is enough, or send unresolved gaps to external search.

Source-library evidence must preserve:

- source item key,
- channel/source scope,
- document ID / chunk ID,
- query text,
- local index mode where applicable,
- parser/search-template profile used.

## 5. Expansion Algorithm

The first implementation should be a deterministic queue, not a fully autonomous long-horizon agent.

```text
create chain from selected graph nodes
normalize seed entities
enqueue seed nodes into frontier
while budget remains:
  pop highest-priority frontier node
  build candidate expansions from graph/source-library/external-search policies
  run allowed expansion actions
  archive/store evidence before analysis
  extract candidate entities and relations
  canonicalize and dedupe candidates
  score novelty, confidence, and source quality
  require review for sensitive/high-impact promotions
  write accepted nodes/edges/evidence refs
  update chain frontier
close or pause with explicit blocker
```

Priority score:

```text
priority =
  0.30 * node_relevance
+ 0.25 * evidence_gap
+ 0.20 * novelty
+ 0.15 * source_reliability
+ 0.10 * graph_centrality
- privacy_risk_penalty
- duplicate_penalty
```

## 6. Data Model Draft

Minimum backend tables or JSON-store records:

| Object | Required fields | Notes |
|---|---|---|
| `clue_chains` | `chain_id`, `project_key`, `title`, `objective`, `status`, `seed_node_ids`, `frontier_node_ids`, `policy_json`, timestamps | top-level audit object |
| `clue_chain_hops` | `hop_id`, `chain_id`, `depth`, `input_node_id`, `mode`, `tool_name`, `query_json`, `status`, `started_at`, `finished_at` | every expansion attempt |
| `clue_chain_evidence` | `evidence_id`, `chain_id`, `hop_id`, `source_kind`, `source_ref`, `url`, `archive_url`, `hash`, `captured_at`, `status` | lead/finding/corroborated/rejected |
| `clue_chain_candidates` | `candidate_id`, `chain_id`, `hop_id`, `entity_type`, `value`, `aliases`, `score`, `decision_status` | review queue before promotion |
| `clue_chain_decisions` | `decision_id`, `chain_id`, `candidate_id`, `actor`, `decision`, `reason`, `created_at` | human/agent audit |

Initial storage can follow the existing project JSON/SQLite pattern. Do not introduce a graph database dependency in the first cut.

## 7. API Surface Draft

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/clue-chains` | create chain from graph seed nodes |
| `GET` | `/api/v1/clue-chains` | list chains by project/status |
| `GET` | `/api/v1/clue-chains/{chain_id}` | load chain, hops, frontier, evidence summary |
| `POST` | `/api/v1/clue-chains/{chain_id}/expand` | run one bounded expansion |
| `POST` | `/api/v1/clue-chains/{chain_id}/candidates/{candidate_id}/decision` | promote/reject/merge/pause candidate |
| `POST` | `/api/v1/clue-chains/{chain_id}/close` | close with final status and blockers |

Response envelope should follow the existing `status/data/error/meta` style.

## 8. Frontend Surface

GraphPage additions:

- `Create Chain` action from selected graph nodes.
- `Chain Inspector` side panel with objective, frontier, hop timeline, evidence, and blockers.
- Node badge showing active chain membership and hop depth.
- Candidate review queue with promote / reject / merge actions.
- Evidence drawer that shows original URL, archive URL, provider/source-library refs, and capture metadata.

OpsPage / agent session additions:

- chain run events in the existing agent session timeline.
- retry/pause controls for blocked hops.
- exportable chain report for evidence review.

## 9. Implementation Waves

### Wave 1: Schema and write path

- Add `clue_chain` schemas and storage service.
- Add create/list/detail APIs.
- Add unit tests for chain creation, status transitions, and evidence refs.
- Add docs for object semantics and source-derived constraints.

### Wave 2: Source-library expansion

- Implement `source_library_search` hop mode.
- Reuse existing source-library query/local-index surfaces.
- Store returned source refs as `ChainEvidence`.
- Add dedupe/canonicalization for same entity from multiple source-library hits.

### Wave 3: External search expansion

- Implement provider-backed `external_search` hop mode.
- Require query trace and provider metadata.
- Add retry policy: broaden/narrow/alias query only within max retry budget.
- Add tests with fixture provider responses and no public-network dependency.

### Wave 4: Agent tool embedding

- Add controlled `chain.expand` tool contract to the agent runtime.
- Attach hop events to `agent_sessions`.
- Add approval gates for sensitive/scope-expanding pivots.
- Add integration tests that prove agent-created hops cannot bypass `ChainDecision`.

### Wave 5: Graph UI and replay

- Add GraphPage chain creation and inspector.
- Add hop replay view and export report.
- Add e2e test for seed node -> source-library hop -> candidate promotion -> graph edge.

## 10. Acceptance Criteria

- A user can create a `Chain` from one or more graph nodes.
- A chain can run one source-library hop and one external-search hop with replayable evidence.
- Every promoted node/edge points back to a `ChainEvidence` record.
- Agent runtime can request chain expansion but cannot silently promote candidates.
- Duplicate entity aliases merge before new graph nodes are created.
- Public-network search is fixture-gated in tests and explicit in live runs.
- The UI exposes frontier, hops, evidence, and blockers without hiding uncertainty.

## 11. External References Used

- Bellingcat, OSHIT: Seven Deadly Sins of Bad Open Source Research: original-source transparency, showing work, tool limitations, uncertainty. <https://www.bellingcat.com/resources/2024/04/25/oshit-seven-deadly-sins-of-bad-open-source-research/>
- Bellingcat, Principles for Data Collection: harm minimization, verification, correction, vulnerable-person protection. <https://www.bellingcat.com/about/principles-for-data-collection>
- OSINT Academy, OSINT methodology and collection: planning/collection/analysis/reporting, provenance, timestamps, hashes, chain of custody, archived citations. <https://os-intelligent.com/methodology/> and <https://os-intelligent.com/methodology/collection/>
- Maltego glossary and integration docs: entity/transform/machine model, entity-in/entity-out pivots, local transforms, link direction and labels. <https://docs.maltego.com/en/support/solutions/articles/15000008829-glossary-for-maltego-graph-desktop-> and <https://docs.maltego.com/en/support/solutions/articles/15000053545-building-integrations-for-maltego>
- Maltego Standard Transforms: practical transform use cases for infrastructure, social, historical web, document metadata, and automation. <https://docs.maltego.com/en/support/solutions/articles/15000041468-introduction-to-maltego-standard-transforms>
- Microsoft GraphRAG query docs: local/global/DRIFT search, entity-based reasoning, question generation. <https://microsoft.github.io/graphrag/query/overview/> and <https://microsoft.github.io/graphrag/query/local_search/>
- Microsoft GraphRAG indexing methods: entity extraction, relationship extraction, summarization, claim extraction, cost/fidelity tradeoffs. <https://microsoft.github.io/graphrag/index/methods/>
- GraphRAG pattern catalog, Graph-Enhanced Vector Search: entity disambiguation, schema-guided extraction, entity embeddings, ontology-driven traversal. <https://graphrag.com/reference/graphrag/graph-enhanced-vector-search/>
