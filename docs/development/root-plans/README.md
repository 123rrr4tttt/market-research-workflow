# Root Plans Migration Entry

> Date: 2026-05-22
> Status: content shim; source content remains in `development/latest-dev-docs`
> Manifest: [latest-dev-docs-entry-manifest.json](../latest-dev-docs-entry-manifest.json)
> Target root: `docs/development/root-plans`
> Shim: `docs/development/root-plans/README.md`

This content shim maps the lowest-risk root-plans development entrypoints while keeping mixed `main/` content under the compatibility root.

## Compatibility Entries

| Source path | Readable compatibility entry | Target role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/root-plans/F_PLAN/index.md](../../../development/latest-dev-docs/root-plans/F_PLAN/index.md) | [development/latest-dev-docs/root-plans/F_PLAN/index.md](../../../development/latest-dev-docs/root-plans/F_PLAN/index.md) | explicit plan index shim | content shim; source authoritative |
| [development/latest-dev-docs/root-plans/main/index.md](../../../development/latest-dev-docs/root-plans/main/index.md) | [development/latest-dev-docs/root-plans/main/index.md](../../../development/latest-dev-docs/root-plans/main/index.md) | mixed main entry shim | content shim; source authoritative |

## Compatibility Rule

Only the explicit `F_PLAN` index is treated as low ambiguity. The `main/` entry is mapped for discoverability but must stay in place until file-level classification proves the mixed material can be split safely.
