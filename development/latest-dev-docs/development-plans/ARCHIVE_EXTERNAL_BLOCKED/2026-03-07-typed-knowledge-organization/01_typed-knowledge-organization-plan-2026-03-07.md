# Typed Knowledge Organization Plan (2026-03-07)

> Date: 2026-03-07
> Scope: typed taxonomy, knowledge-item organization, topic clustering, booklet semantics, bilingual representation, quality grading
> Status: planning document; this file freezes problem framing and phase order before implementation

## 1. Goal

This topic exists to define a stable organization layer between raw evidence and downstream consumers.

Phase 1 should make the following executable:

1. Define the minimum object set for typed knowledge organization.
2. Separate taxonomy, topic grouping, booklet presentation, bilingual representation, and quality grading instead of mixing them into one vague "classification" bucket.
3. Define where automation ends and human governance begins.
4. Define one minimum downstream read contract that search, graph, writing, and reporting can consume consistently.

This is not a request to build a full ontology or finalize database schema in one pass. It is a request to stop downstream features from depending on unstable concepts.

## 2. Current Baseline

### 2.1 Existing repo surfaces that already matter

The repo already contains several adjacent capabilities:

- Evidence ingestion and extraction:
  - `main/backend/app/services/discovery/store.py`
- Resource-pool classification and normalization:
  - `main/backend/app/services/resource_pool/auto_classify.py`
  - `main/backend/app/services/resource_pool/unified_search.py`
  - `main/backend/app/services/resource_pool/resolver.py`
  - `main/backend/app/services/resource_pool/extract.py`
  - `main/backend/app/services/resource_pool/site_entries.py`
- Topic management:
  - `main/backend/app/api/topics.py`
- Graph projection constraints and node-type catalogs:
  - `main/backend/app/services/graph/doc_types.py`
  - `main/backend/app/services/graph/*`
- Writing and report consumption surfaces:
  - `main/backend/app/api/writing.py`
  - `main/backend/app/services/writing/*`
  - `main/backend/app/api/llm_report.py`
- Current operator and consumer pages:
  - `main/frontend-modern/src/pages/OpsPage.tsx`
  - `main/frontend-modern/src/pages/ProjectsPage.tsx`
  - `main/frontend-modern/src/pages/GraphPage.tsx`
  - `main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`

This means the repo does not start from zero. It already has source records, extraction outputs, topic records, graph type projections, and writing/report consumers.

### 2.2 What these existing surfaces already tell us

- `discovery/store.py` is evidence-first: it fetches, gates, and extracts document content, but it is not a typed organization layer.
- `resource_pool/auto_classify.py` is rule-first classification for site-entry URLs and keyword capability metadata. It is useful as an automation pattern, but it does not classify knowledge objects such as type nodes or curated topic bundles.
- `api/topics.py` already provides a lightweight topic object with fields such as `topic_name`, `domains`, `languages`, and `keywords_seed`. This is a useful baseline, but it is too shallow to represent the full organization problem on its own.
- `graph/doc_types.py` already defines graph-facing node and edge combinations. That gives downstream constraints, but graph projection should not become the source of truth for taxonomy design.
- `api/writing.py` and `services/writing/*` show that writing, citation, keyword-card, and template flows already exist. Knowledge organization therefore needs to feed real consumers, not just future ideas.

### 2.3 Baseline gaps that remain open

The missing pieces are still structural:

- There is no dedicated typed knowledge organization domain that unifies taxonomy, knowledge items, topic clusters, booklet groupings, bilingual variants, and quality grades.
- The current topic object is not enough to describe typed hierarchy, governance state, provenance, or downstream-read semantics.
- Automation and manual review boundaries are not yet documented as a platform-level workflow.
- Search, graph, writing, and reporting do not yet share one explicit read model for organized knowledge.
- Booklet semantics, bilingual semantics, and quality semantics are not yet placed in one consistent layer model.

## 3. Requirement Clarification

### 3.1 Who this topic serves

The organization layer must support three audiences:

- Operations and governance users who need to review, merge, correct, and maintain organization results.
- Analysts and writers who need stable topic bundles, evidence grouping, and bilingual-ready summaries.
- Downstream systems that need normalized knowledge objects instead of reading directly from raw extraction artifacts.

### 3.2 Core questions that must be answered in this topic

