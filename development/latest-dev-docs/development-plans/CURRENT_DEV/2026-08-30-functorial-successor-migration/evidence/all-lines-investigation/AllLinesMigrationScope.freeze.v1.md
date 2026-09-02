# AllLinesMigrationScope.freeze.v1（全线迁移冻结范围草案）

状态：`DRAFT_FOR_SUPERVISOR_FREEZE`（不构成冻结或迁移授权）

- schema：`mrw.functorial_successor.all_lines_migration_scope.freeze.v1`
- version：`1.0.0`
- candidate：`null`
- authority：`authority_transfer=false, business_authority_migrated=false, cutover=false, external_delivery=false, live_provider=false, successor_claim_enabled_for_all_lines=false`

本草案只写入 `evidence/all-lines-investigation/`；donor checkout、生产代码、03/04/SUPERVISOR 均只读。未读取任何凭据值。逐字节 manifest 与逐条 disposition 的机器可读副本见同目录 `AllLinesMigrationScope.freeze.v1.json`。

## 1. 冻结范围

范围来自 donor 现场（`/Users/wangyiliang/market-research-workflow`，branch `codex/devdocs-supervisor-seed`，HEAD `35ca039c59d2efae8038a678995e8a0812032e43`，dirty change count 606）与迁移 worktree（`/Users/wangyiliang/.codex/manual-worktrees/mrw-functorial-successor-p0`，branch `codex/functorial-successor-p0`，HEAD `38acdee8862af0971ca063507b8355812894fbce`）。source registry 的字节哈希采用 `BackendDonorSurfaceInventory.v1.json` 中记录的工作树 git blob SHA-1；该文件未覆盖的 `LegacyVsMovementGap` donor path 已在 JSON `supplementary_gap_paths` 现场补 SHA-256/blob SHA-1（目录引用尚未逐文件展开）。

### 1.1 原业务条线清单（18 条）

| 业务线 id | line key | 类型 | 文件数 | 未跟踪数 | 现有 cell/movement 映射数 | disposition | owner |
|---|---|---|---|---|---|---|---|
| BL-business-lines-worker-readback | business_line_worker_readback_project_matrix_nightly | canonical_business_line_evidence_matrix | 8 | 8 | 3 | UNASSIGNED_BLOCKER | B-recheck / OpsPage owner; legacy matrix owner team |
| BL-ingest-submission-worker-readback | ingest | canonical_business_line_evidence_matrix | 10 | 1 | 20 | UNASSIGNED_BLOCKER | B-recheck; legacy worker lane owner |
| BL-search-discovery-index-worker-readback | search_discovery_index | canonical_business_line_evidence_matrix | 9 | 0 | 11 | UNASSIGNED_BLOCKER | B-recheck; legacy search/discovery worker lane owner |
| BL-source-library-resource-worker-readback | resource_source_library | canonical_business_line_evidence_matrix | 13 | 1 | 8 | UNASSIGNED_BLOCKER | B-recheck; source-library/resource lane owner |
| BL-projects-config-workflow | projects_config_workflow | canonical_business_line_evidence_matrix | 7 | 0 | 1 | UNASSIGNED_BLOCKER | B-recheck; project/config workflow owner |
| BL-dashboard-admin-governance | dashboard_admin_governance | canonical_business_line_evidence_matrix | 10 | 0 | 3 | UNASSIGNED_BLOCKER | B-recheck; dashboard/admin/governance owner |
| BL-writing-knowledge-graph-agent | writing_knowledge_graph_agent | canonical_business_line_evidence_matrix | 19 | 0 | 24 | REIMPLEMENTED_AS | B-recheck; writing/knowledge/graph/agent owner |
| BL-runtime-ops | runtime_ops | canonical_business_line_evidence_matrix | 5 | 2 | 1 | UNASSIGNED_BLOCKER | B-recheck; runtime ops owner |
| BL-llm-report-export-token-state | service_surface | service_surface | 14 | 11 | 5 | UNASSIGNED_BLOCKER | B-recheck; report-export/audit owner |
| BL-request-identity | service_surface | service_surface | 3 | 1 | 0 | UNASSIGNED_BLOCKER | B-recheck; authn identity owner |
| BL-task-readback-metadata | service_surface | service_surface | 4 | 2 | 6 | UNASSIGNED_BLOCKER | B-recheck; worker readback metadata owner |
| BL-single-source-guard | service_surface | service_surface | 3 | 1 | 8 | UNASSIGNED_BLOCKER | B-recheck; source-library boundary owner |
| BL-agent-batch-quality-promotion-readback | service_surface | service_surface | 4 | 0 | 5 | UNASSIGNED_BLOCKER | B-recheck; agent-batch owner |
| BL-dashboard-llm-report-detail-export-audit | service_surface | service_surface | 4 | 3 | 1 | UNASSIGNED_BLOCKER | B-recheck; dashboard/report owner |
| BL-typed-knowledge-writing-composition | service_surface | service_surface | 8 | 0 | 4 | REIMPLEMENTED_AS | B-recheck; typed-knowledge/writing owner |
| BL-llm-report-trend-quality-records | service_surface | service_surface | 4 | 2 | 1 | UNASSIGNED_BLOCKER | B-recheck; report trend owner |
| BL-runtime-health-matrix | service_surface | service_surface | 3 | 2 | 0 | UNASSIGNED_BLOCKER | B-recheck; runtime ops owner |
| BL-admin-crawler-cluechain-codexauth-keyword-stats | service_surface | service_surface | 8 | 0 | 1 | UNASSIGNED_BLOCKER | B-recheck; admin/ops owner |

逐条语义、gap、successor 目标与备注见第 2 节。

### 1.2 Donor source registry（130 项）

下表从 `BackendDonorSurfaceInventory.source_file_registry` 投影；`T`=donor HEAD tracked，`U`=donor HEAD 未跟踪（工作树现场字节）。

