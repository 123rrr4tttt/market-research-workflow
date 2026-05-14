# pre-release-2026-05-14-rc1 completion audit

Audit time: 2026-05-14 PST

## Objective restated

Merge the current workstreams into one named pre-release project update so team members can deploy the new version with maintained code, documentation, startup scripts, rollback path, and verification evidence. This is a version-boundary merge, not a physical tar/zip archive.

## Prompt-to-artifact checklist

| Requirement | Artifact / command | Evidence | Status |
|---|---|---|---|
| Merge current workstreams as a named pre-release | `RELEASE_NOTES_pre-release-2026-05-14-rc1.md` | Release name, scope, changed subsystems, version boundary, known risks, regression checklist | Pass |
| Provide release merge manifest | `development/latest-dev-docs/automation-runs/pre-release-2026-05-14-rc1/release_package_manifest.md` | Merged work areas, excluded local artifacts, and team deployment entrypoints are listed | Pass |
| Maintain project documentation | `README.md`, `development/latest-dev-docs/README.md`, `development/latest-dev-docs/MERGED_OVERVIEW.md` | Top-level and dev-doc indexes link to the current pre-release note | Pass |
| Maintain deployment and startup scripts | `scripts/docker-deploy.sh`, `scripts/local-deploy.sh`, `main/ops/README.md` | README and ops guide route team deployment through Docker-first and local-deploy entrypoints | Pass |
| Support cross-platform startup and local external service setup | `scripts/launch.py`, `scripts/platform-macos.sh`, `scripts/platform-linux.sh`, `scripts/platform-windows.ps1`, `scripts/configure-external-services.py`, `tools/macos/Launcher.swift` | One Python GUI opens on all supported platforms; platform `configure` opens the GUI; macOS launcher shows external service readiness and opens graphical key setup | Pass |
| Provide provider links inside the settings window | `scripts/launch.py`, `tools/macos/Launcher.swift` | Settings rows include provider `Open` buttons; macOS quick panel links to OpenAI and Serper plus the full settings UI | Pass |
| Fix Docker startup when local infra ports are occupied | `main/ops/start-all.sh` | `--force` creates a compose override that removes host bindings for db/es/redis while keeping backend/frontend exposed | Pass |
| Maintain release quality gate | `scripts/pre_release_min_gate.sh`, `main/backend/scripts/pre_release_gate.sh` | Gate now runs frontend lint/build, backend Agent/Writing/Search/Local Index tests, rollback dry-run, metrics schema, and hygiene check | Pass |
| Cover backend changes | `main/backend/scripts/pre_release_gate.sh --strict` via root gate | 127 backend tests passed, plus API import guard passed with no new unexpected entries | Pass |
| Cover frontend deployability | `npm run lint`, `npm run build` via root gate | Vite production build succeeded; lint passed | Pass |
| Cover rollback / deployment readiness | `./scripts/docker-deploy.sh rollback-drill --dry-run --skip-preflight` via root gate | Rollback drill command sequence validated | Pass |
| Persist machine-readable gate evidence | `development/latest-dev-docs/automation-runs/pre-release-2026-05-14-rc1/min-gate.json` | All phases `pass`, result `pass` | Pass |
| Persist strict gate evidence | `development/latest-dev-docs/automation-runs/pre-release-2026-05-14-rc1/min-gate-strict.json` | All phases `pass`, result `pass` | Pass |
| Exclude local-only runtime artifacts | `.gitignore`, `git rm --cached main/backend/.venv311` | `.venv311` no longer tracked; `.autonomous`, `.playwright-mcp`, frontend `dist`, and tmp reference clones are ignored or clean | Pass |
| Check patch hygiene for code/docs/scripts | `git diff --check -- ':!main/backend/seed_data/project_demo_proj_v0.9-rc2.0.sql'` | Passed; seed SQL is treated as a raw data dump exception | Pass |

## Verification summary

```text
./scripts/pre_release_min_gate.sh --report development/latest-dev-docs/automation-runs/pre-release-2026-05-14-rc1/min-gate.json
result: pass
lint: pass
frontend_build: pass
backend: pass
rollback_drill: pass
metrics_schema: pass
```

```text
./scripts/pre_release_min_gate.sh --strict --report development/latest-dev-docs/automation-runs/pre-release-2026-05-14-rc1/min-gate-strict.json
result: pass
lint: pass
frontend_build: pass
backend: pass
rollback_drill: pass
metrics_schema: pass
```

Backend strict gate details:

```text
127 passed, 11 warnings, 5 subtests passed
API import guard: No new API-layer direct model imports found.
API HTTPException guard: No new API-layer HTTPException(detail=...) raises found.
```

## Residual risks

- The Docker rollback drill was executed in dry-run mode, not as a live container stop/start cycle.
- External LLM, search provider, and MCP capabilities still depend on local `.env` and external service availability.
- Existing FastAPI / Pydantic deprecation warnings remain non-blocking and should be scheduled separately.
- Full `git diff --check` reports whitespace inside `main/backend/seed_data/project_demo_proj_v0.9-rc2.0.sql`; this file contains raw PDF / webpage seed content and is excluded from code/doc whitespace hygiene.
