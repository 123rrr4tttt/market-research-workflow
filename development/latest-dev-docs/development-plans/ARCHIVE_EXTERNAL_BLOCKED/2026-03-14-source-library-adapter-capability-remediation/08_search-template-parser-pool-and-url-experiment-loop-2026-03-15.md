# Search Template Parser Pool and URL Experiment Loop

Date: 2026-03-15  
Status: in-review  
Owner: Codex  
Scope: `resource_pool` / `unified_search` / `search_template`

## Goal

Move search-result parsing from a single growing function to a modular parser pool so the runtime can:

1. Route by `parser_profile`.
2. Record which parser modules were actually used.
3. Support the loop: `URL experiment -> profile/module gap -> add new parser module -> replay`.

## What Landed

### 1. Parser profile registry

New file:

- [search_result_parser_profiles.py](../../../../../main/backend/app/services/resource_pool/search_result_parser_profiles.py)

It externalizes profile configuration instead of embedding all rule data inside one execution file.

Current profiles:

- `default`
- `site_adaptive`
- `site_adaptive.commercialobserver_card`
- `fallback_anchor_only`

Current profile fields:

- `profile_key`
- `entry_domain`
- `module_chain`
- `container_selectors`
- `title_link_selectors`
- `title_selectors`
- `summary_selectors`
- `structured_result_url_attributes`
- `low_value_anchor_texts`
- `low_value_href_markers`
- `low_value_host_markers`
- `global_anchor_min_text_length`
- `article_path_pattern`

### 2. Parser module executor

New modular executor:

- [search_result_parser_service.py](../../../../../main/backend/app/services/resource_pool/search_result_parser_service.py)

It now resolves a profile into a parser-module chain and executes modules in order.

Current built-in modules:

- `container`
- `structured`
- `jsonld`
- `global_anchor`

Each parse run now returns:

- candidates
- resolved profile key
- first effective module
- full attempted module chain
- hit diagnostics per module family

### 3. Route-layer integration

The route layer keeps owning policy; the parser layer now owns concrete extraction behavior.

Integrated files:

- [site_search_policy.py](../../../../../main/backend/app/services/resource_pool/site_search_policy.py)
- [unified_search.py](../../../../../main/backend/app/services/resource_pool/unified_search.py)
- [search_template_service.py](../../../../../main/backend/app/services/resource_pool/search_template_service.py)

Current flow:

1. Route layer resolves `parser_profile`.
2. `unified_search` injects it into execution params.
3. `search_template_service` forwards it to parser service.
4. Parser service resolves the profile and runs the module chain.

### 4. Generic route-kind propagation

`route_kind` is now treated as a generic candidate property rather than a site-only experiment.

Current behavior:

- parser profiles may define `route_rules`
- parser output writes `extra.route_kind`
- capability candidate construction infers a generic `route_kind` when one is missing
- scoring records `route_kind` and applies a light route-aware bonus/penalty
- unified search ref metadata now persists `route_kind`

Current generic route kinds:

- `article`
- `section`
- `collection`
- `publication_hub`
- `research_tool`
- `event`
- `page`

## URL Experiment Loop

This change enables the intended iteration loop:

1. Replay a failing domain/search URL.
2. Inspect parser trace:
   - `parser_profile_resolved`
   - `parser_module_used`
   - `parser_modules_tried`
   - `parser_container_hit`
   - `parser_structured_hit`
   - `parser_json_ld_hit`
   - `parser_global_anchor_hit`
   - `parser_candidate_rejected_low_value`
3. Decide whether:
   - an existing profile is enough
   - a new profile variant is needed
   - a truly new parser module is needed
4. Persist the selected `parser_profile` via `entry.extra.remediation.parser_profile`
5. Replay and compare outputs

## Current Acceptance

- `commercialobserver.com` now resolves to a site-specific parser profile instead of one-off logic spread in the execution layer.
- `fallback_anchor_only` can be selected explicitly from routing/remediation metadata.
- Entry-level remediation can override only `parser_profile` without needing a full `status` override.
- Parser diagnostics no longer assume all values are numeric.
- Section/collection/publication/tool candidates are no longer forced out at parser time; they are preserved and typed for downstream routing.
- Route typing now affects candidate scoring lightly instead of existing only as metadata.

## Next Execution Order

1. Add `site_adaptive.pymnts_card`
2. Add `site_adaptive.docs_shell`
3. Add `site_adaptive.media_card_dense`
4. Start replaying parser-weak domains one-by-one against the module pool

## Validation

Executed:

```bash
python3.11 -m pytest -q main/backend/tests/unit/test_resource_pool_search_template_service_unittest.py main/backend/tests/unit/test_resource_pool_unified_search_unittest.py
```

Result:

- `37 passed`
