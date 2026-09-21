# Contract 13 factual-evidence claim decisions v2

Decision: `DECISION_TABLE_COMPLETE_ACCEPTANCE_NOT_CLAIMED`.

This is a deduplicated routing table for the frozen 30 `missing_evidence` nodeids. It does not restore deleted evidence, perform live probes, create canonical status, or accept Stage 1.

## Summary

- Unique claims: 16
- Nodeids covered exactly once: 30
- `ACTUAL_HISTORICAL_RECEIPT_REQUIRED`: 8 nodeids
- `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE`: 13 nodeids
- `LIVE_OBSERVATION_REQUIRED`: 9 nodeids

| Claim | Decision | Nodeids | Factual boundary |
| --- | --- | ---: | --- |
| `claim-001` / `crawler-public-replay-gate-recorded-run` | `ACTUAL_HISTORICAL_RECEIPT_REQUIRED` | 1 | The recorded crawler public replay used the exact manifest and passed the reviewed real-public-replay gate. |
| `claim-002` / `crawler-source-expansion-recorded-closure` | `ACTUAL_HISTORICAL_RECEIPT_REQUIRED` | 2 | The recorded crawler source-expansion closure mapped plan tasks to code/evidence and closed only after public-replay review. |
| `claim-003` / `ingest-canary-current-authority-projection` | `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE` | 2 | The current Wave51/56/57 authority documents and indexes preserve the three ingest-canary topic dispositions without treating Wave27 history as current authority. |
| `claim-004` / `source-library-a5-recorded-public-replay` | `ACTUAL_HISTORICAL_RECEIPT_REQUIRED` | 2 | The recorded A5 source-library public replay used the frozen input and received the recorded relevance review. |
| `claim-005` / `wave10-fresh-deterministic-vector-quality` | `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE` | 1 | Current repo-local keyword/vector/hybrid runtime and deterministic benchmark behavior can be recomputed and aggregated without live-provider authority. |
| `claim-006` / `wave12-current-open-search-runtime-readiness` | `LIVE_OBSERVATION_REQUIRED` | 6 | Current configured OpenSearch/SearXNG/YaCy endpoints have an observed runtime state distinguishable from configuration-only or connect-error state. |
| `claim-007` / `wave12-current-provider-readiness` | `LIVE_OBSERVATION_REQUIRED` | 2 | Current local-index modes and explicit SearXNG/YaCy provider routes have observed readiness while unsupported claims remain visible. |
| `claim-008` / `wave14-fresh-local-provider-capability` | `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE` | 1 | Current repo-controlled mode capability and the retained external-provider gap can be recomputed from fresh non-live evidence. |
| `claim-009` / `wave18-fresh-deterministic-hybrid-readback` | `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE` | 1 | Current repo-local deterministic adapter preserves keyword/vector/hybrid mode identity and readback without a live-provider closure claim. |
| `claim-010` / `wave19-fresh-derived-provider-manifest` | `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE` | 2 | A current non-live provider manifest can be deterministically derived from fresh Wave14 capability and Wave18 readback receipts. |
| `claim-011` / `wave27-wave29-fresh-manifest-and-topic-readback` | `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE` | 4 | Current canonical topic projections and a fresh non-live Wave19 manifest can be deterministically replayed without claiming live platform SLA. |
| `claim-012` / `wave29-current-platform-api-ui-sla` | `LIVE_OBSERVATION_REQUIRED` | 1 | The current scheduler/tenant/API/UI platform condition has been observed live for the Wave29 OSS-node route. |
| `claim-013` / `wave55-fresh-controlled-search-quality` | `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE` | 1 | Current controlled repo-local open-search ranking and local embedding quality can be recomputed without network or live-container claims. |
| `claim-014` / `wave57-recorded-production-like-corpus-lineage` | `ACTUAL_HISTORICAL_RECEIPT_REQUIRED` | 2 | The recorded Wave57 production-like vector replay used the historical corpus lineage and prerequisite Wave56/provider artifacts claimed by that run. |
| `claim-015` / `wave57-fresh-public-oss-corpus-relevance` | `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE` | 1 | Current checked-in public OSS corpus excerpts can be deterministically ranked by the repo-local embedding route for the bounded OSS-node topic. |
| `claim-016` / `wave8-recorded-evidence-reuse` | `ACTUAL_HISTORICAL_RECEIPT_REQUIRED` | 1 | The Wave8 aggregate reused the recorded provider trace, container replay, LanceDB runtime and benchmark evidence without claiming live services. |