| 路径 | 字节哈希（working-tree git blob SHA-1） | tracked |
|---|---|---|
| `main/backend/app/api/__init__.py` | `2e9d56997fd79d62c49e6f2a766f568c241f3f69` | T |
| `main/backend/app/api/admin.py` | `59905edd01ab42bc29861e584619bb8d6f7eef6f` | T |
| `main/backend/app/api/agent_batch.py` | `1a516ca73c8b36c77c248851cb2c68acb0873fa2` | T |
| `main/backend/app/api/agent_chat.py` | `61e25d0e4a8caf8cd9acf1d332389adb03464c86` | T |
| `main/backend/app/api/agent_sessions.py` | `36fdd65f97f0cdcdb3c9f4a5bce290a0d888484f` | T |
| `main/backend/app/api/business_lines.py` | `2d030feb52c0a8a2e6c63dd821cc02a6ff96283f` | U |
| `main/backend/app/api/clue_chains.py` | `cf3e3fce4af21cbac5b064586328f6cb194c5333` | T |
| `main/backend/app/api/codex_auth.py` | `7ae76b65ff70709855e22657f20e875775d19480` | T |
| `main/backend/app/api/config.py` | `03fcbd49b49aaa16f89aa59e815939b5221e6b5a` | T |
| `main/backend/app/api/crawler.py` | `f5a766d6dee595713103ee5dce0427c5197ed209` | T |
| `main/backend/app/api/dashboard.py` | `51b03a13cec438039593bc1b74ad071db7563a36` | T |
| `main/backend/app/api/discovery.py` | `48aa0383b40679a89d62ef052477b9057a3c1be1` | T |
| `main/backend/app/api/governance.py` | `09f40989865f530ce126fc3d4cc5b4797a023cc3` | T |
| `main/backend/app/api/indexer.py` | `9e6e9754a37f4889ae69b057777ffe80eb6004f3` | T |
| `main/backend/app/api/ingest.py` | `7f2eaeb622e323b937c1867f6e6bea38aa0892c6` | T |
| `main/backend/app/api/keywords.py` | `c84e68cd69d376725f12822b2352abf2c6e5f8fc` | T |
| `main/backend/app/api/llm_config.py` | `9daf2423e058d84c35206598ab32f80717c641ed` | T |
| `main/backend/app/api/llm_report.py` | `54746f68e02dc1ebbaefe77936a2175cf4b1575d` | T |
| `main/backend/app/api/market.py` | `4095bb696742080e71868fc73ad3bb72f23cb48f` | T |
| `main/backend/app/api/policies.py` | `fa7133509b09c27c050ff981888a1297380cd05e` | T |
| `main/backend/app/api/process.py` | `efe10dca82dae8c2830a48feb256388e6ec02b52` | T |
| `main/backend/app/api/products.py` | `c19bbf72b7f87a1fb080e1518830eb9bc33ff93c` | T |
| `main/backend/app/api/project_customization.py` | `d1e83f5ee7d50de78afb4ec986250582cb3eaeec` | T |
| `main/backend/app/api/projects.py` | `f45f604fbd9ac83ffd3420c7d54fbeaab01b5a5e` | T |
| `main/backend/app/api/reports.py` | `f570a5ca848ec1649341f38ac2ba6256fd372c32` | T |
| `main/backend/app/api/resource_pool.py` | `95976d19cf678e87f5d984016552631039f81886` | T |
| `main/backend/app/api/search.py` | `dd87f6c54e7ff9d72b680569a790e6c2acf9c15d` | T |
| `main/backend/app/api/skills.py` | `b7f89bfd78ed97bb89e90b46671bcdfd6c43af24` | T |
| `main/backend/app/api/source_library.py` | `9b77a5505978d852f331a934252689d25493fc82` | T |
| `main/backend/app/api/stats.py` | `9434a4aa89d37ec164f865feafbb2bae38fd4a29` | T |
| `main/backend/app/api/topics.py` | `f68d33a5f631548751b905035501eff0a3aeddc4` | T |
| `main/backend/app/api/typed_knowledge.py` | `86f6b73f41f50f91fc17b742e02c1762e11783a4` | T |
| `main/backend/app/api/workflow_graph.py` | `64f7ee81ab6c64c699e5e77981be6f0949736d20` | T |
| `main/backend/app/api/writing.py` | `a274a516f975de0d8f0e86a219b2bdd4a022c40d` | T |
| `main/backend/app/main.py` | `87d92c465b7cb411bd8e6e352e8b6dcb1447c595` | T |
| `main/backend/app/models/base.py` | `3565f629a704125302ad315df68133406adc3f00` | T |
| `main/backend/app/models/entities.py` | `41c0670a58cf44ff61b89481490e16fdb41937cb` | T |
| `main/backend/app/models/ingest_registry.py` | `3d0161ec5890c22b0156f651c4fea7abc79c7cb0` | U |
| `main/backend/app/models/llm_report_export_audit.py` | `5dff1ed285edc94ca8f7ff8773e020f063c9f98d` | U |
| `main/backend/app/models/llm_report_export_token_state.py` | `73cab5deee62e2c491c60237ba1f7a97b50921f3` | U |
| `main/backend/app/models/llm_report_trends.py` | `f1e0e3b0d214396da7813361fe5e41963b3fdc93` | U |
| `main/backend/app/models/long_cycle_entities.py` | `273889e47c5beeb0e34441690448425b930316da` | T |
| `main/backend/app/models/typed_knowledge_entities.py` | `b3e5de4900ee68820cb334a3d0d6707c258fa7d9` | T |
| `main/backend/app/models/writing_entities.py` | `e80d53a8e149f99e54eac5054e70964469ac70fb` | T |
| `main/backend/app/services/agent_batch/agent_loop.py` | `63fce87994532688fc7f9a1a97cbf580c71cc644` | T |
| `main/backend/app/services/agent_batch/approval_binding.py` | `67ec76f4cd1294efc1292893150d5441f55d5776` | T |
| `main/backend/app/services/agent_batch/executor_health.py` | `784725ee3ad0b68b6926444835b39e3aa9d8b2c9` | T |
| `main/backend/app/services/agent_batch/planner.py` | `cfc9e3316792935960a7b14c2ae23cd1fe228563` | T |
| `main/backend/app/services/agent_batch/search_quality_replay.py` | `d4e36c50e79a920c5553340bb3efa3af0720da75` | T |
| `main/backend/app/services/agent_batch/task_contract.py` | `8ab4204a0fa5b8f99b5ce2ceabc0d20feb836444` | T |
| `main/backend/app/services/agent_core/core.py` | `9a52404d6f28fa341106bd75c700494e16b3858f` | T |
| `main/backend/app/services/agent_runtime/coordinator.py` | `f71a7fdc2609961b82dc69f1f15c1378cbd0a825` | T |
| `main/backend/app/services/agent_sessions/service.py` | `996bc5ea7f6bfa9a7b4f44b64747921f0c9989f8` | T |
| `main/backend/app/services/agent_sessions/store.py` | `7817e74ac38e42e23089b2b61778313ba1d8b784` | T |
| `main/backend/app/services/aggregator/sync.py` | `8787142f6b01b7bcbc3021004469794c3ee70558` | T |
| `main/backend/app/services/collect_runtime/adapters/search_market.py` | `c6a90203b761b0a94d6b9c42d445dcc8279a4954` | T |
| `main/backend/app/services/collect_runtime/adapters/source_library.py` | `f9f277652a15971836cb78a4275aa22b4f5ecf5a` | T |
| `main/backend/app/services/collect_runtime/contracts.py` | `47b4b410dfca480ed2e074f8eeaa7658132f668f` | T |
| `main/backend/app/services/collect_runtime/runtime.py` | `8c77b7699c6c8d21d7a0704150d3a1f56a784e50` | T |
| `main/backend/app/services/governance/retention.py` | `bab62fc73aeb47c505e5df3b21ce9210d80d74ea` | T |
| `main/backend/app/services/graph/builder.py` | `aeaf4869021a1b0625e15789ef95055b58d10ca2` | T |
| `main/backend/app/services/graph/exporter.py` | `e525d47f0428832ac301a7fe4ad1dd5fa9b09eb2` | T |
| `main/backend/app/services/graph/projection.py` | `4c7ffd260a95e0b996d43a4489929c52333539cb` | T |
| `main/backend/app/services/indexer/application.py` | `54398fd437c2395827951d13dfcde7db577c649c` | T |
| `main/backend/app/services/ingest/frontdoor_contract.py` | `78f1594721fda2de9b0681f69a55106983ddb939` | T |
| `main/backend/app/services/ingest/frontdoor_orchestrator.py` | `77afd39e084641724e32301d2fa9e361311446db` | T |
| `main/backend/app/services/ingest/long_cycle_live_runtime.py` | `8562ff23228a205885d4159af69d90659d45d922` | T |
| `main/backend/app/services/ingest/meaningful_gate.py` | `d410dc55c7a61170aebd0d3c713cb790e64fad77` | T |
| `main/backend/app/services/ingest/retry_policy.py` | `29061f9313947293144cf898451eabf78f672359` | T |
| `main/backend/app/services/ingest/terminal_writer.py` | `f32c9139943ee541f95f236e2083bf6315f77509` | T |
| `main/backend/app/services/llm_report_export.py` | `8e0e198b68d6800e8db31c3de6c3d3a800858191` | U |
| `main/backend/app/services/llm_report_export_audit.py` | `4799746e4f9a4b7ea3a032dc24eec5376ac68640` | U |
| `main/backend/app/services/llm_report_export_token_state.py` | `c311dc50acc8923d1e42b3109d174bf81005ff13` | U |
| `main/backend/app/services/llm_report_generator.py` | `540448baa9064432eef74808ee0eb021c8ac5d8c` | T |
| `main/backend/app/services/llm_report_source_enrichment.py` | `d4f664becf873b0fd00e898a59a8cc3a2d378a0a` | T |
| `main/backend/app/services/llm_report_trends.py` | `79deed264cdcb3f92e349efe3689a0631cc39db9` | U |
| `main/backend/app/services/projects/context.py` | `dd6ad1ca39f783cc81f737b82f8836870a11b65c` | T |
| `main/backend/app/services/projects/workflow.py` | `9b6ce960bba199ac2f3dc529228a2cde9ae73971` | T |
| `main/backend/app/services/report.py` | `8e5cfd80ce8344c373a8ff2f3a12025860842ff1` | T |
| `main/backend/app/services/request_identity.py` | `dfe68e9ea44637a56ffc560fd455e2cef0628318` | U |
| `main/backend/app/services/resource_pool/resolver.py` | `05f04017860a911865250a92219dbfe7450e6c2f` | T |
| `main/backend/app/services/resource_pool/site_entries.py` | `09021cd0873f414cc3c81c3da76b7f5960197380` | T |
| `main/backend/app/services/resource_pool/unified_search.py` | `01f8096a6c59f66a9802f17ce799efe8f65e70e4` | T |
| `main/backend/app/services/search/history.py` | `ce692dd0023719250c260bbb7ca1ee6324004d2a` | T |
| `main/backend/app/services/search/retrieval_runs.py` | `9a7594211d13fb484a426197a8c42f7a58f4440d` | T |
| `main/backend/app/services/source_library/external_project_registration.py` | `10c68636ff8d13c41d3d668e47648b8c67c57045` | T |
| `main/backend/app/services/source_library/item_plan.py` | `c67a17e67511f38280b9671f2da9399e02d8d1b9` | T |
| `main/backend/app/services/source_library/item_resolver.py` | `21264723f7bd6d1c32a4b26f36fda406a09c7738` | T |
| `main/backend/app/services/source_library/relevance_review.py` | `f7b5452c56570b91b0f3d1d72f1a44719bcabf20` | T |
| `main/backend/app/services/source_library/resolver.py` | `522891818c17f8f7e99ddaf43b8ab9bcc9bd4025` | T |
| `main/backend/app/services/source_library/runner.py` | `e39234f9c71382a143400ed1c88c08e0f7611895` | T |
| `main/backend/app/services/source_library/single_source_guard.py` | `513330bc053f4234457aa1ec066efa913ed522b1` | U |
| `main/backend/app/services/source_library/sync.py` | `ad4d98e17148a6618a402b231799ad14c7f2cbf6` | T |
| `main/backend/app/services/task_readback_metadata.py` | `701eec5a0739fec7349c963d985749dfab0602e1` | U |
| `main/backend/app/services/tasks.py` | `c432f1058da53b913225cbe6b36dae97b2910be6` | T |
| `main/backend/app/services/typed_knowledge/baseline.py` | `ae8d50ef8490ad6ed9b12731fd20192dc64b4c62` | T |
| `main/backend/app/services/typed_knowledge/contracts.py` | `d079128873cd9220338c6dbaacc991bcc5864b0d` | T |
| `main/backend/app/services/typed_knowledge/persistence_boundary.py` | `3f071ab778e4b3ecacf2fc6b7209126725b92d66` | T |
| `main/backend/app/services/workflow_graph/compiler.py` | `65a9f73fd8a22037f98f2fbab83fbc90c6f57e00` | T |
| `main/backend/app/services/workflow_graph/contracts.py` | `36d97d0726300639998eab3deaf9ea7319944647` | T |
| `main/backend/app/services/workflow_graph/curated_service.py` | `1398fdf5bd3bcb6526d4cd5115511d5b9b347ebf` | T |
| `main/backend/app/services/workflow_graph/runtime.py` | `3a900dab2264c6b0474172ce3c718c10a5a9f566` | T |
| `main/backend/app/services/workflow_graph/store.py` | `111fe4245728111f1b9daf7020017fe27f14d21d` | T |
| `main/backend/app/services/workflow_graph/templates.py` | `53d9aa25340535bf0d7db2d43de31a0dbc4516c7` | T |
| `main/backend/app/services/writing/document_service.py` | `388de2a092faf09bd373db9a31d75991b9101040` | T |
| `main/backend/app/services/writing/llm_action_service.py` | `cbf60522dacc7af2d475c39db238c52fbcd8263e` | T |
| `main/backend/app/services/writing/template_service.py` | `24d9e8f869a88fb78ff6146b067430ad41244967` | T |
| `main/backend/migrations/versions/20260524_000001_add_ingest_submission_registry.py` | `a011e93d2d3f1a5e6c357cde2064ea09d7f82120` | U |
| `main/backend/migrations/versions/20260524_000002_add_llm_report_quality_trends.py` | `875dd0caf723735b1d89896ea27d867490de3a6f` | U |
| `main/backend/migrations/versions/20260524_000003_add_llm_report_export_audit_events.py` | `03a9996a8dc56169a6490115ea139bfd72ccd6ab` | U |
| `main/backend/migrations/versions/20260524_000004_add_llm_report_export_token_state.py` | `b072d16caa78a93ec21c51b99da11d5d084e652e` | U |
| `main/frontend-modern/tests/e2e/business-line-browser-actions.spec.ts` | `b63af26ebadb552fedc74b60825e7d9fc4b64cab` | U |
| `main/frontend-modern/tests/e2e/real-backend-business-lines.spec.ts` | `d760aa67d9ba0592e4ec96f886ae3ca451df29e0` | U |
| `scripts/build_business_line_async_readiness_artifact.py` | `87a45149ff10ff30eea516a9f9a594f83899f219` | U |
| `scripts/build_business_line_async_task_readback_artifact.py` | `039092613b05a3f43dc65e8444cf89d252974a75` | U |
| `scripts/build_business_line_real_backend_browser_artifact.py` | `78d5ae83d9c403f7c10f94b54e44e96133245989` | U |
| `scripts/build_business_line_task_readback_manifest_from_runtime.py` | `fe72e86d2080f3efab15d7741e9c6f31ab874861` | U |
| `scripts/check_business_line_async_readiness_artifact.py` | `c7f00c9b99f72b9e4fc0ad6fd388349f6773c788` | U |
| `scripts/check_business_line_async_task_readback_artifact.py` | `0d5b360720cc7d2d73c06b5a630a7f155477ed90` | U |
| `scripts/check_business_line_batch_coverage.py` | `c204b7e928cdc8c367ad4deb83290a15b38c576b` | U |
| `scripts/check_business_line_real_backend_browser_artifact.py` | `6a82194f386eec090b34f01f273cb7cbddc62ffc` | U |
| `scripts/check_business_line_task_readback_manifest.py` | `60b604c9795f5d8b9474f91ea1617f283f4d6b72` | U |
| `scripts/check_business_line_trace_baseline_artifact.py` | `0359a63d04351d7c3e841f6b261368083d1853d4` | U |
| `scripts/run_business_line_async_task_readback_live_samples.py` | `bdd8c0f6bfbb64ce74280f4ee01d90872da06984` | U |
| `scripts/run_business_line_trace_baseline_live.py` | `85f62ad681de1f99c47d652d3f3dcbbb0ea6ba30` | U |
| `scripts/run_business_line_user_flow_smoke.py` | `9041eba60cd4e82fb2ac996b3f4071cfcb2dfded` | U |
| `scripts/run_business_line_worker_readback_evidence_chain.py` | `7388ed956c5ce5b4eb42ef46ad4342c1468a2094` | U |
| `scripts/run_business_line_worker_readback_project_matrix.py` | `cb77107058565b0e4ceed62e8f5f5488bee985ff` | U |
| `scripts/run_business_line_worker_readback_smoke_triggers.py` | `8cc389595f084099f49656d8a4cf7d64788e8f97` | U |
| `scripts/runtime_health_matrix.py` | `7517d6d45771830a19cfb0684d74e26d5ef9eb8c` | U |

