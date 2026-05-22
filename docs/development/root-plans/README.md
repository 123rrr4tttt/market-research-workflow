# Root Plans Migration Entry

> Date: 2026-05-22
> Status: mapped, not moved
> Manifest: [latest-dev-docs-entry-manifest.json](../latest-dev-docs-entry-manifest.json)

This entry maps the lowest-risk root-plans development entrypoints while keeping mixed `main/` content under the compatibility root.

## Mapped Sources

| Source | Target role | Authority status |
|---|---|---|
| [development/latest-dev-docs/root-plans/F_PLAN/index.md](../../../development/latest-dev-docs/root-plans/F_PLAN/index.md) | explicit plan index mapping | mapped, not moved |
| [development/latest-dev-docs/root-plans/main/index.md](../../../development/latest-dev-docs/root-plans/main/index.md) | mixed main entry mapping | mapped, not moved |

## Compatibility Rule

Only the explicit `F_PLAN` index is treated as low ambiguity. The `main/` entry is mapped for discoverability but must stay in place until file-level classification proves the mixed material can be split safely.
