# MRW Functorial Structural Debt Remediation Progress (v1)

- Status: `S0_S8_COMPLETE_MUTABLE_PROGRESS · NOT_AUTHORITY`
- Date: `2026-09-05`
- Frozen review: `docs/governance/functorial-project-review-2026-09-04.v1.md`
- Frozen plan: `docs/governance/functorial-structural-debt-remediation-plan.v1.md`
- Freeze manifest: `docs/governance/functorial-structural-debt-remediation.freeze.v1.json`
- Mechanical gate: `functorial-kit.json` + `arch-baseline.json`
- Goal mode: complete under frozen-plan completion definition

## 1. Current state

```text
S0_FREEZE_AND_PROGRESS_DOC: COMPLETE
S1_REPRESENTATION_CENSUS_C7_REGISTRATION: COMPLETE
S2_LIGHTWEIGHT_PROJECTION_CORRECTION: COMPLETE
S3_INGEST_SOURCE_LIBRARY_ADAPTER_BOUNDARY: COMPLETE_CURRENT_IMPORT_DIRECTION_ZERO
S4_DERIVED_AUTHORITY_MARKERS: COMPLETE_BOUNDED_AUTHORITY_SCOPE
S5_FAILURE_FAMILY_AND_TARGETED_NO_THROW: COMPLETE_C2_B5_C7_B8_NOT_AUTHORITY
S6_SHARED_HELPER_CONSOLIDATION: COMPLETE_THIRTEEN_CURRENT_DEV_GIT_HELPERS
S7_C8_C9_REGISTRATION: COMPLETE
S8_REMAINING_FAMILIES: COMPLETE_REGISTRATION_SCOPE_CRAWLER_DEFERRED_NO_MULTI_INTERPRETER
```

Current mechanical baseline:

```text
fail_keys=727
fail_key_breakdown=derived-marked:514, import-direction:0, no-throw-in-core:213
raw_fail_findings=3123
report_notices=257
new_failures=0
stale_baseline_keys=0
architecture_ratchet=271 passed; baseline=727, raw_fail=3123, report=257, new=0, stale=0
project_root_full_suite=725 passed, 2 warnings, 53 subtests passed in 8.84s
exact_byte_candidate_and_predecessor_aggregate=100 passed, 2 warnings
completion5_classification=727/727 classified; scheduled=528, cli_or_report=173, legacy=25, shell=1, unclassified=0
kit_python_fresh=43 passed, 1 warning; ruff PASS
kit_typescript_historical=40 passed; tsc --noEmit passed; fresh retry blocked by absent node_modules
kit_rust_fresh_laws=31 passed plus 1 init acceptance in a content-identical temporary copy; default feature compile failed; 3 doc tests ignored
frontend_current=lint PASS; TypeScript PASS; Vite build PASS; Storybook build PASS; static gates 19/19; isolated runtime visual gates 2/2
backend_full_isolated_original=3450 collected, 19 collection errors, 1 skipped; PostgreSQL localhost:5432 blocked
backend_full_isolated_residual=76 failed, 2453 passed, 921 skipped, 1 deselected, 56 subtests; 19 PostgreSQL-blocked files excluded and one DuckDuckGo native-abort test deselected
backend_full_isolated_s0_s8_direct_failures=0 successor_runtime, architecture, functorial, exact-byte, or failure-registration failures in residual JUnit
backend_frozen_surface_after_isolated_run=1554 files; changed_bytes=0, missing=0, changed_mtime_only=0
```

The `271 passed` architecture result uses the repository Python 3.11 source plus the patched local kit through `--with-editable`; non-editable `uv --with <path>` may resolve stale cached code. The current project-root `tests/` aggregate uses the backend Python 3.11 environment plus source-path kit binding. The earlier `274`, `279`, `295`, `298`, and project-root `686 passed, 40 subtests passed` results are historical within this working session. None is a backend-wide or production-runtime completion claim.

The earlier backend S2-S8 focused aggregate had `12 failed, 209 passed, 25 skipped` because frozen family fragments no longer matched current source bytes. That result is superseded for the repaired exact-byte surface by the additive B5/B8/B10 candidate and predecessor aggregate (`100 passed, 2 warnings`) plus the staging primitive suite (`18 passed`). The candidates remain evidence only: they do not promote, rewrite, or transfer authority from frozen canonical artifacts.

