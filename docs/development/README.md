# Development Documentation Root

> Last updated: 2026-10-05
> Status: current reading root; local daily evidence, stopped production history, and archived development records are kept as separate facts

## Current Reading Path

This is the single current entry for development reading. Start from the role you need:

- **Local daily operation**: use [README.md](../../README.md) for the 2026-10-04 local chain, business capabilities, ports, worker/Codex WebUI lifecycle, OAuth ownership, and evidence path `.data/readiness-repair/20261004-daily-chain/daily-chain-state.json`. The vendored service entry is [main/ops/codex-webui/README.md](../../main/ops/codex-webui/README.md).
- **Stopped production history**: read the production stage record at [development-plans/CURRENT_DEV/2026-09-04-formal-production-release/06_production-deployment-stage-progress.v1.md](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/06_production-deployment-stage-progress.v1.md). Its current header records local acceptance, cleanup completion, stopped execution, deferred release, and no production authority. Treat later sections as historical snapshots.
- **Current maintenance framework and dispatch packages**: read [MRW maintenance plan §10](./MRW结构整理方案与分发包.md#10-当前维护收敛框架与串并行分发包) for the 2026-10-05 framework, package ownership, sequential/parallel dependencies, test resources, and exit conditions. All 15 maintenance packages are complete; implementation results, validation, and retained history are recorded in §10.11.
- **Completed structure and repair work**: read [MRW structure result §8](./MRW结构整理方案与分发包.md#8-实际实施进度) for the completed 2026-10-04 implementation scope and [full-repair package §4](./MRW全量核查修复分发包.md#4-可直接复用的验证入口) for reusable repair verification. The machine summary [execution-state.json](../../.data/structure-cleanup/20261004/execution-state.json) retains that execution's attribution and does not report the new maintenance packages as complete.
- **Stable implementation and operations**: use [docs/architecture](../architecture/) and [docs/implementation](../implementation/).
- **Closed and blocked development history**: use the development-plans indexes below.

The compatibility tree remains at [development/latest-dev-docs](../../development/latest-dev-docs/README.md). It is a compatibility and historical index, not the default current reading root.

## Development Surfaces

Use this root for:

- active plans and execution boards;
- design briefs and atomic tasklists;
- bounded execution and review evidence that has not become stable implementation guidance;
- classified historical archives and compatibility shims.

| Surface | Read here | Meaning |
| --- | --- | --- |
| Root README | [README.md](../../README.md) | Current usage, local runtime, project contribution checks, and stopped-production boundary |
| Current maintenance work | [MRW maintenance plan §10](./MRW结构整理方案与分发包.md#10-当前维护收敛框架与串并行分发包) | 15 packages complete; implementation and validation in §10.11 |
| Completed structure work | [MRW structure result §8](./MRW结构整理方案与分发包.md#8-实际实施进度) | Completed 2026-10-04 scope and verification attribution |
| Historical development plans | [development-plans/README.md](./development-plans/README.md) | Archive and migration navigation; current maintenance work is linked above |
| Frontend records | [frontend-modern/README.md](./frontend-modern/README.md) | Frontend planning and review records |
| Root plans | [root-plans/README.md](./root-plans/README.md) | Repository-level planning records |
| Architecture | [docs/architecture](../architecture/) | Long-lived structure and target-state decisions |
| Implementation | [docs/implementation](../implementation/) | Adopted workflows, API/interface notes, test baselines, and accepted delivery evidence |

## Daily Versus Production Facts

Daily facts are observable from the current machine: the local frontend, API, Codex WebUI, launchd worker, host OAuth sharing, and daily-chain evidence are described by the root README and its evidence JSON. Production facts remain historical: the 2026-09-13 production-stage record says local acceptance and cleanup completed, execution stopped, release was deferred, and release authority was not established. A later archived note can explain why a decision changed; it cannot turn stopped history into a current production instruction.

## Migration Governance and Compatibility

The compatibility tree remains reachable for old links and shared-history readers. Historical Wave25/31 shim records, evidence anchors, promoted navigation, and checker fields are retained in the collapsed migration record below; current reading starts at the top of this README.

<details>
<summary>Historical migration governance and Wave25/31 records</summary>

The docs-root restructuring record is [2026-03-07 docs root restructuring](./development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md).

The first content shim batch is recorded in [latest-dev-docs-entry-manifest.json](./latest-dev-docs-entry-manifest.json). These entries keep `development/latest-dev-docs` as the content authority while the README shims under this root provide readable pointers to the current compatibility entries. Shared navigation still belongs to the integration lane.

The bounded content-plan gate is recorded in [latest-dev-docs-content-plan.json](./latest-dev-docs-content-plan.json) and checked by [scripts/checkers/check_docs_root_content_plan.py](../../scripts/checkers/check_docs_root_content_plan.py). Wave25 moved the two `development-plans/main` files into `docs/development/development-plans/main/`. Wave27 moved the two `frontend-modern/main` files into `docs/development/frontend-modern/main/` and the two `root-plans/main` files into `docs/development/root-plans/main/`. Wave28 classified `CURRENT_DEV` as a supervisor-owned active status surface, not as a broad content move candidate. Wave29 decomposed the `ARCHIVE_CLOSED` broad-tree move into ledger-backed per-file batches, so `remaining_unsafe_moves` is now `0`; Wave31 executed the ledger-backed `ARCHIVE_CLOSED` moved-file batch, created target files under `docs/development/development-plans/ARCHIVE_CLOSED`, and left prior latest-dev-docs archive paths as compatibility shims. The closed docs-root topic evidence is now target-authoritative under `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring`.

## Docs Root Closure Evidence

Target-root navigation carries the post-Wave25 docs-root evidence anchors while shared navigation remains owned by the integration lane:

- Wave25 development-plans main move: [14_wave25-docs-root-development-main-move-2026-05-23.md](./development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/14_wave25-docs-root-development-main-move-2026-05-23.md)
- Wave27 root-plans main move: [15_wave27-worker-b-docs-root-root-plans-main-move-2026-05-23.md](./development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/15_wave27-worker-b-docs-root-root-plans-main-move-2026-05-23.md)
- Wave27 worker A reconciliation: [16_wave27-worker-a-docs-root-root-plans-main-reconciliation-2026-05-23.md](./development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/16_wave27-worker-a-docs-root-root-plans-main-reconciliation-2026-05-23.md)
- Wave28 CURRENT_DEV active surface decision: [17_wave28-docs-root-current-dev-supervisor-owned-2026-05-23.md](./development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/17_wave28-docs-root-current-dev-supervisor-owned-2026-05-23.md)
- Wave28 reviewer decision: [17_wave28-docs-root-reviewer-2026-05-23.md](./development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/17_wave28-docs-root-reviewer-2026-05-23.md)
- Wave28 archive closed classification: [18_wave28-worker-a-docs-root-archive-closed-classification-2026-05-23.md](./development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/18_wave28-worker-a-docs-root-archive-closed-classification-2026-05-23.md)
- Wave29 archive closed decomposition: [19_wave29-worker-a-docs-root-archive-closed-decomposition-2026-05-23.md](./development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/19_wave29-worker-a-docs-root-archive-closed-decomposition-2026-05-23.md)
- Wave29 shared navigation drift gate: [19_wave29-worker-b-docs-root-shared-navigation-drift-2026-05-23.md](./development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/19_wave29-worker-b-docs-root-shared-navigation-drift-2026-05-23.md)
- Wave30 target navigation readback: [20_wave30-docs-root-navigation-target-readback-2026-05-23.md](./development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/20_wave30-docs-root-navigation-target-readback-2026-05-23.md)
- Wave31 shared navigation sync: [21_wave31-docs-root-shared-navigation-sync-2026-05-23.md](./development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/21_wave31-docs-root-shared-navigation-sync-2026-05-23.md)

## Promoted Navigation Batch

Manifest promotion `development-root-reader-navigation-wave11` makes the existing development-root shims visible from this local root README. This is a reader navigation promotion only: it does not move content and does not update the shared latest-dev-docs indexes.

| Target root | Local navigation entry | Manifest entry IDs | Compatibility entry | Partial boundary |
|---|---|---|---|---|
| `docs/development/development-plans` | [docs/development/development-plans/README.md](./development-plans/README.md) | `development-plans-main-index`, `development-plans-main-merged`, `development-plans-current-dev-root` | `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md` | Main index and merged snapshot are target-authoritative; `CURRENT_DEV` is a supervisor-owned active status surface and remains source-authoritative. |
| `docs/development/frontend-modern` | [docs/development/frontend-modern/README.md](./frontend-modern/README.md) | `frontend-modern-main-index`, `frontend-modern-main-merged` | `development/latest-dev-docs/frontend-modern/main/index.md` | Main index and merged snapshot are target-authoritative; source paths remain compatibility shims. |
| `docs/development/root-plans` | [docs/development/root-plans/README.md](./root-plans/README.md) | `root-plans-f-plan-index`, `root-plans-main-index-mixed` | `development/latest-dev-docs/root-plans/F_PLAN/index.md` | Main index and merged snapshot are target-authoritative; `F_PLAN` remains compatibility-bound. |

## Target Routing

| Source family | Target under this root | Notes |
|---|---|---|
| `development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/` | `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-07-docs-root-restructuring/` | Closed docs-root topic evidence; previous topic files remain compatibility shims. |
| `development/latest-dev-docs/development-plans/CURRENT_DEV/` | `docs/development/development-plans/CURRENT_DEV/` | Supervisor-owned active status surface; do not move as a content batch while it owns live topic state. |
| `development/latest-dev-docs/*/F_PLAN/` | `docs/development/<source>/F_PLAN/` | Default destination for explicit planning material. |
| `development/latest-dev-docs/frontend-modern/` | `docs/development/frontend-modern/` | Development-oriented by default unless later promoted. |
| Mixed `main/` or archive trees | file-level routing only | Do not move whole mixed trees without classification. |

</details>

## Adjacent Roots

- [docs/architecture](../architecture/) receives long-lived structure and target-state decisions.
- [docs/implementation](../implementation/) receives adopted workflows, stable API/interface notes, test baselines, and accepted delivery evidence.
- [docs/governance](../governance/) receives release policy, review conclusions, reliability baselines, and operational governance rules.

## Minimum Promotion Rule

A document should move into this root only when the migration note identifies:

1. the previous compatibility path;
2. the new target path;
3. whether the moved file is authoritative or only an index shim;
4. the link-check command used for the changed paths.