## Decision details

### claim-001: crawler-public-replay-gate-recorded-run

The recorded crawler public replay used the exact manifest and passed the reviewed real-public-replay gate.

Decision: `ACTUAL_HISTORICAL_RECEIPT_REQUIRED`.

Missing evidence: The historical manifest, public replay output/transcript, checker result, and review receipt bound to the same run identity.

Authority boundary: A designated historical-evidence custodian must verify the tracked historical objects and issue a new read-only receipt. This task may cite history-only identity but may not restore or copy the deleted files into their old paths.

Dependent nodeids:

- `tests.unit.test_crawler_public_replay_gate_unittest.CrawlerPublicReplayGateUnitTestCase::test_gate_validates_deterministic_artifacts_and_detects_real_public_replay`

### claim-002: crawler-source-expansion-recorded-closure

The recorded crawler source-expansion closure mapped plan tasks to code/evidence and closed only after public-replay review.

Decision: `ACTUAL_HISTORICAL_RECEIPT_REQUIRED`.

Missing evidence: The historical closure decision, provider-handoff check, validation-pack output, and public-replay review references for one run lineage.

Authority boundary: Historical-object readback and semantic acceptance require supervisor/evidence-custodian authorization. No current closure status may be inferred from the HEAD blobs and no deleted package may be restored.

Dependent nodeids:

- `tests.unit.test_crawler_source_expansion_closure_check_unittest.CrawlerSourceExpansionClosureCheckUnitTest::test_closure_check_maps_plan_tasks_to_current_code_and_evidence`
- `tests.unit.test_crawler_source_expansion_closure_check_unittest.CrawlerSourceExpansionClosureCheckUnitTest::test_overall_status_closes_after_public_replay_review`

### claim-003: ingest-canary-current-authority-projection

The current Wave51/56/57 authority documents and indexes preserve the three ingest-canary topic dispositions without treating Wave27 history as current authority.

Decision: `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE`.

Existing generator chain:

- `main/backend/scripts/check_ingest_canary_closure_readiness.py` (`sha256:e3a37b27ae9f440ce5fc35b3713d6f40fc2632f8674b5312e4b43c2f38adcab5`)

Expected artifact:

- `stage1-successor-evidence/contract13-bounded-corrections-v2/claim-decisions/proposed-artifacts/ingest-canary-current-authority-readback.v2.json`

Ceiling: Current repo documentation/authority projection only; not a canary, runtime, deployment, or release receipt.

Dependent nodeids:

- `tests.unit.test_ingest_canary_closure_readiness_unittest.IngestCanaryClosureReadinessTest::test_retains_current_dev_when_repo_local_blockers_remain`
- `tests.unit.test_ingest_canary_closure_readiness_unittest.IngestCanaryClosureReadinessTest::test_write_output_round_trips_report_file`

Read-only canonical anchors:

- `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/INDEX.md` (`sha256:7c9e761b9bcb6e314b7f2907a75adc5c2caf404fe4fa1ae2252e8474d1e525f6`)
- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md` (`sha256:0563941ec3ccd96a9d3cb133727f97d2de47d75ace7cf68bf86d9d4bd3dc31bc`)
- `development/latest-dev-docs/development-plans/TARGET_TOPIC_ALLOWLIST.json` (`sha256:ce35b86f548c64dd1d2dc8d84aad898b58245dcba737ce9dfb700b340681599b`)
- `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-ingest-platformization-assessment/10_wave51-non-target-assessment-wrapper-reclassification-2026-05-23.md` (`sha256:44f724b61793bb3b9fa4b4288887fc9860bbbbd1390bf753c6211b6a37ce7582`)
- `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-meaningful-ingest-guardrails-plan/13_wave56-strict-promotion-final-gate-2026-05-24.md` (`sha256:305b03d206308722bf316224c0a43b56883e3b6e0ae50cf4aca75191a4d277e6`)
- `development/latest-dev-docs/development-plans/ARCHIVE_EXTERNAL_BLOCKED/2026-03-02-single-url-first-ingest-allocation-plan/13_wave57-single-url-external-blocker-closure-2026-05-24.md` (`sha256:32f1f4e43b760852b578f2c498b386ed335c77efcd1d3b1201e999a758c42a44`)

### claim-004: source-library-a5-recorded-public-replay

The recorded A5 source-library public replay used the frozen input and received the recorded relevance review.

Decision: `ACTUAL_HISTORICAL_RECEIPT_REQUIRED`.

Missing evidence: The historical input, real/public probe or replay outputs and logs, A5 gate result, and human relevance-review receipt bound to one execution.

Authority boundary: Only an authorized historical evidence readback can establish the past run. A new public replay would be a new live observation, not a replacement for the historical claim; synthetic fixtures cannot close it.

Dependent nodeids:

- `tests.unit.test_source_library_public_replay_a5_gate_unittest.SourceLibraryPublicReplayA5GateUnitTestCase::test_a5_gate_freezes_manifest_fixture_and_reviewed_public_replay`
- `tests.unit.test_source_library_public_replay_a5_gate_unittest.SourceLibraryPublicReplayA5GateUnitTestCase::test_term_fallback_public_fixture_remains_relevance_review`

### claim-005: wave10-fresh-deterministic-vector-quality

Current repo-local keyword/vector/hybrid runtime and deterministic benchmark behavior can be recomputed and aggregated without live-provider authority.

Decision: `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE`.

Existing generator chain:

- `ops/search-lab/scripts/search_provider_trace_contract.py` (`sha256:6b49b9fedd44386556f84a1a2f58ea8f1d2919463c832ad9f139f417a2a14343`)
- `ops/search-lab/scripts/local_index_lancedb_runtime_smoke.py` (`sha256:3744e2c4923792a725e3ca51574a372dab81f6847a6e1229505a712cdcab96e8`)
- `ops/search-lab/scripts/local_index_lancedb_benchmark_quality.py` (`sha256:4380536a71d8aaf0a018edf3031128a2d283b2e69c03fe91973e57852096271c`)
- `ops/search-lab/scripts/wave10_vectorization_quality_gate.py` (`sha256:14659ba8a69215139f4aaf80687153d59f3980ed39cd14aab2a0e0d1e4690e4d`)

Expected artifact:

- `stage1-successor-evidence/contract13-bounded-corrections-v2/claim-decisions/proposed-artifacts/wave10-vector-quality-fresh-local.v2.json`

Ceiling: Repo-local deterministic quality only; provider-live, production-semantic-quality, promotion and release claims remain forbidden.

Dependent nodeids:

- `tests.unit.test_wave10_vectorization_quality_gate_unittest.Wave10VectorizationQualityGateTest::test_gate_checks_provider_trace_modes_thresholds_and_fallback_reason`

### claim-006: wave12-current-open-search-runtime-readiness

Current configured OpenSearch/SearXNG/YaCy endpoints have an observed runtime state distinguishable from configuration-only or connect-error state.

Decision: `LIVE_OBSERVATION_REQUIRED`.

Missing evidence: A fresh service-identity/config snapshot plus actual connection/query responses, timestamps, endpoint identity, failures, and an unsealed readback receipt.

Authority boundary: Requires explicit authorization to probe the named local services/containers and permission to record the responses. Do not start services, use network, or infer live state from mocks under this contract.

Dependent nodeids:

- `tests.unit.test_open_search_health_artifact_schema_readback_unittest.OpenSearchHealthArtifactSchemaReadbackTest::test_schema_readback_distinguishes_compose_config_from_stopped_connect_error`
- `tests.unit.test_open_search_health_artifact_schema_readback_unittest.OpenSearchHealthArtifactSchemaReadbackTest::test_schema_readback_records_real_live_probe_response_without_closure`
- `tests.unit.test_open_search_health_artifact_unittest.OpenSearchHealthArtifactTest::test_running_live_probe_remains_unsealed_and_explicit_only`
- `tests.unit.test_open_search_health_artifact_unittest.OpenSearchHealthArtifactTest::test_stopped_services_record_connect_error_without_live_closure`
- `tests.unit.test_open_search_runtime_boundary_unittest.OpenSearchRuntimeBoundaryTest::test_connect_error_is_reported_as_service_not_started_without_failing_boundary_gate`
- `tests.unit.test_open_search_runtime_boundary_unittest.OpenSearchRuntimeBoundaryTest::test_live_query_success_remains_unsealed_and_explicit_only`

### claim-007: wave12-current-provider-readiness

Current local-index modes and explicit SearXNG/YaCy provider routes have observed readiness while unsupported claims remain visible.

Decision: `LIVE_OBSERVATION_REQUIRED`.

Missing evidence: Fresh local-index mode probes and real explicit-provider responses with route/family/auto-inclusion trace, timestamp, environment identity, and unsupported-claim propagation.

Authority boundary: The existing Wave12 generator may be used only after live-probe authorization and after fresh non-live prerequisites are supplied. A --skip-live-probes output is useful but cannot satisfy this claim.

Dependent nodeids:

- `tests.unit.test_wave12_provider_readiness_gate_unittest.Wave12ProviderReadinessGateTest::test_gate_reports_live_probe_status_fallbacks_and_unsupported_claims`
- `tests.unit.test_wave12_provider_readiness_gate_unittest.Wave12ProviderReadinessGateTest::test_skip_live_probes_keeps_gate_passed_with_not_run_visibility`

### claim-008: wave14-fresh-local-provider-capability

Current repo-controlled mode capability and the retained external-provider gap can be recomputed from fresh non-live evidence.

Decision: `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE`.

Existing generator chain:

- `main/backend/scripts/check_wave14_vectorization_provider_capability.py` (`sha256:3fbce21722f0d560a3446e6135c2af497d19a52c0971ce236b7755506c446abb`)
- `ops/search-lab/scripts/wave10_vectorization_quality_gate.py` (`sha256:14659ba8a69215139f4aaf80687153d59f3980ed39cd14aab2a0e0d1e4690e4d`)
- `ops/search-lab/scripts/wave12_provider_readiness_gate.py` (`sha256:f08ee676c7e17611340acb9b0918f504722140b1d206c8cbee0db90862331c94`)

Expected artifact:

- `stage1-successor-evidence/contract13-bounded-corrections-v2/claim-decisions/proposed-artifacts/wave14-provider-capability-fresh-local.v2.json`

Ceiling: Local capability and explicit retained-gap report only; no external-provider/live-quality or closure authority.

Dependent nodeids:

- `tests.unit.test_wave14_vectorization_provider_capability_unittest.Wave14VectorizationProviderCapabilityTest::test_gate_reports_local_capability_external_gap_and_no_closure_claim`

### claim-009: wave18-fresh-deterministic-hybrid-readback

Current repo-local deterministic adapter preserves keyword/vector/hybrid mode identity and readback without a live-provider closure claim.

Decision: `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE`.

Existing generator chain:

- `ops/search-lab/scripts/wave18_vectorization_hybrid_readback.py` (`sha256:aa3be28bd3646e01130ba2b519daf785e5052e38f3494a2145ba4be3f20fa314`)

Expected artifact:

- `stage1-successor-evidence/contract13-bounded-corrections-v2/claim-decisions/proposed-artifacts/wave18-hybrid-readback-fresh-local.v2.json`

Ceiling: Deterministic adapter/readback behavior only; semantic quality, provider-live closure and production authority remain false.

Dependent nodeids:

- `tests.unit.test_wave18_vectorization_hybrid_readback_unittest.Wave18VectorizationHybridReadbackTest::test_checker_proves_mode_identity_quality_trace_and_readback_without_live_closure`

### claim-010: wave19-fresh-derived-provider-manifest

A current non-live provider manifest can be deterministically derived from fresh Wave14 capability and Wave18 readback receipts.

Decision: `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE`.

Existing generator chain:

- `ops/search-lab/scripts/wave19_vectorization_provider_manifest_readback.py` (`sha256:f5e6d56e5e3ef41436aeb9ec91b787843ef6a16ac10f83820681bbdac2686d94`)

Expected artifact:

- `stage1-successor-evidence/contract13-bounded-corrections-v2/claim-decisions/proposed-artifacts/wave19-provider-manifest-fresh-local.v2.json`

Ceiling: Derived non-live manifest only; it must retain all external/live/semantic gaps and cannot authorize topic status changes.

Dependent nodeids:

- `tests.unit.test_wave19_vectorization_provider_manifest_readback_unittest.Wave19VectorizationProviderManifestReadbackTest::test_manifest_fails_if_source_trace_claims_live_provider_verification`
- `tests.unit.test_wave19_vectorization_provider_manifest_readback_unittest.Wave19VectorizationProviderManifestReadbackTest::test_manifest_records_modes_fallback_trace_quality_and_no_live_closure`

### claim-011: wave27-wave29-fresh-manifest-and-topic-readback

Current canonical topic projections and a fresh non-live Wave19 manifest can be deterministically replayed without claiming live platform SLA.

Decision: `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE`.

Existing generator chain:

- `ops/search-lab/scripts/wave27_vectorization_closure_gate.py` (`sha256:2a5ca4cf7ecb488951c27607eb6feca1c4539d97878f05861cef63c8b5f9db8a`)
- `ops/search-lab/scripts/wave29_oss_node_vector_manifest_replay.py` (`sha256:23905d0174444ad3eef13ac86acae96ebcde2248add0360039c03531bf9c5b16`)

Expected artifact:

- `stage1-successor-evidence/contract13-bounded-corrections-v2/claim-decisions/proposed-artifacts/wave27-wave29-manifest-replay-fresh-local.v2.json`

Ceiling: Non-live manifest/topic readback only; platform SLA remains open and no new canonical status or migration is authorized.

Dependent nodeids:

- `tests.unit.test_wave27_vectorization_closure_gate_unittest.Wave27VectorizationClosureGateTest::test_gate_fails_if_provider_manifest_claims_closure`
- `tests.unit.test_wave27_vectorization_closure_gate_unittest.Wave27VectorizationClosureGateTest::test_gate_retains_all_three_topics_and_preserves_provider_external_boundary`
- `tests.unit.test_wave29_oss_node_vector_manifest_replay_unittest.Wave29OssNodeVectorManifestReplayTest::test_gate_fails_if_manifest_mode_claims_live_provider`
- `tests.unit.test_wave29_oss_node_vector_manifest_replay_unittest.Wave29OssNodeVectorManifestReplayTest::test_node_manifest_replay_closes_repo_local_oss_node_blockers`

Read-only canonical anchors:

- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/INDEX.md` (`sha256:b1377fd42a6b049428b941a60de7f3472ac4d451e3e8ad9e394d1c9ccb19b00d`)
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/07_wave27-vectorization-closure-decision-2026-05-23.md` (`sha256:3c5818809d0f512dd3b961f6b3477714c89ee6b5752df9a97f457b6bd953ccc8`)
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/08_wave29-oss-node-vector-manifest-replay-2026-05-23.md` (`sha256:9ff6233de1ff5313bbed3e86031e55a8c9e7544661c2e2029c365d037aa96e25`)
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-05-14-global-vectorization-general-foundation/INDEX.md` (`sha256:09255aa414a279bf06ebadf46a36374e778e132f38c65803abdc21c6a4706c10`)
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-05-14-global-vectorization-general-foundation/09_wave27-vectorization-closure-decision-2026-05-23.md` (`sha256:0a0117c5329dd7360a21eae4dab1beccfe86deb0e0f6f5e152c0cedfb7e2a613`)