### 1.3 Donor HEAD 未跟踪文件（35 项，冻结重点）

这些文件存在于 donor 工作树但不在 donor HEAD 提交中；clean checkout 与当前迁移 worktree 均不含它们。

- `main/backend/app/api/business_lines.py` `2d030feb52c0a8a2e6c63dd821cc02a6ff96283f`
- `main/backend/app/models/ingest_registry.py` `3d0161ec5890c22b0156f651c4fea7abc79c7cb0`
- `main/backend/app/models/llm_report_export_audit.py` `5dff1ed285edc94ca8f7ff8773e020f063c9f98d`
- `main/backend/app/models/llm_report_export_token_state.py` `73cab5deee62e2c491c60237ba1f7a97b50921f3`
- `main/backend/app/models/llm_report_trends.py` `f1e0e3b0d214396da7813361fe5e41963b3fdc93`
- `main/backend/app/services/llm_report_export.py` `8e0e198b68d6800e8db31c3de6c3d3a800858191`
- `main/backend/app/services/llm_report_export_audit.py` `4799746e4f9a4b7ea3a032dc24eec5376ac68640`
- `main/backend/app/services/llm_report_export_token_state.py` `c311dc50acc8923d1e42b3109d174bf81005ff13`
- `main/backend/app/services/llm_report_trends.py` `79deed264cdcb3f92e349efe3689a0631cc39db9`
- `main/backend/app/services/request_identity.py` `dfe68e9ea44637a56ffc560fd455e2cef0628318`
- `main/backend/app/services/source_library/single_source_guard.py` `513330bc053f4234457aa1ec066efa913ed522b1`
- `main/backend/app/services/task_readback_metadata.py` `701eec5a0739fec7349c963d985749dfab0602e1`
- `main/backend/migrations/versions/20260524_000001_add_ingest_submission_registry.py` `a011e93d2d3f1a5e6c357cde2064ea09d7f82120`
- `main/backend/migrations/versions/20260524_000002_add_llm_report_quality_trends.py` `875dd0caf723735b1d89896ea27d867490de3a6f`
- `main/backend/migrations/versions/20260524_000003_add_llm_report_export_audit_events.py` `03a9996a8dc56169a6490115ea139bfd72ccd6ab`
- `main/backend/migrations/versions/20260524_000004_add_llm_report_export_token_state.py` `b072d16caa78a93ec21c51b99da11d5d084e652e`
- `main/frontend-modern/tests/e2e/business-line-browser-actions.spec.ts` `b63af26ebadb552fedc74b60825e7d9fc4b64cab`
- `main/frontend-modern/tests/e2e/real-backend-business-lines.spec.ts` `d760aa67d9ba0592e4ec96f886ae3ca451df29e0`
- `scripts/build_business_line_async_readiness_artifact.py` `87a45149ff10ff30eea516a9f9a594f83899f219`
- `scripts/build_business_line_async_task_readback_artifact.py` `039092613b05a3f43dc65e8444cf89d252974a75`
- `scripts/build_business_line_real_backend_browser_artifact.py` `78d5ae83d9c403f7c10f94b54e44e96133245989`
- `scripts/build_business_line_task_readback_manifest_from_runtime.py` `fe72e86d2080f3efab15d7741e9c6f31ab874861`
- `scripts/check_business_line_async_readiness_artifact.py` `c7f00c9b99f72b9e4fc0ad6fd388349f6773c788`
- `scripts/check_business_line_async_task_readback_artifact.py` `0d5b360720cc7d2d73c06b5a630a7f155477ed90`
- `scripts/check_business_line_batch_coverage.py` `c204b7e928cdc8c367ad4deb83290a15b38c576b`
- `scripts/check_business_line_real_backend_browser_artifact.py` `6a82194f386eec090b34f01f273cb7cbddc62ffc`
- `scripts/check_business_line_task_readback_manifest.py` `60b604c9795f5d8b9474f91ea1617f283f4d6b72`
- `scripts/check_business_line_trace_baseline_artifact.py` `0359a63d04351d7c3e841f6b261368083d1853d4`
- `scripts/run_business_line_async_task_readback_live_samples.py` `bdd8c0f6bfbb64ce74280f4ee01d90872da06984`
- `scripts/run_business_line_trace_baseline_live.py` `85f62ad681de1f99c47d652d3f3dcbbb0ea6ba30`
- `scripts/run_business_line_user_flow_smoke.py` `9041eba60cd4e82fb2ac996b3f4071cfcb2dfded`
- `scripts/run_business_line_worker_readback_evidence_chain.py` `7388ed956c5ce5b4eb42ef46ad4342c1468a2094`
- `scripts/run_business_line_worker_readback_project_matrix.py` `cb77107058565b0e4ceed62e8f5f5488bee985ff`
- `scripts/run_business_line_worker_readback_smoke_triggers.py` `8cc389595f084099f49656d8a4cf7d64788e8f97`
- `scripts/runtime_health_matrix.py` `7517d6d45771830a19cfb0684d74e26d5ef9eb8c`