## 2. Authority ceiling

This progress document authorizes implementation work only within the frozen plan. It does not authorize:

- production canonical write;
- live provider;
- external delivery;
- cutover;
- authority transfer;
- candidate promotion;
- mutation of frozen migration artifacts.

## 3. Work package ledger

| Package | State | Baseline delta | Verification | Blocker / note |
| --- | --- | ---: | --- | --- |
| S0 freeze + progress | COMPLETE | 0 | `freeze-manifest-exact-check: PASS`; kit full ratchet `274 passed in 1.23s` | Complete. |
| S1 representation census + C7 registration | COMPLETE | 0 removed / 0 added | C7 registration `4 passed`; C7 focused pure suite `57 passed`; full kit `279 passed` | Complete: representation census, alternatives/input/format/disposition vocabularies, terminal failure family, four C7 ports, five token codecs, and witness sketch. |
| S2 lightweight projection correction | COMPLETE | 0 removed / 0 added | focused projection `6 passed, 2 warnings`; full kit `278 passed` | Stored program is the sole executable representation; prior output routes to dependent steps; typed status/error/retry is preserved; operator schemas derive from CoreToolSpec; closed risk/failure vocabularies and domain writers are in place; import-time seeding/filesystem creation removed. |
| S3 ingest/source-library adapter boundary | COMPLETE | import-direction 1 -> 0 / 0 added | architecture `271 passed`; C7 B8 candidate live/history checks green | Cleanup, discovery, graph, LLM, online-lottery, resource-pool, ingest, and source-library construction now depend on explicit ports/composition roots. Frozen C7 evidence was not rewritten; B8 binds the current witness bytes and remains NOT_AUTHORITY. |
| S4 derived authority markers | COMPLETE_BOUNDED_SCOPE | -6 repaired / 0 added | typed-knowledge focused `25 passed`; authority negative subset `4 passed`; C7/C9 sidecars focused green | Priority preflights, quality signals, generated evidence, and typed-knowledge simulations/views are explicitly non-authoritative. Prepared commands remain correctly non-derived. No live DB/browser/production authority is claimed. |
| S5 failure-family + targeted no-throw | COMPLETE_PLANNED_SCOPE | 0 added | C2 B5 and C7 B8 live/history checks green; exact-byte aggregate `100 passed, 2 warnings`; staging suite `18 passed`; FirstSpecimen `4 passed` | C2/C7 closed runtime families are accepted only in additive candidates. FirstSpecimen retains its eight-code local shell family and capability-owned passthrough. No candidate promotion or canonical rewrite occurred. |
| S6 shared helper consolidation | COMPLETE_TARGET_SCOPE | fail keys unchanged; report 260 -> 257 | AST equivalence `26/26`; unit `4 OK`; architecture/helper `269 passed, 13 subtests`; entry smokes `26/26` | `scripts/_current_dev_git.py` is shared by wave8-wave20 (13 scripts). The smokes prove stable imports/entry execution, not checker success; formal_release remains an intentional isolated exception. |
| S7 C8/C9 registration | COMPLETE | 0 removed / 0 added | C8/C9 registration included in prior `303 passed`; current project-root `725 passed, 2 warnings, 53 subtests` | C8 operation/failure families and C9 projection/source vocabularies/failure family are registered with existing witnesses. Registration does not claim runtime cutover. |
| S8 remaining families | COMPLETE_REGISTRATION_SCOPE | 0 removed / 0 added | provider failure focused `15 passed`; architecture `271 passed`; current project-root `725 passed, 2 warnings, 53 subtests` | Shared generator, scheduled automation, LLM provider, and seven provider failure families are registered. CrawlerProvider is explicitly deferred because it has one production interpreter and no shared typed Scrapyd effect boundary; no false port/failure closure was added. Market/policy iteration, collect execution/routing, and provider-specific operational conversion remain declared losses. |

## 4. Baseline ledger

Every package must append:

```text
package
changed files
baseline keys removed by gate
baseline keys added (expected 0)
classification of each removed key
focused command and exact result
full kit ratchet result
rollback route
timestamp
```

Baseline rewrite is prohibited except to remove stale keys created by completed, reviewed changes.

### S3 classification delta 1