### claim-012: wave29-current-platform-api-ui-sla

The current scheduler/tenant/API/UI platform condition has been observed live for the Wave29 OSS-node route.

Decision: `LIVE_OBSERVATION_REQUIRED`.

Missing evidence: A fresh Wave29 probe receipt with actual API and UI base identities, request/response timestamps, scheduler/tenant readback, failure details, and environment identity.

Authority boundary: Requires explicit permission to access the local API/UI runtime and record live responses. This contract neither starts those services nor authorizes a live probe.

Dependent nodeids:

- `tests.unit.test_wave29_oss_node_vector_manifest_replay_unittest.Wave29OssNodeVectorManifestReplayTest::test_live_platform_probe_can_close_scheduler_tenant_ui_condition`

### claim-013: wave55-fresh-controlled-search-quality

Current controlled repo-local open-search ranking and local embedding quality can be recomputed without network or live-container claims.

Decision: `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE`.

Existing generator chain:

- `ops/search-lab/scripts/search_provider_trace_contract.py` (`sha256:6b49b9fedd44386556f84a1a2f58ea8f1d2919463c832ad9f139f417a2a14343`)
- `ops/search-lab/scripts/wave55_live_embedding_provider_gate.py` (`sha256:35d17b9fc61226790aeb079b53e5695f0f13bec403c05b8bca98d6d57f4cfb71`)
- `ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py` (`sha256:9c92092498ddaa16559b5117177e41dc90fe65868771d91d4ee51cf8c481fe4b`)