### 1.4 LegacyVsMovementGap 补充 donor path（30 项，不在 Backend registry）

其中文件级路径已在 donor 现场补 SHA-256 与 blob SHA-1（见 JSON `supplementary_gap_paths`）；目录级引用尚未逐文件展开，留给 WP-1。

- `main/backend/app/celery_app.py` sha256=`5f28badfb562179370c4042e2a9a7ef5a8f84933c961755aa86d6c6b8be1b380` blob=`f551f59cae36bca41596b3b42ccf69391f185e20`
- `main/backend/app/contracts/responses.py` sha256=`c8dd8dfde25c3be60322ed00ed070aac1f9c9d53a40f97d71fcb517a86f461a2` blob=`5318d5c1d86cb7961bdc93ed76f4338568133570`
- `main/backend/app/services/agent_core/contracts.py` sha256=`769c14a267306d4488108f3efa4a6704d1f2f9ebab84de8f6a4440ced8ebde41` blob=`22bcce677819fbcd732fb5249add4f3093d2d278`
- `main/backend/app/services/agent_core/provider_trace.py` sha256=`d4cdd38d3d568c885946affe92f20826c5244d949b36484a4d27ce300c938b39` blob=`e33c4f269823f192c92234058a8e96ed7bdeeb34`
- `main/backend/app/services/agent_runtime/interactive_agent.py` sha256=`cf6505a2ebf0d1bb19dc22cba0e5b7ed34e2d04db5142b1276ee04949e1072a6` blob=`a8ef5ceac7fd4a5d7f47b39a1a53d2757e873591`
- `main/backend/app/services/agent_runtime/run_loop.py` sha256=`9c11c49cf985d9e5d5563e6111a6084def841875e584c80f7ffd5c7a5ff934c5` blob=`6f43e2caf2058edcbcada15667ec865be6ade683`
- `main/backend/app/services/clue_chains` kind=`directory_reference`
- `main/backend/app/services/collect_runtime/adapters` kind=`directory_reference`
- `main/backend/app/services/crawlers` kind=`directory_reference`
- `main/backend/app/services/document_views/writing_card_view.py` sha256=`6366af1de0e0108174d7d208c225f8290d31c39a8cb667b97ada4f470068aada` blob=`647b4b10709cf0095a2ecd7da365757beae3fd5f`
- `main/backend/app/services/extraction` kind=`directory_reference`
- `main/backend/app/services/graph` kind=`directory_reference`
- `main/backend/app/services/graph/backfill_graph_nodes.py` sha256=`9bb609882ed2dd55fa8e5815cf6b29ceca532bd7570af9ff5e131935b4980f6d` blob=`c9e6cd46e5609671aad5b19e7467a2f7c9dd0aa0`
- `main/backend/app/services/graph/models.py` sha256=`d4408a15bf981020a8652d500bb989a00bf3d34f73dac884a2facb1332816a8f` blob=`893aff58ff9e8d67c480684d1bf331b702015161`
- `main/backend/app/services/indexer` kind=`directory_reference`
- `main/backend/app/services/indexer/policy.py` sha256=`ca58531efe5f4d4074d30eaeb3d679c26b38b36e11c8019039b27608b9dec011` blob=`2d3abe9d3eb9c5011101d6bd29db37379dfa8e7d`
- `main/backend/app/services/ingest/digestion_scaffold.py` sha256=`99af7ffac3fa39f461fc2bdbe50b937e6298fcce2c013b336b106780671d2c3d` blob=`ad3fef4b7b8efea32b6602b380891f7fbdf99e50`
- `main/backend/app/services/ingest/frontdoor_ingress.py` sha256=`ccebc219cf0dca5bb22fddba6752822a9853e9eb91430936e669c0a234f08d15` blob=`03f23acf23af5ca13cbef8bd12cceffef01c0843`
- `main/backend/app/services/ingest/postprocess_frontdoor.py` sha256=`f63de8161d9f56289ed8c93e7eb3a5536e8fe391e311dad4a7853cfaf4c2b830` blob=`1eaa7990f4a51870fb8f8d7842c75047c9a7568c`
- `main/backend/app/services/llm/platformization.py` sha256=`e3577c53191d79e02256fccc586a63d251e610268236cf971b2492b956861b4a` blob=`708e0a0a1c159a03e0fb790df2e304d6a6575f5f`
- `main/backend/app/services/llm/provider.py` sha256=`07074030655cf55520ed222f1dcb7b92b83d22b3322b65c9061c268f16edd0f0` blob=`35d0ec590df271a447a8f279960d5c3322d4f946`
- `main/backend/app/services/source_library/terminal_output.py` sha256=`035f6a4c085f57df944efd39850cd884311ea688dd25eec6fdc7336902ef36d5` blob=`81fb5820281bbdc9bc0fa0abecf7efdab59fcc7e`
- `main/backend/app/services/streamplus` kind=`directory_reference`
- `main/backend/app/services/writing` kind=`directory_reference`
- `main/backend/app/services/writing/citation_service.py` sha256=`808d6024e18cae5dc74ade6b8ceb5169b80579ad3473debce01d42e730be6cc3` blob=`074b87eada446d89e83c66a1ccd19dbf35f21a7f`
- `main/frontend-modern/src/lib/api/client.ts` sha256=`d65ad6875b3334e6149c28daa201188b341c4d123cc8ffa4f1d397794bdfe6f7` blob=`ed5385d20d9539eff45409ec0e74464220859ff8`
- `main/frontend-modern/src/lib/types.ts` sha256=`7ca907bb6083c2dbac90d27b3c2638b923f87f63df9a01149edafcb827cc1c47` blob=`e176ee7d3e9647321ee60bafd10836a07392ed74`
- `main/frontend-modern/src/pages/DashboardPage.tsx` sha256=`17e6af0e06abfe62aad82b60dbdb227c58cf58769d5f9b20e75e9cd76643473c` blob=`17873fc2de0cd5f4bbe0477188eb7951bc7022d8`
- `main/frontend-modern/src/pages/GraphPage.tsx` sha256=`6cc0cb4a3974e472ede0fde7bc605c22630f1e2a8415ac538ac7732e2e7ad014` blob=`94b6890f402a86527d46e6b2d251aeeb18b05f51`
- `main/frontend-modern/src/pages/dashboard/DashboardSearchRetrievalRunPanel.tsx` sha256=`4a672312833df2dd2fc0ae230d4a0579673c9055d4ac47209f26f522d85d881d` blob=`8753624fa2ba3ad4973c8809de37bfbea9841ab4`

