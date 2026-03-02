# Standard Ingest Workflows (2026-03-02)

Last updated: 2026-03-02 PST
Owner: backend-core
Scope: normalize current production-intended ingest workflows from entry API to stored document output.

## 1. Workflow Catalog (Current Standard)

### WF-1: `single_url` standard path

- Entry:
  - `POST /api/v1/ingest/url/single`
  - async task: `task_ingest_single_url`
- Core service:
  - `app/services/ingest/single_url.py::ingest_single_url`
- Standard stages:
  1. URL normalization + validity guard
  2. capability profile (`entry_type`, `render_mode`, `anti_bot_risk`)
  3. handler allocation (native first; crawler pool fallback when needed)
  4. page gate (low-value shell detection)
  5. structured extraction + quality scoring
  6. idempotent write (`Document.uri` dedupe)
- Output contract (business):
  - `status`: `success | degraded_success | failed`
  - `inserted`, `skipped`, `document_id`, `quality_score`
  - `degradation_flags`, `handler_allocation`, `page_gate`

### WF-2: `url_pool` site-first standard path

- Entry:
  - adapter path through collect runtime `channel=url_pool`
  - commonly triggered by source_library/unified_search auto-ingest
- Core service:
  - `app/services/ingest/url_pool.py::{collect_urls_from_list, collect_urls_from_pool}`
- Standard stages:
  1. normalize pool/list URLs
  2. build site-first targets (`domain_root/search_template/sitemap/rss` seeds first, detail later)
  3. each target reuses WF-1 (`ingest_single_url`)
  4. attach `url_pool_context` back to inserted docs
  5. aggregate counters + debug traces
- Output contract (business):
  - `inserted`, `skipped`, `skipped_exists`, `skipped_fetch_error`
  - pool mode adds `pool_total`, `pool_returned`, `skipped_invalid_url`
  - debug: `site_seed_count`, `target_count`, `url_details`, `errors`

### WF-3: `source_library` handler-cluster (`search_template`) standard path

- Entry:
  - `POST /api/v1/ingest/source-library/run` with `handler_key=search_template`
- Core services:
  - `collect_runtime/adapters/source_library.py::SourceLibraryAdapter.run`
  - `resource_pool/unified_search.py::unified_search_by_item_payload`
- Standard stages:
  1. resolve `handler.cluster.search_template` item + site entries
  2. template search parse candidates
  3. optional write-to-pool
  4. optional auto-ingest to WF-2
  5. batch result merge
- Output contract (business):
  - `result.inserted/updated/skipped`
  - `result.written.{urls_new,urls_skipped}`
  - `result.ingest_result.{inserted,updated,skipped}`
  - `result.site_entries_used`, `result.candidates`, `result.error_details`

### WF-4: post-ingest sanitation (`meaningful_doc_cleanup`) standard path

- Entry:
  - operations script/manual SQL batch (project schema scoped)
  - mandatory two-step mode: `dry-run` then `apply`
- Scope:
  - `documents` table in project schema (for example: `project_demo_proj.documents`)
- Standard stages:
  1. candidate rule scan (strict rules first, then optional aggressive rules)
  2. dry-run sample review (id/title/uri/content preview + hit reason)
  3. apply deletion by explicit IDs (no broad destructive delete)
  4. post-delete verification (`remaining_count`, rule-hit count should drop to 0)
  5. cleanup report snapshot (counts by rule/doc_type/domain)
- Output contract (business):
  - `candidate_count`, `deleted_count`, `deleted_ids`
  - `rule_breakdown`
  - `remaining_total`, `remaining_rule_hits`

## 2. Standard Result/Status Model

### API envelope

- success envelope: `status=data/error/meta` (status=`ok`)
- failure envelope: `status=error` + structured error payload

### task/process status

- async submit returns `task_id`
- process polling uses `/api/v1/process/{task_id}`
- terminal states mapped to `SUCCESS/FAILURE` (Celery) and `completed/failed` (job logger)

### ingest business status

- `success`: inserted with acceptable quality
- `degraded_success`: workflow completed but downgraded (e.g., parser fallback, duplicate, low-confidence)
- `failed`: no acceptable output

