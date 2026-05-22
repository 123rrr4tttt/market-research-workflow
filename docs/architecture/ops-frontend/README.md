# Ops Frontend Architecture Migration Entry

> Date: 2026-05-22
> Status: Wave17 moved-file batch; shared navigation remains compatibility-bound
> Manifest: [latest-dev-docs-entry-manifest.json](../latest-dev-docs-entry-manifest.json)
> Target root: `docs/architecture/ops-frontend`
> Shim: `docs/architecture/ops-frontend/README.md`

This entry maps the explicit ops-frontend architecture tree into the future `docs/architecture/` taxonomy. Wave17 moved the low-ambiguity ops-frontend architecture files into this target root and left the old latest-dev-docs paths as compatibility shims.

## Moved Content Batch

| Previous compatibility path | Authoritative target | Role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/DIR_MAP.md](../../../development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/DIR_MAP.md) | [docs/architecture/ops-frontend/A_ARCHITECTURE/DIR_MAP.md](./A_ARCHITECTURE/DIR_MAP.md) | ops-frontend directory map | content moved; target authoritative |
| [development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md](../../../development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md) | [docs/architecture/ops-frontend/A_ARCHITECTURE/frontend-modern-README.md](./A_ARCHITECTURE/frontend-modern-README.md) | frontend-modern architecture summary | content moved; target authoritative |

## Compatibility Entries

| Source path | Readable compatibility entry | Target role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/ops-frontend/A_ARCHITECTURE](../../../development/latest-dev-docs/ops-frontend/A_ARCHITECTURE) | [development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/DIR_MAP.md](../../../development/latest-dev-docs/ops-frontend/A_ARCHITECTURE/DIR_MAP.md) | compatibility shim | target authoritative; source shim retained |

## Compatibility Rule

The moved target files are authoritative for this ops-frontend architecture batch. The old latest-dev-docs files remain as compatibility shims until a supervisor-owned integration pass updates shared navigation and shared overview references.