Phase 1 must answer these questions explicitly:

1. What is a `Type Node` and how is it different from a graph node type, a tag, or a topic label?
2. What is a `Knowledge Item` and how does it relate to documents, extraction results, and graph nodes?
3. Is a `Topic Cluster` a first-class object or just a filtered view?
4. Is a `Booklet` a classification primitive or a curated presentation container?
5. Are bilingual variants separate objects or localized views of the same knowledge item?
6. How does quality grade affect downstream consumption?
7. Which steps can be automated and which require explicit human confirmation?

### 3.3 Constraints from the parent planning document

The parent planning document at `../2026-03-07-后续安排/01_abstract-planning-folderization-plan-2026-03-07.md` requires every child plan to cover:

- current baseline
- requirement clarification
- scope and non-goals
- recommended sequencing
- serial vs parallel relationships
- minimum validation

This file therefore optimizes for execution guidance, not for speculative completeness.

## 4. Scope and Non-Goals

### 4.1 In scope for this topic

Phase 1 should cover:

- the minimum object model for `Type Node`, `Knowledge Item`, `Topic Cluster`, and `Booklet`
- the role of `quality_grade`, `review_state`, `locale`, and `source provenance`
- the minimum automation-plus-human-governance loop
- one minimum downstream read contract
- project-scoped organization rules, because current repo surfaces already use project-level boundaries heavily

### 4.2 Out of scope for this topic

This topic should not do the following in its first round:

- redesign ingestion or crawler pipelines
- turn graph projection types into the master taxonomy without review
- freeze a complete database schema
- enumerate every future topic or every type-node branch
- lock a full bilingual content-production workflow
- take over graph-editing interaction design

## 5. Recommended Layering

### 5.1 Layer 0: Evidence layer

This layer contains raw and semi-processed records:

- source documents
- discovery outputs
- extraction outputs
- resource-pool entries

This layer remains evidence-first. It is allowed to be noisy, duplicated, or incomplete.

### 5.2 Layer 1: Organization layer

Phase 1 should freeze four organization objects.

#### `Type Node`

- Purpose: taxonomy anchor for classification and navigation
- Recommended shape in Phase 1:
  - project-scoped
  - stable key
  - label(s)
  - optional parent key
  - status / review metadata
- Recommendation:
  - support one primary parent in Phase 1
  - do not optimize for multi-parent write semantics yet
  - do not equate `Type Node` with a graph-rendering node

#### `Knowledge Item`

- Purpose: normalized knowledge object that downstream systems can read
- It should point back to evidence and carry organization metadata.
- Recommended minimum fields:
  - stable key
  - project key
  - canonical title or statement
  - primary `type_node_key`
  - optional `topic_cluster_keys`
  - optional `booklet_keys`
  - provenance refs
  - review state
  - quality grade
  - locale metadata

#### `Topic Cluster`

- Purpose: cross-item thematic grouping
- Recommendation:
  - treat it as a first-class organization object
  - allow it to aggregate many knowledge items across type nodes
  - do not treat it as a synonym for taxonomy

#### `Booklet`

- Purpose: curated organization container for a project, theme, or reporting view
- Recommendation:
  - treat booklet as presentation-oriented organization, not as the core classification primitive
  - a booklet can include multiple type nodes and topic clusters
  - booklet membership should be explicit, not implied from type hierarchy alone

### 5.3 Layer 2: Governance dimensions

The following should be modeled as dimensions on organized knowledge, not as separate top-level systems:

- `review_state`
  - example states: draft candidate, human-confirmed, revised, deprecated
- `quality_grade`
  - this should influence downstream ranking or eligibility
- `locale`
  - bilingual support should be modeled as language variants of the same knowledge object unless there is a strong repo-specific reason to split identities later
- `provenance`
  - every organized result should preserve source/evidence traceability

### 5.4 Layer 3: Consumer adapters

Downstream readers should consume organization results through one minimal contract, then adapt locally:

- search uses type/topic/booklet/quality facets
- graph uses organization metadata as projection inputs, not as the only source of truth
- writing uses organized items as evidence cards, citation candidates, and topic bundles
- reporting uses organized items as filterable, quality-aware evidence inputs

## 6. Recommended Phase-1 Decisions

Phase 1 should freeze the following decisions before any heavy automation work:

