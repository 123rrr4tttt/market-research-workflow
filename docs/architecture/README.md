# Architecture Documentation Root

> Date: 2026-05-22
> Status: target root prepared; compatibility entry still lives at `development/latest-dev-docs`

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