```text
before: 1191 fail keys
after: 947 fail keys
delta: -244
no-throw-in-core: 568 -> 347 (-221)
import-direction: 102 -> 79 (-23)
derived-marked: 521 -> 521 (0)
reason: main/backend/scripts and root scripts are CLI/report shell paths, not pure core
verification: full kit ratchet 279 passed in 1.19s
new_failures: 0
rollback: restore scripts to core_paths and regenerate the exact baseline
```

### S3 delta 2

```text
before: 942 fail keys
after: 873 fail keys
delta: -69
code repair: collect-runtime concrete adapter imports removed (-5)
topology repair: adapter registries, composition/main/celery/tasks, startup/web UI classified shell (-64)
remaining import-direction keys: 23
new_failures: 0
verification: full kit ratchet 281 passed in 1.40s
rollback: remove collect composition registration and restore the prior coarse scanner topology
```

### S4 delta 1

```text
before: 873 fail keys
after: 868 fail keys
delta: -5
repaired: agent-batch symbolic quality/promotion preflight builders
new_failures: 0
verification: focused tests 15 passed; architecture ratchet 268 passed
rollback: restore plain dict returns and the five baseline keys
```

### S3 delta 3

```text
before: 863 fail keys
after: 850 fail keys
delta: -13
repaired:
  resource_pool HTTP and official-access imports (-5)
  ingest fetch/parser imports to shared HTTP port (-8)
  market/policy/news/social concrete provider imports behind ports (-5, after -13 bridge)
registered ports:
  HttpFetchPort
  OfficialAccessPort
  MarketAdapterPort
  PolicyAdapterPort
  RedditPort
  GoogleNewsPort
new_failures: 0
verification: architecture ratchet 269 passed; focused laws/provider suites green
rollback: restore concrete imports and the corresponding baseline keys
```

### S3 delta 4

```text
before: 850 fail keys
after: 849 fail keys
delta: -1
repaired:
  discovery application imports DiscoveryAdapterPort only
  DefaultDiscoveryAdapter construction moved to app/composition/discovery.py
new_failures: 0
verification: module wiring 1 passed; architecture ratchet 269 passed
blocked focused aggregate: discovery core-contract collection opens an existing
  workflow-graph PostgreSQL store at import time; no discovery assertion executed
rollback: restore build_default and the single baseline key
```

### S5 delta 1

```text
before: 850 fail keys
after: 850 fail keys
delta: 0
registered failure family:
  typed_knowledge.persistence_boundary_failure
registered boundary code:
  typed_knowledge_persistence_boundary_violation
observable repair:
  TypedKnowledgePersistenceBoundaryError carries the stable code
  typed-knowledge API error details preserve that code
granularity:
  boundary-level closure only; internal validation diagnostics remain messages
new_failures: 0
verification: backend focused 19 passed; registration + architecture 272 passed; full kit 295 passed
unexecuted: repository recursive root suite (uv kit environment lacks sqlalchemy;
  backend Python environment lacks hypothesis and the required editable-kit export surface;
  combined requirements environment is blocked building psycopg2-binary 2.9.9 on Python 3.13)
rollback: remove the typed failure projection/registry row and API details field
```

### S5 delta 2

```text
before: 850 fail keys
after: 850 fail keys
delta: 0
registered failure family:
  c2.shared.contract_failure
registered categories:
  schema, digest, scope, catalog, mode, provider_effect, terminal, legacy_input_union
witness:
  AST classification covers every current constructor raise owner
runtime source sha256:
  5b366cb7d7e316b59ad57e794a608170a705f4032730a24798e5bb3d967e57c1 (unchanged)
state:
  registration projection complete; typed runtime closure not claimed
new_failures: 0
verification: C2 registration + architecture 272 passed; full kit 298 passed
rollback: remove the C2 kit projection, registry row, and registration tests
```

### S3/S5 topology and boundary delta

```text
before observed snapshot: 843 fail keys
after boundary/topology packages: 729 fail keys
delta: -114
repaired:
  graph normalizer injected by the script composition shell
  LLM provider construction moved behind LLMProviderPort
  online-lottery concrete market factories moved to composition
classified shell topology:
  successor_migration
  successor_runtime assembly/specification/substrate
  determined service effect shells
remaining import-direction:
  cleanup_executor.py -> ingest.adapters.http_utils (exact-byte C7 fragment blocker)
new_failures: 0
verification: architecture ratchet 268 passed
rollback: restore the boundary call sites and the corresponding exact baseline keys
```

