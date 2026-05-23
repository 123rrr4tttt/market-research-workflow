# Development Plans Migration Entry

> Date: 2026-05-22
> Status: Wave25 moved-file batch; selected main files are target authoritative
> Manifest: [latest-dev-docs-entry-manifest.json](../latest-dev-docs-entry-manifest.json)
> Target root: `docs/development/development-plans`
> Shim: `docs/development/development-plans/README.md`

This entry maps low-ambiguity development-planning material from the compatibility root into the future `docs/development/` taxonomy. Wave25 moved the two `development-plans/main` files into this target root and left the old latest-dev-docs paths as compatibility shims.

## Moved Content Batch

| Previous compatibility path | Authoritative target | Role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/development-plans/main/index.md](../../../development/latest-dev-docs/development-plans/main/index.md) | [docs/development/development-plans/main/index.md](./main/index.md) | main entry | content moved; target authoritative |
| [development/latest-dev-docs/development-plans/main/MERGED_DEVELOPMENT_PLANS.md](../../../development/latest-dev-docs/development-plans/main/MERGED_DEVELOPMENT_PLANS.md) | [docs/development/development-plans/main/MERGED_DEVELOPMENT_PLANS.md](./main/MERGED_DEVELOPMENT_PLANS.md) | merged snapshot | content moved; target authoritative |

## Compatibility Entries

| Source path | Readable compatibility entry | Target role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/development-plans/main](../../../development/latest-dev-docs/development-plans/main) | [development/latest-dev-docs/development-plans/main/index.md](../../../development/latest-dev-docs/development-plans/main/index.md) | moved-file compatibility shim | target authoritative; source shim retained |
| [development/latest-dev-docs/development-plans/CURRENT_DEV](../../../development/latest-dev-docs/development-plans/CURRENT_DEV) | [development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md](../../../development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md) | active plan root shim | content shim; source authoritative |

## Compatibility Rule

The moved target files are authoritative for this main development-plans batch. The old latest-dev-docs files remain as compatibility shims until shared navigation fully switches to `docs/development`. `CURRENT_DEV` remains source-authoritative because it is the active status surface.
