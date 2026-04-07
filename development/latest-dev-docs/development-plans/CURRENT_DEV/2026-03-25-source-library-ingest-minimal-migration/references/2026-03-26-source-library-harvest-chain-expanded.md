# Source-Library Harvest Chain Expanded

Updated: 2026-03-26 PST

This file is the markdown companion for:

- [2026-03-26-source-library-harvest-chain-expanded.drawio](./2026-03-26-source-library-harvest-chain-expanded.drawio)

## Core Rule

`Harvest` is the peer standardized collection family to `Search`.

It should not be over-flattened into one generic provider box. In current reality, `Harvest` still contains two visible internal execution sub-lines:

1. provider direct-frontdoor path
2. provider to existing-ingest compat path

## Expanded Chain

1. Compile / runtime projection
- `run_source_library_item_compat`
- `run_collect`
- `SourceLibraryAdapter.run`
- `ItemResolver`
- `ExecutionRequest`
- `provider_harvest` as runtime projection

2. Execution line
- `Harvest` standardized family
- runtime-visible view:
  - `provider_harvest`

3. Execution binding
- `run_provider_harvest_orchestrator`
- `run_channel`
- `handler_registry`
- provider dispatch

4. Internal sub-line A: provider direct-frontdoor path
- concrete engines:
  - `policy`
  - provider-backed direct content
  - crawler / provider harvest outputs
- retained direct ingress path:
  - `build_frontdoor_ingress_envelope`

5. Internal sub-line B: provider to existing-ingest compat path
- concrete engines:
  - `google_news`
  - `reddit`
  - `market`
- retained compat chain:
  - `collect_urls_from_list`
  - `ingest_url_via_source_library_frontdoor`
  - `build_frontdoor_ingress_envelope`

6. Middle outputs + side effects
- `records`
- fetch stats / diagnostics
- provider snapshots
- compat counters when retained
- provider to existing ingest-service side paths
- direct frontdoor handoff
- optional resource-pool side paths when applicable

7. Boundary
- `SourceLibraryTerminalOutput v1`
- `build_source_library_ingress_envelope`
- `ingress_envelope`
- legal ingress forms:
  - `document_candidate accept`
  - `records-only defer`

8. Observability
- `terminal_output`
- `legacy_result`
- trace / debug / metrics
- family-level contract drift checks

## Mermaid Copy

```mermaid
flowchart LR

  A["Runtime / Compile
  run_source_library_item_compat
  run_collect
  SourceLibraryAdapter.run
  ItemResolver
  provider_harvest projection"] --> B["Execution Line
  Harvest standardized family
  provider_harvest as runtime view"]

  B --> C["Execution Binding
  run_provider_harvest_orchestrator
  run_channel
  handler_registry
  provider dispatch"]

  C --> D1["Provider direct-frontdoor path
  policy
  provider-backed direct content
  crawler / provider harvest outputs"]
  C --> D2["Provider to existing-ingest compat path
  google_news / reddit / market"]

  D1 --> E1["Direct ingress
  build_frontdoor_ingress_envelope"]

  D2 --> E2["Retained compat chain
  collect_urls_from_list"]
  E2 --> E3["ingest_url_via_source_library_frontdoor"]
  E3 --> E4["build_frontdoor_ingress_envelope"]

  D1 --> F["records / stats / diagnostics
  provider snapshots / compat counters"]
  D2 --> F

  F --> G["SourceLibraryTerminalOutput v1"]
  G --> H["build_source_library_ingress_envelope"]

  H --> I["ingress_envelope"]
  E1 --> I
  E4 --> I

  I --> J["document_candidate accept
  or records-only defer"]

  G --> K["observability
  terminal_output / legacy_result
  trace / debug / contract drift"]
```