## 2. 逐条 disposition

disposition 取值：`PRESERVED_AS` / `MOVED_TO` / `REIMPLEMENTED_AS` / `DECLARED_LOSS` / `EXPLICITLY_REJECTED` / `UNASSIGNED_BLOCKER`。本草案只有 2 条已具备可裁决 successor 映射，16 条仍为 `UNASSIGNED_BLOCKER`；组件级另有 14 条 declared-loss/rejected 记录与 15 个 unmapped gap（不改变上述行级计数）。

### BL-business-lines-worker-readback

- line key：`business_line_worker_readback_project_matrix_nightly`；kind：`canonical_business_line_evidence_matrix`
- owner：B-recheck / OpsPage owner; legacy matrix owner team
- donor evidence：8 个源文件；未跟踪 8 个；main/backend/app/api/business_lines.py; main/backend/app/services/task_readback_metadata.py; scripts/run_business_line_worker_readback_project_matrix.py; scripts/run_business_line_worker_readback_evidence_chain.py; scripts/run_business_line_async_task_readback_live_samples.py; scripts/build_business_line_async_readiness_artifact.py; scripts/runtime_health_matrix.py; main/frontend-modern/tests/e2e/real-backend-business-lines.spec.ts
- 现有 cell/movement 映射：cells `C9.1, C9.3`；movements `C9-M001, C9-M004, C9-M005`
- gaps：`GAP-business-lines-evidence-matrix`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：UNKNOWN; candidate C9.1/C9.3 structural envelope plus a new evidence-matrix/readback meta capability owner
- 备注：Meta business-line evidence matrix is not owned by any C1-C9 movement; key donor files are untracked at donor HEAD.

