# External Project Powered Item Design

Updated: 2026-03-27 PST

## Purpose

This note defines a two-stage mechanism for turning an external project link into an executable source-library item:

`external project link -> external item manifest -> provider runner -> frontdoor normalized output`

The goal is to let users interact with the resulting item through the same source-library input/output contract they already know, while keeping the project-specific machinery behind an execution boundary.

## Why This Exists

The current source-library stack already has the right structural pieces:

- `item` is a source-set abstraction.
- execution strategy is derived later.
- runtime diagnostics and frontdoor normalization already exist as separate layers.

This proposal adds a new kind of source-set abstraction whose meaning is discovered from an external project, but whose runtime behavior is still executed through explicit providers and normalized through the same frontdoor path.

The external project should not become a per-query LLM interpretation problem. It should become a registered, stable manifest with a bounded runner.

## Non-Goals

- Do not make arbitrary repository code executable at runtime.
- Do not let the LLM re-parse the project on every user request.
- Do not replace the existing source-library item model.
- Do not change the frontdoor contract for normal source-library outputs.
- Do not require every external project to support full article-body extraction in v1.
- Do not build a generic plugin marketplace in the first version.

## Two-Stage Flow

### 1. Registration Stage

Input:

- a project link
- optional hints such as project type, auth needs, or example targets

Process:

- probe the project repository or docs
- inspect README, configuration files, package metadata, or feed endpoints
- use LLM assistance to infer what the project can do
- synthesize a stable external item manifest
- persist the manifest as a registered external item

Output:

- an external item definition that can be listed and invoked like other source-library items

### 2. Runtime Stage

Input:

- the registered external item
- the same source-library style runtime params users already pass today

Process:

- build an execution plan from the manifest
- route to a provider runner selected by `source_kind` and `execution_mode`
- let the runner fetch or compute raw outputs
- normalize the result into source-library terminal output
- build source-library frontdoor ingress
- run frontdoor postprocess

Output:

- standard source-library terminal output
- standard `frontdoor_ingress`
- standard `postprocess_frontdoor`

## Manifest Contract

An external item manifest should be the stable contract between discovery and runtime.

Required fields:

```json
{
  "contract_version": "external_item.manifest.v1",
  "item_key": "external.rsshub.finextra",
  "display_name": "Finextra Headlines",
  "project_link": "https://github.com/... or https://...",
  "source_kind": "feed_aggregator",
  "source_scope": "finance_news",
  "capabilities": {
    "candidate_urls": true,
    "article_metadata": true,
    "article_body": false,
    "pdf_artifact": false
  },
  "accepted_inputs": {
    "query_terms": true,
    "urls": false,
    "domains": true,
    "date_range": true,
    "max_items": true
  },
  "execution_mode": "rss_feed",
  "runner_ref": "rsshub://finextra/headlines",
  "normalization": {
    "record_kind": "candidate_url",
    "frontdoor_strategy": "records_only_defer"
  },
  "limits": {
    "default_max_items": 20,
    "max_items_cap": 100,
    "request_timeout_ms": 30000
  },
  "refresh_policy": {
    "manifest_ttl_minutes": 60,
    "probe_ttl_minutes": 1440
  },
  "provenance": {
    "discovered_by": "llm_probe",
    "source_refs": []
  }
}
```

### Contract Notes

- `item_key` must be stable and human traceable.
- `source_kind` describes what the project is capable of, not how the current query executes.
- `execution_mode` describes the runner family, not the source meaning.
- `capabilities` declare the highest guaranteed output type for the manifest.
- `normalization.frontdoor_strategy` decides how the runtime should map into the standard source-library frontdoor flow.
- `provenance` should preserve where the manifest came from and what evidence was used.

## Execution Modes

The first version should support only a small set of execution modes:

- `rss_feed`
- `sitemap`
- `http_api`
- `python_library`
- `cli_or_container`

Suggested semantics:

- `rss_feed`
  - consume RSS/Atom feeds and map items to candidate URLs or article metadata
- `sitemap`
  - consume sitemap indexes, monthly archives, or channel indexes
- `http_api`
  - call a documented API endpoint and transform the response into candidates or records
- `python_library`
  - call a known packaged library through a narrow wrapper
- `cli_or_container`
  - run a predeclared CLI or containerized tool through a controlled adapter

This list should stay narrow until the runner boundary is proven safe and stable.

## Runner Boundary

The runner boundary should be explicit and conservative.

Allowed inside the runner:

- HTTP fetches to known endpoints
- feed parsing
- sitemap traversal
- API calls with declared parameters
- invocation of a predeclared Python library or CLI wrapper
- artifact download for known output types

Not allowed inside the runner:

- arbitrary repo code execution
- dynamic package installation during a user query
- unrestricted shell execution
- mutating the external project repo to make it work
- letting the LLM select arbitrary runtime code paths without a manifest contract

The runner should return a canonical internal result, for example:

- raw candidates
- materialized records
- stats
- diagnostics
- artifact metadata

The runner should not be responsible for frontdoor policy decisions.

## Frontdoor Mapping

External item output should still pass through the same source-library normalization path.

### Mapping Rules

- `candidate_urls`
  - become source-library `records` or candidate records, depending on the manifest capability
- `article_metadata`
  - becomes record fields such as title, url, summary, source, publish date
- `article_body`
  - becomes source-library records with content candidates that can reach frontdoor extraction
- `pdf_artifact`
  - becomes `record_meta.artifact_ref` plus `frontdoor_ingress.collection_payload.source_artifacts`

### Recommended Frontdoor Behavior

- If the runner only returns candidate URLs, the source-library path should build `terminal_output` and then defer extraction, matching current records-only semantics.
- If the runner returns a fully materialized document candidate, the source-library path may allow frontdoor extraction and writer steps where applicable.
- If the runner returns a file artifact such as PDF, the artifact should be preserved on both sides of the source-library/frontdoor boundary.

### Boundary Identity

The output should still land in:

- `terminal_output`
- `frontdoor_ingress`
- `postprocess_frontdoor`

This keeps external items compatible with the rest of the ingest stack.

## Risks And Limits

- Project docs may be incomplete or outdated, so LLM-generated manifests need a reviewable provenance trail.
- Many external projects will only support partial capability, not full article-body extraction.
- Authenticated APIs, rate limits, and anti-bot policies can make some projects unstable at runtime.
- If the manifest tries to infer too much, the system will become brittle.
- If the runner boundary is too loose, the system will become unsafe.
- If the manifest surface is too large, the item will stop feeling like a source abstraction and start feeling like an execution config again.

## Recommended V1 Scope

The first version should be intentionally narrow:

1. Support only registered external projects, not arbitrary live repo execution.
2. Support only three discovery families:
   - `rss_feed`
   - `sitemap`
   - `http_api`
3. Allow `python_library` only when the package is already known and sandboxed.
4. Use LLM only for manifest synthesis and capability classification, not for per-query runtime routing.
5. Normalize every result through the existing source-library frontdoor path.
6. Keep article-body extraction optional.
7. Keep PDF artifact handling as an explicit capability, not a default assumption.

This scope is enough to make the feature useful without turning it into a generic plugin system.

## Suggested First Milestone

The first milestone should register one project link into one stable external item manifest, then run one end-to-end query through:

`manifest -> runner -> terminal_output -> frontdoor_ingress -> postprocess_frontdoor`

That milestone is sufficient to prove that the abstraction works before expanding to more project types.