### S4 delta 2

```text
before: 729 fail keys
after: 728 fail keys
delta: -1
repaired:
  build_source_quality_signals returns list[NonAuthoritativeDict]
  each signal is derived_as=view while preserving the legacy dict/JSON ABI
new_failures: 0
verification: focused agent-batch tests green; architecture ratchet 268 passed
rollback: restore plain dict signal items and the exact baseline key
```

### S6 delta 1

```text
fail baseline: unchanged at 728
report notices: 260 -> 259
consolidated:
  root and backend automation CLI repo_root mechanics
preserved exception:
  formal_release owns an isolated repo_root implementation outside this lane
new_failures: 0
verification: focused helper 1 passed; 22 direct/module --help smokes green
rollback: restore local _repo_root helpers and remove the shared backend re-export
```

### S7/S8 registration delta 1

```text
fail baseline: unchanged at 728
registered:
  C8 operation vocabulary and four failure families
  C9 projection/source vocabularies and projector failure family
  shared P3/P4 representative fragment codecs and generator failure family
  scheduled automation evidence report codec, seven vocabularies, and failure family
  LLM provider name, port, and resolution failure family
authority:
  registration projection only; no runtime adoption, evidence rebind, promotion, or cutover
verification:
  registration/focused/architecture aggregate 303 passed
  project-root full suite 686 passed, 40 subtests passed
rollback: remove only the additive declarations, registry rows, sketches, and focused tests
```

### S8 registration delta 2

```text
fail baseline: unchanged at 728
registered failure families:
  ingest.market.failure
  ingest.policy.failure
  ingest.reddit.failure
  ingest.google_news.failure
  resource_pool.http_fetch.failure
  resource_pool.official_access.failure
  collect.runtime.failure
runtime correction:
  exhausted HTTP 5xx retries preserve http_status, status_code, and retryable metadata
declared losses:
  market/policy provider iteration exceptions remain observable but are not converted
  Reddit/Google News fetch methods intentionally remain best-effort total
  collect execution/routing/auto-batch failure conversion is outside this registration closure
new_failures: 0
verification: provider/HTTP focused 15 passed; architecture ratchet 267 passed
rollback: remove only the seven additive failure projections and sketches; restore the prior HTTP retry-exhaustion wrapper
```

### S3-S6 completion delta

```text
S3:
  import-direction baseline 1 -> 0
  cleanup and source-library construction now cross explicit port/composition boundaries
  C7 current witness bytes are carried only by additive Stage B8 evidence
S4:
  typed-knowledge simulation/view envelopes carry authoritative=false
  reserved/public project identities fail before bind_project
  GET projections remain read-only; explicit POST writer boundaries are preserved
S5:
  C2 Stage B5 and C7 Stage B8 runtime/failure closure candidates independently accepted
  every candidate authority field remains false
S6:
  wave8-wave20 use scripts/_current_dev_git.py for the two shared git operations
  13 direct and 13 package entry smokes are import-stable
new_failures: 0 after the I1 generator derived-value marker repair
verification:
  architecture 271 passed; baseline=727, raw_fail=3123, report=257, new=0, stale=0
  S4 focused 25 passed; authority negative subset 4 passed
  S6 AST equivalence 26/26; unit 4 OK; entry smokes 26/26
rollback:
  package-local reversals only; do not mutate frozen review, plan, canonical evidence, or old candidates
```

### Additive exact-byte candidate closure

```text
C2 Stage B5:
  candidate_id=2d00693facbcb71aab9177519844a3150c6d96240db318c3fcb0f357d2d85936
C4 Stage B8:
  candidate_id=c5a956bbc493dd6e9868bfd6213d94a37853e2a53d707690b5e290061a454c66
C6 Stage B8:
  candidate_id=633b0d322f7f7c3ad9dee3e7af02fdf81c1548f5815a3de6bdccbf5a6a3c2815
C7 Stage B8:
  candidate_id=446c3164ca675d78e00b4a9a5bb6e555be1b4b01365dfdc2fa22ef016ea88484
C9 Stage B8:
  candidate_id=49a6afb7efd36b20746ccdbdb8aabe811b2799221d64063c68e3e946522dd1f8
I1 Stage B9 predecessor:
  candidate_id=67ae384be170801a501f176969fa5d3ba2b3a2fb4280e5fd80d710142ddc325e
  status=HISTORY_SNAPSHOT_VALID_NOT_AUTHORITY
I1 Stage B10 current:
  candidate_id=2104fa8acc6e079d66d0ff90c416d9d39e280cce6b8d5b4df0a7740a14822b98
  amendment=STAGE_B10_I1_DERIVED_MARKER_REBIND_CANDIDATE_NOT_AUTHORITY
verification:
  candidate/predecessor exact-byte aggregate 100 passed, 2 warnings
  B10 generator CHECK_OK; live and history candidate checks green
authority:
  CANDIDATE_VALID_NOT_AUTHORITY only
  no promotion, canonical write, runtime cutover, authority transfer, or frozen evidence rewrite
```