### BL-ingest-submission-worker-readback

- line key：`ingest`；kind：`canonical_business_line_evidence_matrix`
- owner：B-recheck; legacy worker lane owner
- donor evidence：10 个源文件；未跟踪 1 个；main/backend/app/models/ingest_registry.py
- 现有 cell/movement 映射：cells `C7.1, C7.2, C7.3, C7.4`；movements `C7-MOV-001, C7-MOV-002, C7-MOV-003, C7-MOV-010, C7-MOV-011, C7-MOV-020, C7-MOV-021, C7-MOV-030, C7-MOV-031, C7-MOV-040, C7-MOV-041, C7-MOV-050, C7-MOV-051, C7-MOV-060, C7-MOV-061, C7-MOV-070, C7-MOV-071, C7-MOV-072, C7-MOV-073, C7-MOV-074`
- gaps：`GAP-ingest-submission-registry`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：backend-core/C7 and document.canonical/C7.2 candidates
- 备注：C7.1-C7.4 mapped and external C7 movement matrix exists, but untracked ingest_registry model+migration are not a locator/movement source and target worktree has no copy.

### BL-search-discovery-index-worker-readback

- line key：`search_discovery_index`；kind：`canonical_business_line_evidence_matrix`
- owner：B-recheck; legacy search/discovery worker lane owner
- donor evidence：9 个源文件；未跟踪 0 个
- 现有 cell/movement 映射：cells `C2.4, C3.1, C3.2`；movements `C2-M001, C2-M002, C2-M003, C2-M004, C2-M005, C2-M006, C2-M007, C2-M008, C3-M001, C3-M002, C3-M003`
- gaps：`GAP-untracked-frontend-dashboard-panel`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：collect-runtime/C3 and frontend-platform/C9.2 candidates
- 备注：C2.4 partial, C3.1-C3.2 mapped; untracked DashboardSearchRetrievalRunPanel has no P1 locator or successor cell.

### BL-source-library-resource-worker-readback

- line key：`resource_source_library`；kind：`canonical_business_line_evidence_matrix`
- owner：B-recheck; source-library/resource lane owner
- donor evidence：13 个源文件；未跟踪 1 个；main/backend/app/services/source_library/single_source_guard.py
- 现有 cell/movement 映射：cells `C2.1, C2.2, C2.3, C2.4`；movements `C2-M001, C2-M002, C2-M003, C2-M004, C2-M005, C2-M006, C2-M007, C2-M008`
- gaps：`GAP-single-source-guard`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：backend-core/C2, C2.3 execution-boundary candidate
- 备注：C2.1-C2.4 mapped, but single_source_guard.py is untracked, absent from migration worktree, and not named in P1 locators.

### BL-projects-config-workflow

- line key：`projects_config_workflow`；kind：`canonical_business_line_evidence_matrix`
- owner：B-recheck; project/config workflow owner
- donor evidence：7 个源文件；未跟踪 0 个
- 现有 cell/movement 映射：cells `UNKNOWN`；movements `C9-M001`
- gaps：`GAP-projects-config-workflow`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：UNKNOWN; no dedicated C1-C9 locator cell
- 备注：Project/config/workflow semantics have only structural C9.1 alignment; no movement owns the line.

### BL-dashboard-admin-governance

- line key：`dashboard_admin_governance`；kind：`canonical_business_line_evidence_matrix`
- owner：B-recheck; dashboard/admin/governance owner
- donor evidence：10 个源文件；未跟踪 0 个
- 现有 cell/movement 映射：cells `UNKNOWN`；movements `C9-M001, C9-M004, C9-M005`
- gaps：`GAP-dashboard-admin-governance, GAP-dashboard-report-closure`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：UNKNOWN; C9.1/C9.3 structural only
- 备注：Dashboard/admin/governance and report closure semantics have no dedicated successor cell.

### BL-writing-knowledge-graph-agent

- line key：`writing_knowledge_graph_agent`；kind：`canonical_business_line_evidence_matrix`
- owner：B-recheck; writing/knowledge/graph/agent owner
- donor evidence：19 个源文件；未跟踪 0 个
- 现有 cell/movement 映射：cells `C1.1, C1.2, C1.3, C4.1, C4.2, C4.3, C5.1, C5.2, C5.3, C5.4, C6.1, C6.2, C6.3, C8.1, C8.2, C8.3, C8.4`；movements `C1-M001, C1-M002, C1-M003, C1-M004, C4-M001, C4-M002, C4-M003, C4-M004, C4-M005, C5-M001, C5-M002, C5-M003, C5-M004, C5-M005, C5-M006, C6-M001, C6-M002, C6-M003, C6-M004, C8-M001, C8-M002, C8-M003, C8-M004, C8-M005`
- gaps：`无`
- disposition：**REIMPLEMENTED_AS**
- successor 目标：backend-core/C1/C4/C5/C6, knowledge-core/C8, writing-core/C8, report-admission/C8, graph-projection/C8
- 备注：Mapped to C1/C4/C5/C6/C8.1-C8.4 movement family; declared-loss/rejected component rows remain binding obligations. Local-only, no authority.

### BL-runtime-ops

- line key：`runtime_ops`；kind：`canonical_business_line_evidence_matrix`
- owner：B-recheck; runtime ops owner
- donor evidence：5 个源文件；未跟踪 2 个；scripts/runtime_health_matrix.py; scripts/check_business_line_trace_baseline_artifact.py
- 现有 cell/movement 映射：cells `UNKNOWN`；movements `C9-M001`
- gaps：`GAP-runtime-ops`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：UNKNOWN; no dedicated locator cell
- 备注：Runtime ops not represented in C1-C9 locator; C9.1 health/deep exemption is envelope-only.

### BL-llm-report-export-token-state

