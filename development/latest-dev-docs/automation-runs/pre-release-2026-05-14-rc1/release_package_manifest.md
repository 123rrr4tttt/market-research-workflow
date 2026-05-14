# pre-release-2026-05-14-rc1 release merge manifest

This manifest records the current workstreams merged into the named pre-release
version. It is not a physical tar/zip package and does not require generating
an archive.

## Release identity

- Release: `pre-release-2026-05-14-rc1`
- Primary note: `RELEASE_NOTES_pre-release-2026-05-14-rc1.md`
- Completion audit: `development/latest-dev-docs/automation-runs/pre-release-2026-05-14-rc1/completion_audit.md`
- Gate reports:
  - `development/latest-dev-docs/automation-runs/pre-release-2026-05-14-rc1/min-gate.json`
  - `development/latest-dev-docs/automation-runs/pre-release-2026-05-14-rc1/min-gate-strict.json`

## Merged work areas

- Backend API and services:
  - `main/backend/app/api/agent_chat.py`
  - `main/backend/app/api/projects.py`
  - `main/backend/app/api/writing.py`
  - `main/backend/app/services/agent_core/`
  - `main/backend/app/services/agent_runtime/`
  - `main/backend/app/services/local_index/`
  - `main/backend/app/services/source_library/source_candidate_trust.py`
  - `main/backend/app/services/search/web.py`
  - `main/backend/app/services/writing/`
- Backend tests and gates:
  - `main/backend/scripts/pre_release_gate.sh`
  - `main/backend/docs/API_LAYER_MODEL_IMPORT_ALLOWLIST.txt`
  - `main/backend/docs/API_LAYER_HTTP_EXCEPTION_DETAIL_ALLOWLIST.txt`
  - `main/backend/tests/unit/test_agent_*`
  - `main/backend/tests/unit/test_interactive_agent_runtime_unittest.py`
  - `main/backend/tests/unit/test_local_index_service_unittest.py`
  - `main/backend/tests/unit/test_material_ontology_unittest.py`
  - `main/backend/tests/unit/test_search_web_provider_adapters_unittest.py`
  - `main/backend/tests/unit/test_source_candidate_trust_unittest.py`
  - `main/backend/tests/unit/test_structured_data_search_unittest.py`
  - `main/backend/tests/integration/test_agent_*`
  - `main/backend/tests/integration/test_writing_api_unittest.py`
- Frontend modern:
  - `main/frontend-modern/src/pages/AgentChatPage.tsx`
  - `main/frontend-modern/src/pages/WritingWorkbenchPage.tsx`
  - `main/frontend-modern/src/components/writing/AgentWritingAssistantPanel.tsx`
  - `main/frontend-modern/src/components/writing/MarkdownEditor.tsx`
  - `main/frontend-modern/src/app/kernel/`
  - `main/frontend-modern/src/lib/api*`
  - `main/frontend-modern/tests/e2e/`
- Deployment and operations:
  - `scripts/launch.py`
  - `scripts/configure-external-services.py`
  - `scripts/pre_release_min_gate.sh`
  - `scripts/docker-deploy.sh`
  - `scripts/local-deploy.sh`
  - `scripts/platform-macos.sh`
  - `scripts/platform-linux.sh`
  - `scripts/platform-windows.ps1`
  - `scripts/build-macos-launcher.sh`
  - `tools/macos/Launcher.swift`
  - `main/ops/README.md`
  - `main/ops/start-all.sh`
  - `main/ops/docker-compose.yml`
  - `ops/search-lab/`
  - `tools/macos/Launcher.swift`
- Documentation and evidence:
  - `README.md`
  - `RELEASE_NOTES_pre-release-0.md`
  - `development/latest-dev-docs/README.md`
  - `development/latest-dev-docs/MERGED_OVERVIEW.md`
  - `development/latest-dev-docs/development-plans/`
  - `development/latest-dev-docs/automation-runs/`

## Local artifacts excluded from the pre-release boundary

- `main/backend/.venv311/` is removed from git tracking and ignored.
- `.autonomous/` is ignored.
- `.playwright-mcp/` is ignored.
- `main/frontend-modern/dist/` remains ignored by the frontend project.
- `tmp/open-source-references/**` is ignored for local reference clone churn; existing tracked gitlinks are outside the application runtime boundary.

## Team deployment entrypoints

```bash
cp main/backend/.env.example main/backend/.env
./scripts/docker-deploy.sh preflight
./scripts/docker-deploy.sh start --profile modern-ui
./scripts/docker-deploy.sh health
```

```bash
./scripts/pre_release_min_gate.sh --strict --report development/latest-dev-docs/automation-runs/pre-release-2026-05-14-rc1/min-gate-strict.json
```
