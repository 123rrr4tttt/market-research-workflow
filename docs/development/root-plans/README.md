# Root Plans Migration Entry

> Date: 2026-05-23
> Status: Wave27 moved-file batch; selected main files are target authoritative
> Manifest: [latest-dev-docs-entry-manifest.json](../latest-dev-docs-entry-manifest.json)
> Target root: `docs/development/root-plans`
> Shim: `docs/development/root-plans/README.md`

This entry maps the lowest-risk root-plans development entrypoints while preserving compatibility under `development/latest-dev-docs`. Wave27 classified the complete `development/latest-dev-docs/root-plans/main` batch as development planning content and moved the two main files into `docs/development/root-plans/main/`.

## Moved Content Batch

| Previous compatibility path | Authoritative target | Role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/root-plans/main/index.md](../../../development/latest-dev-docs/root-plans/main/index.md) | [docs/development/root-plans/main/index.md](./main/index.md) | main entry | content moved; target authoritative |
| [development/latest-dev-docs/root-plans/main/MERGED_PLAN.md](../../../development/latest-dev-docs/root-plans/main/MERGED_PLAN.md) | [docs/development/root-plans/main/MERGED_PLAN.md](./main/MERGED_PLAN.md) | merged program plan | content moved; target authoritative |

## Compatibility Entries

| Source path | Readable compatibility entry | Target role | Authority status |
|---|---|---|---|
| [development/latest-dev-docs/root-plans/F_PLAN/index.md](../../../development/latest-dev-docs/root-plans/F_PLAN/index.md) | [development/latest-dev-docs/root-plans/F_PLAN/index.md](../../../development/latest-dev-docs/root-plans/F_PLAN/index.md) | explicit plan index shim | content shim; source authoritative |
| [development/latest-dev-docs/root-plans/main](../../../development/latest-dev-docs/root-plans/main) | [development/latest-dev-docs/root-plans/main/index.md](../../../development/latest-dev-docs/root-plans/main/index.md) | moved-file compatibility shim | target authoritative; source shim retained |

## Compatibility Rule

The moved target files are authoritative for this root-plans main batch. The old latest-dev-docs files remain as compatibility shims until shared navigation fully switches to `docs/development`. The explicit `F_PLAN` index remains source-authoritative because it is still a separate shim-only planning entry.
