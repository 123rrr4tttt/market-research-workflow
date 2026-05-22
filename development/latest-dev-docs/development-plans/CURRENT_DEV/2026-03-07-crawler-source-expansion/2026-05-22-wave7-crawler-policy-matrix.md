# Wave7-2 Crawler Policy Matrix

Date: 2026-05-22
Branch: `codex/devdocs-wave7-crawler-policy-matrix`
Scope: `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-crawler-source-expansion/`

## Closure Decision

A4 status in this branch: `closed`.

The A4 gap from Wave6 is closed by binding a source-layer `allow` / `downgrade` / `block` shape to the existing resolver, probe, and enforcement points. This document is topic-local. Shared navigation files stay untouched for the later integration lane.

A5 remains blocked by the full opt-in public replay. A6 still needs provider-specific crawler and high-JS/browser handoff proof.

## Policy Shape

The source-layer decision field is `source_policy_action`. Valid values are:

- `allow`: the source can proceed as a fresh governed candidate.
- `downgrade`: the source remains traceable but must not be treated as bulk-ingest-green without review, replay, fallback, or dedupe context.
- `block`: the source is rejected before source-library execution or downstream write.

The decision is source-layer metadata, not a replacement for downstream ingest gates. Downstream gates still enforce content quality, provenance, frontdoor admission, and persistence safety.

## Matrix

| Decision | Source-layer condition | Resolver/probe binding | Enforcement and downstream binding | Outcome |
| --- | --- | --- | --- | --- |
| `allow` | Trusted public URL, valid source tier, valid handler entry type, and no duplicate normalized URL. High trust source candidate is the cleanest case. | [source_candidate_trust.py](../../../../../main/backend/app/services/source_library/source_candidate_trust.py) emits `source_policy_action=allow`; [resolver.py](../../../../../main/backend/app/services/source_library/resolver.py) carries `source_tier`, `onboarding_priority`, and `middle_layer_protocol`; [llm_validator.py](../../../../../main/backend/app/services/resource_pool/llm_validator.py) accepts only allowed `entry_type` and `channel_key`. | [meaningful_gate.py](../../../../../main/backend/app/services/ingest/meaningful_gate.py) still runs `url_policy_check` and `content_quality_check`; [discovery/store.py](../../../../../main/backend/app/services/discovery/store.py) applies `_discovery_gate_check` before frontdoor postprocess. | Candidate may continue to resolver/probe execution and normal downstream admission. |
| `downgrade` | Medium trust candidate, duplicate normalized URL, term-fallback candidate, slow-lane/browser-deferred source, or experimental source tier. | [source_candidate_trust.py](../../../../../main/backend/app/services/source_library/source_candidate_trust.py) emits `source_policy_action=downgrade` for medium-trust and duplicate candidates; [resolver.py](../../../../../main/backend/app/services/source_library/resolver.py) records crawler fallback, `site_policy_breakdown`, and slow-lane diagnostics in source-library results. | Downstream may keep the source as review evidence, replay evidence, fallback evidence, or dedupe trace, but should not silently count it as a fresh bulk-ingest success. Discovery remains candidate discovery, not the canonical source registry. | Candidate is retained with a downgrade label and review/fallback context. |
| `block` | Private or invalid URL, low-value URL endpoint, blocked URL policy, shell/empty/garbled content, invalid LLM recommendation, or discovery gate rejection. | [source_candidate_trust.py](../../../../../main/backend/app/services/source_library/source_candidate_trust.py) emits `source_policy_action=block`; [llm_validator.py](../../../../../main/backend/app/services/resource_pool/llm_validator.py) returns `None` for invalid recommendations; [resolver.py](../../../../../main/backend/app/services/source_library/resolver.py) isolates per-URL errors instead of promoting the source. | [meaningful_gate.py](../../../../../main/backend/app/services/ingest/meaningful_gate.py) blocks via `GateDecision`; [discovery/store.py](../../../../../main/backend/app/services/discovery/store.py) rejects before `build_discovery_ingress_envelope` / `run_postprocess_frontdoor`. | Source does not proceed as an ingestable candidate. |

## Minimum Rule Set

| Rule | Source-layer requirement | Existing anchor |
| --- | --- | --- |
| Reliability | Resolve source tier and route before provider execution; isolate per-URL failures and timeouts. | `resolver._build_frontdoor_protocol`, `resolver._run_url_routing_materialization` |
| Repeatability | Normalize URLs, keep checksums, dedupe before fresh execution, and keep replay metadata. | `source_candidate_trust.evaluate_source_candidate_url`, `duplicate_candidate_url`, `url_checksum` |
| Content signal | Run URL checks before fetch and content checks before write. | `meaningful_gate.url_policy_check`, `meaningful_gate.content_quality_check` |
| Dedupe | Treat normalized duplicate candidates as `downgrade`, not fresh allow. | `source_candidate_trust.build_source_candidate_plan` |
| Metadata completeness | Preserve `source_tier`, `onboarding_priority`, `middle_layer_protocol`, gate diagnostics, and route/fallback details. | `resolver._protocol_to_dict`, `discovery.store._discovery_gate_check` |

## Examples

| Example | Expected action | Evidence path |
| --- | --- | --- |
| `https://example.com/robot?id=1` after wrapper normalization, public DNS, domain match, and high trust score. | `allow` | `source_candidate_trust.evaluate_source_candidate_url` |
| A second candidate that normalizes to the same URL, or a medium-trust public URL that passes URL policy but lacks high-trust signals. | `downgrade` | `source_candidate_trust.build_source_candidate_plan` |
| `http://127.0.0.1/admin`, `https://www.google.com/search?q=robotics`, or shell-only content. | `block` | `external_project.validate_external_http_url`, `meaningful_gate.url_policy_check`, `content_quality_check` |

## Executable Check

```bash
cd main/backend
python3 scripts/check_crawler_policy_matrix.py
python3.11 -m pytest -q \
  tests/unit/test_crawler_policy_matrix_check_unittest.py \
  tests/unit/test_source_candidate_trust_unittest.py \
  tests/unit/test_crawler_source_expansion_closure_check_unittest.py
```

Expected result: the policy matrix check passes and the closure checker reports A4 as `closed` while the overall topic remains `not_closed` because A5-A7 are not fully closed.
