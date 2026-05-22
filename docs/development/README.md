# Development Documentation Root

> Date: 2026-05-22
> Status: target root prepared; first content shim batch points to `development/latest-dev-docs`

## Purpose

`docs/development/` is the target root for active development planning and execution history that is currently concentrated under `development/latest-dev-docs`.

Use this root for:

- active plans and execution boards;
- design briefs and atomic tasklists;
- stage-specific evidence and review notes that have not become stable implementation guidance;
- historical development archives after they have been classified.

## Compatibility Path

The current readable entrypoint remains [development/latest-dev-docs](../../development/latest-dev-docs/README.md). Do not remove or bypass that compatibility path until a migration batch has updated the shared navigation and passed structure plus link checks.

The docs-root restructuring plan is tracked in [2026-03-07 docs root restructuring](../../development/latest-dev-docs/development-plans/CURRENT_DEV/2026-03-07-docs-root-restructuring/01_docs-root-restructuring-mapping-2026-03-07.md).

The first content shim batch is recorded in [latest-dev-docs-entry-manifest.json](./latest-dev-docs-entry-manifest.json). These entries keep `development/latest-dev-docs` as the content authority while the README shims under this root provide readable pointers to the current compatibility entries. Shared navigation still belongs to the integration lane.

## Target Routing

| Source family | Target under this root | Notes |
|---|---|---|
| `development/latest-dev-docs/development-plans/CURRENT_DEV/` | `docs/development/development-plans/CURRENT_DEV/` | Early migration candidate after shared navigation is ready. |
| `development/latest-dev-docs/*/F_PLAN/` | `docs/development/<source>/F_PLAN/` | Default destination for explicit planning material. |
| `development/latest-dev-docs/frontend-modern/` | `docs/development/frontend-modern/` | Development-oriented by default unless later promoted. |
| Mixed `main/` or archive trees | file-level routing only | Do not move whole mixed trees without classification. |

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