1. `Knowledge Item` is the downstream-facing normalized unit.
2. `Type Node` is taxonomy, not graph rendering and not free-form tag soup.
3. `Topic Cluster` is a thematic grouping object and can cross type boundaries.
4. `Booklet` is a curated organization container and should not replace taxonomy.
5. `quality_grade`, `review_state`, and `locale` live on the organized knowledge layer.
6. Automation may propose `type_node` / `topic_cluster` candidates, but human governance owns final confirmation.
7. Downstream consumers should read stable keys and metadata from one minimum contract instead of reading ad hoc fields from unrelated sources.

## 7. Implementation Order

### 7.1 Serial foundation

The first two steps are serial and should be completed before branching:

1. Audit the existing repo objects and freeze terminology.
2. Freeze object boundaries for `Type Node`, `Knowledge Item`, `Topic Cluster`, and `Booklet`.

### 7.2 Parallelizable design work after object boundaries are frozen

After the object set is stable, the following can proceed in parallel:

- governance semantics
  - `review_state`
  - `quality_grade`
  - `locale`
  - provenance rules
- booklet and topic-cluster semantics
- downstream read-contract drafting for search, graph, writing, and reporting

### 7.3 Serial closure work

After the parallel design pieces converge:

1. define the automation-to-human workflow
2. validate one end-to-end sample
3. freeze unresolved questions explicitly instead of hiding them in vague wording

## 8. Serial and Parallel Relationships

- `S1 -> S2` must be serial:
  - `S1`: baseline audit and terminology freeze
  - `S2`: core object boundary definition
- `S3a`, `S3b`, `S3c` can run in parallel after `S2`:
  - `S3a`: topic cluster and booklet semantics
  - `S3b`: governance dimensions
  - `S3c`: downstream contract draft
- `S4` must wait for `S3a-S3c`:
  - automation and manual-governance workflow
- `S5` closes the phase:
  - one sample scenario and minimum validation pack

The key rule is simple: do not design automation or UI workflow against unstable object definitions.

## 9. Minimum Downstream Contract Recommendation

Phase 1 does not need a final API schema, but it should freeze a minimum read shape conceptually.

Recommended minimum fields for downstream readers:

- `project_key`
- `knowledge_item_key`
- `title`
- `type_node_key`
- `topic_cluster_keys`
- `booklet_keys`
- `quality_grade`
- `review_state`
- `locale`
- `source_refs`
- `updated_at`

This is a planning recommendation, not a claim that the contract already exists in code.

## 10. Minimum Validation

At minimum, this topic should be considered coherent only if all of the following are possible:

### 10.1 Structural validation

Provide one concrete example that maps:

- one evidence source
- one `Knowledge Item`
- one `Type Node`
- one `Topic Cluster`
- optional `Booklet`
- one downstream consumer view

### 10.2 Workflow validation

Provide one minimal flow for:

1. auto-generated classification candidate
2. human confirmation or override
3. organization-layer write-back
4. downstream read by graph or writing

### 10.3 Boundary validation

The document must make it impossible to confuse:

- `Type Node` vs graph node type
- `Topic Cluster` vs booklet
- quality grade vs taxonomy
- bilingual representation vs separate taxonomy branch

## 11. Risks and Open Questions

### 11.1 Risks

- If taxonomy is derived directly from current graph node types, the organization layer will inherit graph-specific constraints too early.
- If automation is treated as final truth instead of candidate generation, governance debt will grow quickly.
- If booklet, topic cluster, type node, and tag-like labels are not separated, downstream readers will each invent their own meaning.
- If bilingual semantics are postponed without a placeholder model, writing and reporting will invent incompatible language behaviors later.

### 11.2 Open questions to carry into execution

- Should Phase 1 allow only one primary `type_node_key` per `Knowledge Item`, with later support for secondary associations?
- Does booklet membership need ordering semantics in Phase 1, or is membership-only enough?
- Does quality grade affect eligibility, ranking, or both for downstream readers?
- Are bilingual variants stored as canonical-plus-translation fields, or as localized payload slices under one identity?

## 12. Recommended Next Step

The next document should not jump into implementation details blindly. It should break this plan into atomic planning tasks that:

- cite current repo inputs
- keep file/module boundaries explicit
- preserve serial/parallel execution order
- define minimum verification for each step
