# Wave28 Docs Root Reviewer (2026-05-23)

## Result

- Decision: keep `2026-03-07-docs-root-restructuring` in `CURRENT_DEV`.
- Classification: `partial` / `retained_partial`, not `closed`, not `retired`, and not `external_blocked`.
- Reason: the remaining blocker state is still repo-local docs integration work. It is not an external runtime blocker and not obsolete work.

## Current Gate Evidence

Initial reviewer run, before concurrent Wave28 content-plan edits were visible in the worktree:

```text
python3 scripts/checkers/check_docs_root_content_plan.py
OK docs_root_content_plan=passed plans=2 entries=12 unsafe_moves=2
```

The user-requested manifest command path does not exist in the current tree:

```text
python3 scripts/checkers/check_docs_root_migration_manifest.py
/Library/Developer/CommandLineTools/usr/bin/python3: can't open file '/Users/wangyiliang/market-research-workflow/scripts/checkers/check_docs_root_migration_manifest.py': [Errno 2] No such file or directory
```

The actual manifest checker path is `scripts/check_docs_root_migration_manifest.py`:

```text
python3 scripts/check_docs_root_migration_manifest.py
OK docs_root_migration_manifest=passed manifests=2 entries=12
```

Final reviewer rerun against the current worktree:

```text
python3 scripts/checkers/check_docs_root_content_plan.py
OK docs_root_content_plan=passed plans=2 entries=12 unsafe_moves=1

python3 scripts/check_docs_root_migration_manifest.py
OK docs_root_migration_manifest=passed manifests=2 entries=12
```

## Remaining Unsafe Moves Review

The initial authoritative list was `remaining_unsafe_moves` in [docs/development/latest-dev-docs-content-plan.json](../../../../../docs/development/latest-dev-docs-content-plan.json). During this reviewer pass, the current worktree gained uncommitted Wave28 edits that reclassified `development-plans-current-dev-tree` out of `remaining_unsafe_moves` and into `supervisor_owned_active_surfaces`. This reviewer did not edit those plan files.

| Unsafe move | Current reviewer finding | Executable judgment |
|---|---|---|
| `development-plans-current-dev-tree` | Still real as a non-move active status surface. `development/latest-dev-docs/development-plans/CURRENT_DEV` remains the active status surface, still has `INDEX.md`, `STATUS_AUDIT_2026-04-07.md`, 12 topic directories plus `main/`, and is still referenced by the latest-dev-docs navigation and docs/development shim. The current worktree now treats this as `supervisor_owned_active_surface` instead of an unsafe broad content move. | Do not broad-move or archive docs-root. If the concurrent plan edit is accepted, no migration task remains for `CURRENT_DEV`; it remains source-authoritative by design until topic-level archive or retire decisions remove the active status role. |
| `development-plans-archive-closed-tree` | Still real as the only current `remaining_unsafe_moves` entry. `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED` has 31 archived topic directories. Current `docs/development/development-plans/main/index.md` still links directly back into `ARCHIVE_CLOSED`, and the content-plan still lacks a file-level classification batch for this archive root. | Do not broad-move. Next worker should classify archive files by role before any target-authoritative move under `docs/development`. |

## Close / Migrate Decision

- `ARCHIVE_CLOSED`: no. Closure would be false because the current worktree still reports `unsafe_moves=1` for live, repo-local docs migration work.
- `ARCHIVE_EXTERNAL_BLOCKED`: no. The blockers are not external services, production data, public replay, or human-only review; they are in-repo navigation/status/classification tasks.
- `ARCHIVE_RETIRED`: no. The docs-root restructuring remains the active migration plan for `docs/development` target roots.

## Risk

Moving this topic out of `CURRENT_DEV` now would reduce `partial` cosmetically while archive routing remains unresolved. The safer next Wave28 implementation split is:

1. `archive-closed-classification`: create a file-level role classification for `ARCHIVE_CLOSED` and migrate only verified development-plan archive files.
2. `current-dev-status-surface`: if the concurrent `supervisor_owned_active_surface` plan edit is accepted, keep `CURRENT_DEV` source-authoritative and make sure shared indexes describe it as an active status surface rather than a pending broad move.