Expected artifact:

- `stage1-successor-evidence/contract13-bounded-corrections-v2/claim-decisions/proposed-artifacts/wave55-oss-search-quality-fresh-local.v2.json`

Ceiling: Controlled repo-local ranking only; live-container and production semantic quality remain unproven.

Dependent nodeids:

- `tests.unit.test_wave55_oss_node_search_quality_gate_unittest.Wave55OssNodeSearchQualityGateTest::test_gate_closes_repo_local_open_search_quality_and_reduces_semantic_scope`

Read-only canonical anchors:

- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/INDEX.md` (`sha256:b1377fd42a6b049428b941a60de7f3472ac4d451e3e8ad9e394d1c9ccb19b00d`)
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/10_wave55-oss-node-search-quality-gate-2026-05-23.md` (`sha256:2bb3c453d321486040fe04c56dc60029de1f602810b2b7aa461516e1449ce20b`)

### claim-014: wave57-recorded-production-like-corpus-lineage

The recorded Wave57 production-like vector replay used the historical corpus lineage and prerequisite Wave56/provider artifacts claimed by that run.

Decision: `ACTUAL_HISTORICAL_RECEIPT_REQUIRED`.

Missing evidence: The historical Wave56 gate, both recorded LanceDB JSONL corpora, four narrative inputs, and the Wave57 vector-store execution receipt bound to one corpus manifest.

