# Wave8-6 Writing Workbench Typed Knowledge Card Contract Evidence (2026-05-22)

Scope: local closure slice for `2026-03-07-writing-workbench-evolution` consuming the typed knowledge handoff.

Shared indexes were intentionally not edited.

## Landed Slice

- Added a typed-knowledge card adapter in `main/backend/app/services/document_views/writing_card_view.py`.
- The adapter maps `WritingKnowledgeHandoff` into a workbench-compatible `KeywordCardItem`.
- The card uses `source_type=resource` and `publisher=typed_knowledge`; graph projection remains outside this slice.
- The card keeps the typed object identity and selection boundary in `extra`, so frontend/workbench consumers can render or inspect the same stable fields without a large UI rewrite.
- Added unit coverage in `main/backend/tests/unit/test_writing_keyword_card_service_unittest.py` for:
  - handoff contract version
  - selection hash preservation
  - typed knowledge object identity
  - topic/booklet pass-through fields
  - downstream-ready visibility scope

## Plan Closure

Locally sealed:

- `E3` evidence vs graph context boundary is locally extended: typed knowledge is consumed as an explicit resource card, not as implicit graph context.
- `E8` cross-theme dependency contract is locally sealed for the writing side of typed knowledge consumption; graph projection ownership remains with the graph worker.
- `E9` minimum regression gate is strengthened with a focused unit test for the typed-knowledge card/selection contract.

Still partial:

- `E4` templates and generated artifacts remain partial; this slice does not add a generated-artifact model.
- `E5` remains sealed only for Markdown export; non-Markdown adapters are still deferred.
- `E7` surface refactor remains open; `WritingWorkbenchPage.tsx` is intentionally untouched.
- Live frontend E2E remains a broader environment gate and was not run for this backend contract slice.

## Validation

```bash
/Users/wangyiliang/.local/bin/python3.11 -m pytest main/backend/tests/unit/test_writing_keyword_card_service_unittest.py -q
```

Observed:

- `4 passed in 1.54s`
