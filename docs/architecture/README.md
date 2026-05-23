# Architecture Documentation Root

> Date: 2026-05-22
> Status: partial moved-file batches; shared navigation remains compatibility-bound

## Purpose

`docs/architecture/` is the target root for long-lived system structure, cross-cutting constraints, and target-state topology that is currently mixed into `development/latest-dev-docs`.

Use this root for:

- architecture decision records and target-state papers;
- module boundary and ownership notes;
- cross-service topology and integration constraints;
- durable system diagrams or narrative architecture references.

## Compatibility Path

The current readable entrypoint remains [development/latest-dev-docs](../../development/latest-dev-docs/README.md). This root is prepared for migration targets, but it does not replace the compatibility entry until an integration batch updates shared navigation.

The docs-root restructuring plan is tracked in [2026-03-07 docs root restructuring](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md).

The first content shim batch is recorded in [latest-dev-docs-entry-manifest.json](./latest-dev-docs-entry-manifest.json). These entries keep `development/latest-dev-docs` as the content authority while the README shims under this root provide readable pointers to the current compatibility entries. Shared navigation still belongs to the integration lane.

The bounded content-plan gate is recorded in [latest-dev-docs-content-plan.json](./latest-dev-docs-content-plan.json) and checked by [scripts/checkers/check_docs_root_content_plan.py](../../scripts/checkers/check_docs_root_content_plan.py). Wave20 now records validated `moved_file_batch` entries for backend-core, root-plans, ops-frontend, backend-docs, and development-plans architecture content while keeping docs-root migration blocked by shared navigation, CURRENT_DEV status sync, and `MERGED_OVERVIEW` drift where still applicable.

## Moved Content Batches Through Wave20

| Target root | Authoritative content | Compatibility shim | Manifest entry |
|---|---|---|---|
| `docs/architecture/backend-core` | [docs/architecture/backend-core/A_ARCHITECTURE/README.backend-core.md](./backend-core/A_ARCHITECTURE/README.backend-core.md) | [development/latest-dev-docs/backend-core/A_ARCHITECTURE/README.backend-core.md](../../development/latest-dev-docs/backend-core/A_ARCHITECTURE/README.backend-core.md) | `backend-core-architecture-tree` |
| `docs/architecture/root-plans` | [docs/architecture/root-plans/A_ARCHITECTURE/README.md](./root-plans/A_ARCHITECTURE/README.md) | [development/latest-dev-docs/root-plans/A_ARCHITECTURE/README.md](../../development/latest-dev-docs/root-plans/A_ARCHITECTURE/README.md) | `root-plans-architecture-tree` |
| `docs/architecture/ops-frontend` | [docs/architecture/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md](./ops-frontend/A_ARCHITECTURE/frontend-modern-README.md) | [development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md](../../development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md) | `ops-frontend-architecture-tree` |
| `docs/architecture/backend-docs` | [docs/architecture/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md](./backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md) | [development/latest-dev-docs/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md](../../development/latest-dev-docs/backend-docs/A_ARCHITECTURE/API_CONTRACT_STANDARD.md) | `backend-docs-architecture-tree` |
| `docs/architecture/development-plans` | [docs/architecture/development-plans/A_ARCHITECTURE/INDEX.md](./development-plans/A_ARCHITECTURE/INDEX.md) | [development/latest-dev-docs/development-plans/A_ARCHITECTURE/INDEX.md](../../development/latest-dev-docs/development-plans/A_ARCHITECTURE/INDEX.md) | `development-plans-architecture-tree` |

## Target Routing

| Source family | Target under this root | Notes |
|---|---|---|
| `development/latest-dev-docs/*/A_ARCHITECTURE/` | `docs/architecture/<source>/A_ARCHITECTURE/` | Default destination for explicit architecture trees. |
| Long-horizon design docs in `development-plans/` | `docs/architecture/development-plans/` | Promote only when the document is architecture, not execution tracking. |
| Architecture sections inside mixed `main/` trees | file-level routing only | Do not move whole `main/` directories blindly. |
| Architecture evidence under review archives | file-level routing only | Keep policy or release judgment in `docs/governance/`. |

## Adjacent Roots

- [docs/development](../development/) receives active plans, execution history, and stage-specific evidence.
- [docs/implementation](../implementation/) receives adopted workflows, stable API/interface notes, test baselines, and accepted delivery evidence.
- [docs/governance](../governance/) receives release policy, review conclusions, reliability baselines, and operational governance rules.

## Minimum Promotion Rule

A document should move into this root only when the migration note identifies:

1. the previous compatibility path;
2. the new target path;
3. why the document is architecture rather than development or implementation material;
4. the link-check command used for the changed paths.