Authority boundary: Historical corpus objects must be verified by an authorized evidence custodian. Rebuilding a different current corpus would be a successor experiment, not proof of the recorded claim; no deleted source may be restored by this task.

Dependent nodeids:

- `tests.unit.test_wave57_production_vector_quality_gate_unittest.Wave57ProductionVectorQualityGateTest::test_gate_replays_production_like_corpus_and_closes_when_vector_store_is_available`
- `tests.unit.test_wave57_production_vector_quality_gate_unittest.Wave57ProductionVectorQualityGateTest::test_require_vector_store_passes_in_optional_lancedb_environment`

### claim-015: wave57-fresh-public-oss-corpus-relevance

Current checked-in public OSS corpus excerpts can be deterministically ranked by the repo-local embedding route for the bounded OSS-node topic.

Decision: `FRESH_LOCAL_DETERMINISTIC_EVIDENCE_POSSIBLE`.

Existing generator chain:

- `ops/search-lab/scripts/wave55_live_embedding_provider_gate.py` (`sha256:35d17b9fc61226790aeb079b53e5695f0f13bec403c05b8bca98d6d57f4cfb71`)
- `ops/search-lab/scripts/wave55_oss_node_search_quality_gate.py` (`sha256:9c92092498ddaa16559b5117177e41dc90fe65868771d91d4ee51cf8c481fe4b`)
- `ops/search-lab/scripts/wave57_oss_node_public_corpus_semantic_relevance_gate.py` (`sha256:48346e3ff952910dede974706f0bd9b779c35f13ca0967538eaea26a0a8cd0b9`)

Expected artifact:

- `stage1-successor-evidence/contract13-bounded-corrections-v2/claim-decisions/proposed-artifacts/wave57-public-corpus-relevance-fresh-local.v2.json`

Ceiling: Bounded checked-in-corpus relevance only; no generic public-web, live provider, production traffic, or release authority.

Dependent nodeids:

- `tests.unit.test_wave57_oss_node_public_corpus_semantic_relevance_gate_unittest.Wave57OssNodePublicCorpusSemanticRelevanceGateTest::test_gate_closes_target_local_public_corpus_provider_quality_route`

Read-only canonical anchors:

- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/INDEX.md` (`sha256:b1377fd42a6b049428b941a60de7f3472ac4d451e3e8ad9e394d1c9ccb19b00d`)
- `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-05-oss-node-platform-io-plan/11_wave57-oss-node-public-corpus-semantic-relevance-2026-05-23.md` (`sha256:9f7cea64c2392e92d3421347cde24cdf0454889ee99ebc093f787036e63fdebf`)

### claim-016: wave8-recorded-evidence-reuse

The Wave8 aggregate reused the recorded provider trace, container replay, LanceDB runtime and benchmark evidence without claiming live services.

Decision: `ACTUAL_HISTORICAL_RECEIPT_REQUIRED`.

Missing evidence: The four historical source receipts and their aggregate Wave8 contract with matching run/object identities.

Authority boundary: Because the claim is explicitly about recorded reuse, fresh outputs cannot prove it. Authorized read-only historical verification is required; no old path restoration is allowed.

Dependent nodeids:

- `tests.unit.test_wave8_search_vectorization_contract_unittest.Wave8SearchVectorizationContractTest::test_wave8_contract_reuses_recorded_evidence_without_claiming_live_services`

## Hard ceilings

Synthetic fixtures may test checker behavior but cannot close historical or live facts. History-only Git objects remain identity/provenance, not current authority. A fresh deterministic receipt is bounded to current repo-local behavior and cannot establish live provider, production, canary, cutover, or release authority.
