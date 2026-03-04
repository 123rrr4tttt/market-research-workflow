# Ingest Platformization to Cleanup Optimization (2026-03-03)

## Scope
- Backend ingest platformization and quality-governance hardening.
- Coverage from `single_url/url_pool/raw_import` to `cleanup_meaningless_docs.py`.

## Implemented Changes

### 1) Structured extraction orchestration modularization
- Added reusable orchestrator module:
  - `main/backend/app/services/ingest/structured_extraction.py`
- `single_url` now calls shared orchestration instead of inline extraction flow.
- `raw_import`, `social`, and `market_web` reuse the same structured extraction orchestration entry.

### 2) Strict gate consistency and bulk-path inheritance
- `single_url.strict_mode` now effectively controls pre-fetch URL gate and pre-write content gate.
- `url_pool` no longer hard-codes `strict_mode=False`; bulk/parallel/async paths can inherit strict mode.

### 2.1) Single URL modularization and layering
- Layered flow for `single_url` is now explicitly aligned with platformized ingest:
  1. API/entry layer: receive single URL payload and runtime flags (`strict_mode`, project context, limits).
  2. Ingest orchestration layer: perform fetch/clean/gate decisions and call shared extraction orchestrator.
  3. Structured extraction layer: `services/ingest/structured_extraction.py` executes common extraction + summary contract.
  4. Persistence/routing layer: write structured fields and route by document semantics (including market routing rules).
- Result:
  - `single_url` no longer owns a private extraction chain.
  - structured module is reusable for `single_url`, `url_pool`, `raw_import`, `social`, `market_web`.
  - gate behavior is consistent between single-item and bulk/async paths.
- Design rule (for future changes):
  - keep structured extraction module independent from single chain execution shape (sync/thread/async);
  - single URL acts as caller, not owner of structured logic.

### 3) Raw import mixed input (text + url) platformization
- `raw_import` supports mixed item payload:
  - direct `text`
  - `url/uri/uris` fetch-and-merge pipeline
- New behavior:
  - fetch URL when text is empty
  - optionally fetch URL even when text exists, merge both for extraction
  - optional URL-success -> `market_info` routing when doc_type is not explicitly set

### 4) Shell-noise pinpoint cleaning (line-level)
- `normalize_content_for_ingest` enhanced with line-level shell-noise trimming:
  - nav/menu/login/privacy/cookie/footer noise
  - script-template short lines
  - repeated noise-line dedupe
- Target: remove shell-only fragments while preserving semantic body paragraphs.

### 5) Cleanup script hardening
- Script: `main/backend/scripts/cleanup_meaningless_docs.py`
- Added quality-focused cleanup mode:
  - `--target-mode quality_only`
  - rules include `structured_extraction_status=failed` and `quality_score<threshold`
- Added in-place sanitize mode (non-delete):
  - `--sanitize` (+ `--sanitize-max-chars`)
  - applies shell-noise pinpoint cleaning to candidate docs
- Added recent quality pipeline:
  - `--recent-quality-pipeline --recent-limit N`
  - classify `unstructured / pseudo-success / real-low-quality`
  - optional re-extract + optional delete low-quality
- Token-protection update:
  - low-quality documents are excluded from re-extraction path by design
  - only non-low-quality unstructured/pseudo-success docs may be re-extracted

## Production Validation Snapshot
- Recent-20 inspection found:
  - unstructured docs: 5
  - pseudo-success docs (ok without summary): 15
- Applied pipeline:
  - re-extracted 5 (success)
  - backfilled structured summary for 15
- Low-quality-only deletion (no re-extract):
  - candidate: 15
  - deleted: 15
  - post-check candidate: 0

## Key Commands
```bash
# quality-only dry-run
cd main/backend
./.venv311/bin/python scripts/cleanup_meaningless_docs.py \
  --project demo_proj --target-mode quality_only --write-id-file /tmp/ids.txt

# quality-only delete apply
./.venv311/bin/python scripts/cleanup_meaningless_docs.py \
  --project demo_proj --target-mode quality_only --apply --id-file /tmp/ids.txt

# recent quality pipeline (no re-extract, delete real low quality)
./.venv311/bin/python scripts/cleanup_meaningless_docs.py \
  --project demo_proj --recent-quality-pipeline --recent-limit 500 --delete-real-low-quality --apply
```

## Notes
- `--delete-real-low-quality` can now run without `--reextract-unstructured` to avoid token waste.
- For operational safety, all destructive actions remain opt-in via `--apply`.
