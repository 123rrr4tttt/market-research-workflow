# Backend Core Architecture Migration Entry

> Date: 2026-05-22
> Status: Wave16 moved-file batch; shared navigation remains compatibility-bound
> Manifest: [latest-dev-docs-entry-manifest.json](../latest-dev-docs-entry-manifest.json)
> Target root: `docs/architecture/backend-core`
> Shim: `docs/architecture/backend-core/README.md`

This entry maps the explicit backend-core architecture tree into the future `docs/architecture/` taxonomy. Wave16 moved the single low-ambiguity backend-core architecture README into this target root and left the old latest-dev-docs path as a compatibility shim.

## Moved Content Batch

| Previous compatibility path | Authoritative target | Role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/backend-core/A_ARCHITECTURE/README.backend-core.md](../../../development/latest-dev-docs/backend-core/A_ARCHITECTURE/README.backend-core.md) | [docs/architecture/backend-core/A_ARCHITECTURE/README.backend-core.md](./A_ARCHITECTURE/README.backend-core.md) | explicit architecture README | content moved; target authoritative |

## Compatibility Entries

| Source path | Readable compatibility entry | Target role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/backend-core/A_ARCHITECTURE](../../../development/latest-dev-docs/backend-core/A_ARCHITECTURE) | [development/latest-dev-docs/backend-core/A_ARCHITECTURE/README.backend-core.md](../../../development/latest-dev-docs/backend-core/A_ARCHITECTURE/README.backend-core.md) | compatibility shim | target authoritative; source shim retained |

## Compatibility Rule

The moved target file is authoritative for this backend-core architecture README. The old latest-dev-docs file remains as a compatibility shim until a supervisor-owned integration pass updates shared navigation and shared overview references.