### Completion definition item 5

```text
artifact:
  docs/governance/functorial-structural-debt-remediation-completion5-classification.v1.json
sha256:
  954af8ef72ebd5a8955597d771eafd1aaeb3684c3f9e1079b1306f0c0d0e1137
baseline_keys: 727
classified:
  SCHEDULED_SEMANTIC_REPAIR=528
  CLI_OR_REPORT=173
  LEGACY_COMPATIBILITY=25
  SHELL_BOUNDARY=1
  UNCLASSIFIED=0
status:
  ACTIVE_MUTABLE_CLASSIFICATION_NOT_AUTHORITY
meaning:
  all remaining baseline keys are explicitly classified; they are not claimed physically repaired or removed
```

### Kit realization validation

```text
checkout: /Users/wangyiliang/Desktop/functorial-kit
head: 785ff25e201c9eae84c862e68e786bc975e7a800-dirty
python fresh: 43 passed, 1 warning
python ruff fresh: all checks passed
python pyright fresh: blocked, command unavailable
typescript historical: 40 passed; tsc --noEmit passed
typescript fresh retry: blocked/unexecuted because node_modules is absent and dependency installation was outside scope
rust default fresh: failed at compile time with 5 feature-gating errors in tests/core.rs; 0 tests executed
rust laws fresh: 31 passed in checkout plus 1 init acceptance passed in a content-identical temporary copy
rust doc fresh: 3 ignored
rust clippy/fmt fresh: blocked because cargo-clippy and cargo-fmt are not installed
scope: validates a dirty local kit checkout and records all negative evidence; it does not prove a clean kit release or MRW production readiness
```

## 5. Current blockers

```text
BACKEND_FULL_SUITE_ENVIRONMENT_AND_DIRTY_TREE_UNSAFE
KIT_TYPESCRIPT_DEPENDENCIES_NOT_INSTALLED_FOR_FRESH_RETRY
KIT_RUST_DEFAULT_FEATURE_TEST_COMPILE_FAILURE
KIT_PYRIGHT_CLIPPY_FMT_UNAVAILABLE
ALL_CANDIDATES_NOT_AUTHORITY
```

These are validation, release, and authority ceilings, not unfinished S0-S8 implementation packages. A fresh isolated backend copy preserved all 1554 frozen/candidate/governance-bound files exactly. Its original full collection stopped at `3450 collected, 19 errors` because PostgreSQL localhost access was blocked. After excluding those 19 environment-blocked files, the run reached a native abort in DuckDuckGo initialization; deselecting only that test and supplementing the copy with root tests, frontend source, and current automation directories produced a normal residual summary of `76 failed, 2453 passed, 921 skipped, 1 deselected, 56 subtests passed`. The residual JUnit contains zero successor-runtime, architecture, functorial, exact-byte, or failure-registration failures. The remaining 76 are current negative evidence for missing historical artifacts, other dirty-tree contracts, and environment-bound surfaces, not S0-S8 completion evidence.

The 727 remaining architecture baseline keys satisfy frozen-plan completion item 5 only because every key is explicitly classified. The 528 scheduled semantic repairs remain future package work; classification does not convert them into repaired code. Likewise, current B5/B8/B10 artifacts and the B9 predecessor remain `NOT_AUTHORITY`.

## 6. Next action

No S0-S8 implementation package remains open under the frozen plan. Keep this mutable ledger and the three maps synchronized with fresh scans. Any candidate promotion, canonical evidence write, live provider claim, production cutover, clean kit release, or the 528 scheduled semantic repairs requires a separately authorized package and its own witnesses.