- line key：`service_surface`；kind：`service_surface`
- owner：B-recheck; report-export/audit owner
- donor evidence：14 个源文件；未跟踪 11 个；main/backend/app/services/llm_report_export.py; main/backend/app/services/llm_report_export_token_state.py; main/backend/app/services/llm_report_export_audit.py; main/backend/app/services/llm_report_trends.py; main/backend/app/models/llm_report_export_token_state.py; main/backend/app/models/llm_report_export_audit.py; main/backend/app/models/llm_report_trends.py; main/backend/migrations/versions/20260524_000002_add_llm_report_quality_trends.py; main/backend/migrations/versions/20260524_000003_add_llm_report_export_audit_events.py; main/backend/migrations/versions/20260524_000004_add_llm_report_export_token_state.py; main/backend/app/services/request_identity.py
- 现有 cell/movement 映射：cells `C6.2, C8.3`；movements `C6-M001, C6-M002, C6-M003, C6-M004, C8-M003`
- gaps：`GAP-llm-report-export, GAP-llm-report-token-state`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：report-admission/C8 candidate
- 备注：C8-M003 does not bind export/token implementation; untracked llm_report_export family absent from target worktree.

### BL-request-identity

- line key：`service_surface`；kind：`service_surface`
- owner：B-recheck; authn identity owner
- donor evidence：3 个源文件；未跟踪 1 个；main/backend/app/services/request_identity.py
- 现有 cell/movement 映射：cells `UNKNOWN`；movements `无`
- gaps：`GAP-request-identity`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：UNKNOWN; C9.1 caller-actor scope is nearest structural match
- 备注：Request identity has no unified successor cell; C9-M001 scope is not a binding.

### BL-task-readback-metadata

- line key：`service_surface`；kind：`service_surface`
- owner：B-recheck; worker readback metadata owner
- donor evidence：4 个源文件；未跟踪 2 个；main/backend/app/services/task_readback_metadata.py; main/backend/app/api/business_lines.py
- 现有 cell/movement 映射：cells `C5.4`；movements `C5-M001, C5-M002, C5-M003, C5-M004, C5-M005, C5-M006`
- gaps：`GAP-task-readback-metadata-line-events`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：runtime-observation/C5 candidate
- 备注：Dirty source file is intentionally excluded (adopted=false), but line-event semantics have no successor movement; exclusion does not realize the capability.

### BL-single-source-guard

- line key：`service_surface`；kind：`service_surface`
- owner：B-recheck; source-library boundary owner
- donor evidence：3 个源文件；未跟踪 1 个；main/backend/app/services/source_library/single_source_guard.py
- 现有 cell/movement 映射：cells `C2.3`；movements `C2-M001, C2-M002, C2-M003, C2-M004, C2-M005, C2-M006, C2-M007, C2-M008`
- gaps：`GAP-single-source-guard`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：backend-core/C2, C2.3 candidate
- 备注：Guard validation/blocking authority has no explicit P1 locator/movement source path.

### BL-agent-batch-quality-promotion-readback

- line key：`service_surface`；kind：`service_surface`
- owner：B-recheck; agent-batch owner
- donor evidence：4 个源文件；未跟踪 0 个
- 现有 cell/movement 映射：cells `C4.1/C4.2`；movements `C4-M001, C4-M002, C4-M003, C4-M004, C4-M005`
- gaps：`无`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：UNKNOWN; C4.1/C4.2 structural plus provider-independent quality-gate owner
- 备注：No LegacyVsMovementGap row names search_quality_replay.py/executor_health.py; C4 movement rows cover agent_loop/planner/task_contract/API only. Evidence omission to be resolved by supervisor. Promotion readback files are not bound by C4 movement rows; freeze must decide whether C4.3 directory scope covers them or an additional gap/owner is required.

### BL-dashboard-llm-report-detail-export-audit

- line key：`service_surface`；kind：`service_surface`
- owner：B-recheck; dashboard/report owner
- donor evidence：4 个源文件；未跟踪 3 个；main/backend/app/services/llm_report_export_audit.py; main/backend/app/services/llm_report_export_token_state.py; main/backend/app/services/llm_report_trends.py
- 现有 cell/movement 映射：cells `C8.3`；movements `C8-M003`
- gaps：`GAP-llm-report-export-audit`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：UNKNOWN; report-admission/C8 and runtime observability adjudication required
- 备注：Durable export-audit events and dashboard trace readback have no successor audit movement/cell.

### BL-typed-knowledge-writing-composition

- line key：`service_surface`；kind：`service_surface`
- owner：B-recheck; typed-knowledge/writing owner
- donor evidence：8 个源文件；未跟踪 0 个
- 现有 cell/movement 映射：cells `C8.1, C8.2, C8.4`；movements `C8-M001, C8-M002, C8-M004, C8-M005`
- gaps：`无`
- disposition：**REIMPLEMENTED_AS**
- successor 目标：knowledge-core/C8, writing-core/C8, graph-projection/C8
- 备注：C8.1/C8.2/C8.4 movements map the typed-knowledge/writing composition surface; declared legacy convenience loss applies. Local-only, no authority.

### BL-llm-report-trend-quality-records

- line key：`service_surface`；kind：`service_surface`
- owner：B-recheck; report trend owner
- donor evidence：4 个源文件；未跟踪 2 个；main/backend/app/services/llm_report_trends.py; main/backend/app/models/llm_report_trends.py
- 现有 cell/movement 映射：cells `UNKNOWN`；movements `C8-M003`
- gaps：`GAP-llm-report-quality-trends`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：UNKNOWN; report-admission/C8 consumer candidate
- 备注：Trend records are evidence-trace material with no movement/cell in the current C1-C9 map.

### BL-runtime-health-matrix

- line key：`service_surface`；kind：`service_surface`
- owner：B-recheck; runtime ops owner
- donor evidence：3 个源文件；未跟踪 2 个；scripts/runtime_health_matrix.py; scripts/build_business_line_async_readiness_artifact.py
- 现有 cell/movement 映射：cells `UNKNOWN`；movements `无`
- gaps：`无`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：UNKNOWN; runtime ops shared surface
- 备注：No dedicated locator cell or gap row; shares runtime_health_matrix.py donor path with GAP-runtime-ops. No dedicated cell; runtime_health_matrix.py is donor path of GAP-runtime-ops.

### BL-admin-crawler-cluechain-codexauth-keyword-stats

- line key：`service_surface`；kind：`service_surface`
- owner：B-recheck; admin/ops owner
- donor evidence：8 个源文件；未跟踪 0 个
- 现有 cell/movement 映射：cells `UNKNOWN`；movements `C9-M001`
- gaps：`GAP-remaining-backend-surfaces`
- disposition：**UNASSIGNED_BLOCKER**
- successor 目标：UNKNOWN; C9.1 envelope only
- 备注：Remaining tracked backend groups have no dedicated successor cells; structural envelope is not capability ownership.

### Disposition 汇总

| disposition | 条线数 |
|---|---|
| UNASSIGNED_BLOCKER | 16 |
| REIMPLEMENTED_AS | 2 |

现有映射行级汇总来自 `LegacyVsMovementGap.v1.json`：mapped 14、declared_loss_or_rejected 14、unmapped_gap 15；P1 30 cell 已全部审阅但未授予迁移/写入 authority。

## 3. 冻结清单（SHA/bytes/lines）

引用 evidence 的 SHA-256 为写稿时现场计算。本 scope 两份新文档处于 DRAFT，不做自引用字节冻结；实际 SHA-256/bytes/lines 由起草回传外部提供，supervisor freeze pass 应密封为正式 receipt。

