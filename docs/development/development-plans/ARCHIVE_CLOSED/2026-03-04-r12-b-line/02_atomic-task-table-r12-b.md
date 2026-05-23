<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-04-r12-b-line/02_atomic-task-table-r12-b.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-04-r12-b-line/02_atomic-task-table-r12-b.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# R12 B线原子任务表（M1）

- date: 2026-03-04
- scout_batch_id: `2026-03-04-scout-r12`
- task_id: `B-R12-M1`
- goal: required-check 名称冻结清单并与 ruleset 机读对齐
- scope: B线仓库内最小切片，仅 warning 灰度

research:
- Source-of-truth workflow: `.github/workflows/backend-tests.yml`.
- Existing convergence contract is declared in `gateplus-required-check` via `required = ("standards-check", "gateplus-guard-check", "r81-b-min-verify-check")`.
- Required check gate name in workflow is `gateplus-required-check`.

plan:
- Add one machine-readable emitter script to freeze required checks for `B-R12-M1`.
- Generate artifact at `/Users/wangyiliang/market-research-workflow-parallel-20260303-215619-B/artifacts/gates/r12_b/required-check-freeze.json`.
- Keep mode in warning (non-blocking) for this round; preserve failure isolation to governance/CI gate scope.

atomic:
- 原子任务并行序列:
  - P1 (parallel):
    - AT1: 提取 workflow 中 required tuple（`standards-check`, `gateplus-guard-check`, `r81-b-min-verify-check`）。
    - AT2: 提取 gate job 名称（`gateplus-required-check`）并读取 ruleset 对齐来源。
  - P2 (serial):
    - AT3: 生成机读冻结产物（JSON）并写入 warning 模式、failure isolation 元数据。
- Implementation file:
  - `scripts/governance/emit_required_check_freeze.py`

ver:
- Repro command 1:
  - `python3 /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-B/scripts/governance/emit_required_check_freeze.py --mode warning --out /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-B/artifacts/gates/r12_b/required-check-freeze.json`
- Repro command 2:
  - `python3 -m json.tool /Users/wangyiliang/market-research-workflow-parallel-20260303-215619-B/artifacts/gates/r12_b/required-check-freeze.json >/dev/null`
- Expected:
  - Artifact exists and JSON valid.
  - `alignment.workflow.status=pass`.
  - `alignment.ruleset.status=warn` (local ruleset config absent in repo, workflow contract aligned).

close:
- M1 output artifact path (absolute):
  - `/Users/wangyiliang/market-research-workflow-parallel-20260303-215619-B/artifacts/gates/r12_b/required-check-freeze.json`
- Gray strategy:
  - warning only (`blocking_enabled=false`).
- Failure isolation:
  - only governance/CI gate contract evaluation; no business/API/DB path impact.
- rollback_ref:
  - `0b54e98b6e72bbe3e2e0b14e576f5b5a43ea9e05`