## 3. Current Implemented Standardization (as of 2026-03-02)

1. Native-first + crawler fallback unified in WF-1.
2. Search-template no-result gated (prevents false-success homepage shell writes).
3. Crawler output quality gate added (reject script/navigation shell-like docs).
4. URL pool switched to site-first target allocation and WF-1 reuse.
5. Domain-specific shell parser introduced (GitHub repository pages).
6. Forced crawler-domain policy introduced for anti-bot-prone domain baseline (Reddit).
7. Post-ingest sanitation playbook validated in production-like data:
  - strict shell/noise rules can be executed safely with dry-run/apply workflow.

## 4. Verification Snapshot

### Automated tests (latest local pass)

- `tests/unit/test_single_url_ingest_unittest.py`: passed
- `tests/core_business/test_ingest_core_contract.py`: passed

### Runtime checks (recent)

- single URL (GitHub stargazers) produced structured parser output:
  - inserted doc id observed: `229`
  - flag: `domain_specific_parser_applied:github_repo_page`
  - structured content fields present (`Repository`, `Page type`, `Description`)
- source-library handler-cluster run (`search_template`) completed:
  - task id observed: `54d29dad-2d92-49b0-a17f-050fe1ad16af`
  - result pattern: candidates parsed, but many dedup-skipped in ingest stage

### Data quality cleanup checks (recent)

- Project schema: `project_demo_proj`
- Initial issue pattern observed in recent ingest:
  - `url_fetch` shell pages (navigation/login/search/homepage wrappers)
  - JS/SSR shell payloads (`window.wiz_*`, `var bodyCacheable`, Next.js hydration chunks)
  - binary PDF raw bytes (`%PDF-1.x`) stored as plain text
  - empty-content rows
- Executed strict cleanup waves (all verified before delete):
  - wave-1: empty-content docs removed: `20`
  - wave-2: explicit shell-domain docs removed: `30` (`news.google.com`, `x.com`, `actiontoaction.ai`)
  - wave-3: remaining `url_fetch` + PDF-raw noise removed: `19`
  - total removed: `69`
- Final verification snapshot:
  - `remaining_url_fetch = 0`
  - `remaining_pdf_raw = 0`
  - current mix: `market_info=33`, `social_sentiment=8`, `raw_note=1` (total `42`)

## 5. Known Gaps (Still Open)

1. Shell content can still pass in some domains without dedicated parser/API.
2. 403/anti-bot remains recurrent (not fully policy-driven by domain).
3. Dedup causes frequent `0 new inserted` while task still returns success.
4. `/admin/documents/list` currently lacks rich quality fields (`uri/content/quality/parser tags`) for fast frontend triage.
5. `url_fetch` currently has no enforced meaningful-content threshold before final write.
6. Binary/PDF ingestion path lacks strict text-extraction success guard (raw bytes may leak into content).

## 6. Standard Next-Step Backlog

1. Parser/API specialization expansion:
  - BBC/news pages, Google search pages, X/Reddit specialized routes.
2. Domain-level provider policy:
  - mandatory crawler domains, retry budgets, anti-bot strategy profile.
3. Unified meaningful-document acceptance metric:
  - enforce one consistent pass criterion before final success.
4. List API observability upgrade:
  - expose `uri`, `quality_score`, `handler_used`, `skip_reason`, parser tag.
5. Make WF-4 operationalized as default guardrail:
  - ship cleanup script with `--project`, `--dry-run`, `--apply`, `--id-file`.
  - always delete by explicit ID set generated by dry-run.
6. Introduce mandatory pre-write reject rules in WF-1/WF-2:
  - reject if `content` empty or below minimum semantic length.
  - reject if shell signatures hit (Google wiz shell, Wix bodyCacheable shell, error/login/search wrappers).
  - reject if binary signatures hit (`%PDF-1.` without successful parsed text extraction).
7. Add domain/path denylist for low-value endpoints:
  - examples: `/search`, `/login`, `/home`, `/showcase`, `/topics/*`, `/stargazers` (unless parser explicitly supports target value).