| 文件 | SHA-256 | bytes | lines |
|---|---|---|---|
| `evidence/all-lines-investigation/BackendDonorSurfaceInventory.v1.json` | `1328969a9d05a2d583f0ff0862c30de166b932c3ed3df3446ddc9ee5520492bd` | 78549 | 1804 |
| `evidence/all-lines-investigation/LegacyVsMovementGap.v1.json` | `401699e5237f776a72dc736c127e5d9d6ad4911d30fb381b583805ddc02c7af7` | 33764 | 795 |
| `evidence/P1FunctorizationEligibility.v1.json` | `16dac2d34f2cdcaeffa4718fe2e63733f48b29ad0ba64daab32ed011527d4642` | 408332 | 7165 |
| `evidence/semantic-movement/p1-p3-semantic-movement-spec.v1.json` | `2a96bb63d0e3b548173558959da9fc4421024f300d9c39daf6dda5f7b79e53d2` | 99846 | 1065 |
| `04_functorial-successor-capability-ledger.json` | `f6fb3748ea30522712ed510f52c5163e9d67fae8b6a162ad7af5acbbefc6d36e` | 85163 | 1535 |
| `evidence/all-lines-investigation/AllLinesMigrationScope.freeze.v1.json` | `EXTERNAL_POST_DRAFT` | external | external |
| `evidence/all-lines-investigation/AllLinesMigrationScope.freeze.v1.md` | `EXTERNAL_POST_DRAFT` | external | external |

## 4. 迁移顺序与工作包建议（共享基底优先）

顺序：WP-0 冻结裁决 -> WP-1 donor 字节闭包/parity 证据 -> WP-2 共享 substrate/生成器收敛 -> WP-3 worker-required 垂直切片 -> WP-4 横向 service ports -> WP-5 report export 家族 -> WP-6 剩余 ops/governance/meta 与 loss profile。最后才允许单独 authority milestone 讨论 provider/live/cutover；本草案 authority 保持 false。

### WP-0：supervisor scope freeze and blocker adjudication

- 目标：Resolve every UNASSIGNED_BLOCKER owner/successor and accept or amend this freeze draft; leave authority false.
- 输入：AllLinesMigrationScope.freeze.v1.json; AllLinesMigrationScope.freeze.v1.md; BackendDonorSurfaceInventory.v1.json; LegacyVsMovementGap.v1.json
- 输出：supervisor freeze record; amended line adjudication if required
- 允许读写：same all-lines-investigation evidence directory; supervisor-controlled freeze manifests
- 验收：line-level UNASSIGNED_BLOCKER count and every gap owner are explicit; candidate/authority remain null/false or a separately authorized milestone records change

### WP-1：donor byte closure and parity evidence binding

- 目标：Expand donor registry closure to every business-line and untracked family path (35 untracked registry files plus supplementary LegacyVsMovementGap paths), with byte and line closure and old-to-new movement parity.
- 输入：BackendDonorSurfaceInventory.v1.json; LegacyVsMovementGap.v1.json; p1-p3-semantic-movement-spec.v1.json
- 输出：expanded donor path/byte registry; old-to-new movement matrix; parity/digestion checkers
- 允许读写：evidence/all-lines-investigation and semantic-movement evidence directories only; no legacy donor or production writes
- 验收：every BL donor source and untracked family path resolves to a byte hash; parity counts match and UNASSIGNED gaps are reduced without changing authority

### WP-2：shared substrate and capability-spec generator convergence

- 目标：Freeze one shared typed substrate/program/capability-spec generator consumed by every successor family; do not duplicate per-lane stacks.
- 输入：P1FunctorizationEligibility.v1.json; p1-p3-semantic-movement-spec.v1.json; 04 ledger phase P4 pilot tooling
- 输出：shared substrate contracts; generator/matched artifacts and law tests
- 允许读写：main/backend/app/successor_runtime and evidence/capability-spec* directories
- 验收：generator match/read-only check exit contract; law tests for identity/ordered composition; all families reuse shared substrate

### WP-3：worker-required canonical vertical slices

- 目标：Complete C7/C2/C3/C4/C5/C6/C8 vertical slices for ingest, search/discovery, source-library and writing worker-required lanes with readback and recovery; bind ingest registry and guard gaps after WP-0.
- 输入：WP-1 registry; WP-2 shared substrate; LegacyVsMovementGap mapped/loss rows
- 输出：capability packets; vertical slice tests; lane readback evidence
- 允许读写：successor_runtime packages and per-family test directories; legacy donor read-only
- 验收：per-lane parity/readback/recovery gates pass; line-level blocker count drops only with a supervisor record

### WP-4：horizontal service ports

- 目标：Adjudicate and implement request identity, task-readback metadata, single-source guard, agent-batch quality promotion and runtime health matrix as shared ports/effects over substrate.
- 输入：WP-0 dispositions; BackendDonorSurfaceInventory service_surface records
- 输出：typed port contracts and effect interpreters; authority/recovery tests
- 允许读写：successor_runtime horizontal ports and tests
- 验收：effect/failure/authority/recovery explicit; no credential value binding required for scope freeze

### WP-5：report export/audit/token/trend family

- 目标：Bind llm_report_export/audit/token_state/trends under C8.3 admission with durable one-time token, audit events and trend records.
- 输入：untracked donor family paths; C8-M003 movement record
- 输出：C8.3 successor export/audit realization; token/audit/trend tests
- 允许读写：successor_runtime C8/delivery packages and tests
- 验收：revocation/crash/recovery/admission digest closure; no live provider claim without separate authority milestone

### WP-6：remaining ops/governance/meta surfaces and loss profile

- 目标：Create successor cells or explicit declared-loss/no-call records for projects/config, dashboard/admin/governance, runtime ops, business-line evidence matrix and remaining backend surface; close the line-level UNASSIGNED_BLOCKER count.
- 输入：WP-0 freeze; BackendDonorSurfaceInventory uncovered_items; 14 declared-loss/rejected rows
- 输出：line-level disposition closure record; loss/no-call manifest
- 允许读写：migration evidence and successor capability specs
- 验收：UNASSIGNED_BLOCKER == 0 at all-lines level; authority/cutover still false and separate

## 5. 风险

- 16 of 18 business-line records remain UNASSIGNED_BLOCKER at line level; 15 unmapped-gap rows and an evidence omission for agent-batch quality promotion require supervisor adjudication.
- 35 donor registry files and the named untracked families are absent from clean donor HEAD and the migration worktree; byte freeze depends on working-tree snapshots, not git commits.
- C7 movement matrix is external and not promoted; 04 ledger wording is internal/pending and grants no promotion.
- No live provider, external delivery, business authority transfer or cutover authority is claimed.
- Directory-level donor paths in LegacyVsMovementGap (crawlers, graph, indexer, writing and related families) are not expanded in BackendDonorSurfaceInventory; WP-1 must expand them before a byte-closure freeze.
- This draft does not bind its own byte hash (self-reference); actual SHA-256/bytes/lines are reported externally in the handoff and must be sealed by the supervisor freeze pass.

