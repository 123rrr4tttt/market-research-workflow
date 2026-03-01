# Root Plans Merge Review (2026-03-01)

## Review Scope
- Scope: `development/latest-dev-docs/root-plans`
- Check date: `2026-03-01`
- Focus: time labels, link/path validity, and source-attribution clarity

## Keep
| File | Time label | Link/source clarity | Decision |
|---|---|---|---|
| `README.md` | Updated `2026-03-01` | Core links mostly valid; now points to this review file | Keep as main entry |
| `RELEASE_NOTES_pre-release-0.9-rc2.0.md` | Release dated `2026-02-26` with sync notes `2026-02-27` / `2026-03-01` | Source references mostly resolvable | Keep as release baseline |
| `project-standardization-development-directions-2026-03-01.md` | Dated `2026-03-01` | Directional document; sources are strategy-level and acceptable | Keep as roadmap direction |
| `ingest-chain-evidence-matrix-2026-03-01.md` | Dated `2026-03-01` | Evidence path format is explicit (`main/backend/...`) | Keep as evidence record |

## Merge
| Candidate files | Reason | Merge action |
|---|---|---|
| `ingest-chain-taskboard-2026-03-01.md` + `ingest-chain-evidence-matrix-2026-03-01.md` | High overlap on same workstream; taskboard references same evidence | Keep both for now; treat `evidence-matrix` as source of truth and taskboard as summary |
| `status-8x-2026-02-27.md` + `RELEASE_NOTES_pre-release-0.9-rc2.0.md` (8.x sync section) | Both contain progress-state narrative | Keep release notes for version context; keep `status-8x` only as dated snapshot |

## Suspected Outdated / Needs Follow-up
| Item | Issue | Suggested handling |
|---|---|---|
| `status-8x-2026-02-27.md` | Date is older snapshot; multiple referenced round/decision files are missing in current repo | Mark as historical snapshot; do not treat as current execution board |
| `index.md` | Generated index contains `UNCOMMITTED` and point-in-time commit snapshot | Regenerate when publishing external status or release docs |
| `ingest-chain-taskboard-2026-03-01.md` | Original evidence paths were relative and ambiguous | Normalized to `main/backend/...`; missing unittest file explicitly marked |
| `README.md` (`tasks.py`) | `tasks.py` at repo root/backend root not found as written | Interpret as service task module (`main/backend/app/services/tasks.py`) in future edits |

## Link/Path Check Notes
- Missing local files found during this review:
  - `/app.html` (route-style reference, not repository file)
  - `tasks.py`
  - `main/backend/tests/test_project_key_policy_unittest.py`
  - `app/api/ingest.py`
  - `app/api/source_library.py`
  - `app/main.py`
  - `tests/test_project_key_policy_unittest.py`
  - `tests/conftest.py`
  - `plans/8x-round-1-2026-02-27.md`
  - `plans/8x-round-2-2026-02-27.md`
  - `plans/8x-round-2-2026-02-27-taskboard.md`
  - `plans/decision-log-2026-02-27.md`
- Existing local references were retained.
