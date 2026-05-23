# Wave31 Docs Root Shared Navigation Sync

日期：2026-05-23

状态：`clear_closed` / `wave31_verified`

## 结论

Wave31 已关闭 docs-root 的 shared navigation reference drift，并在 supervisor integration 中执行完整 `ARCHIVE_CLOSED` moved-file batch；本目录不再作为 `CURRENT_DEV` partial 计数项保留。

`scripts/checkers/check_docs_root_navigation_drift.py --require-clean --verbose` 当前读数为 target-root `missing_refs=0`、shared navigation `shared_missing_refs=0`、`unsafe_moves=0`、`decomposed_moves=0`。Wave31 将 `docs/development/development-plans/archive-closed-file-classification-2026-05-23.json` 中的 195 个 `ARCHIVE_CLOSED` source 文件全部生成到 `docs/development/development-plans/ARCHIVE_CLOSED`，并把旧 `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED` 路径转换为 compatibility shims。

## 仓内已封证据

- `development/latest-dev-docs/README.md` 补齐 Wave28 docs-root active-surface/reviewer/classification anchors。
- `development/latest-dev-docs/MERGED_OVERVIEW.md` 补齐同一批 Wave28 anchors。
- `development/latest-dev-docs/development-plans/INDEX.md` 补齐同一批 Wave28 anchors。
- `development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md` 补齐 Wave27/Wave28 docs-root anchors。
- `docs/development/latest-dev-docs-content-plan.json` 将 `development-plans-archive-closed-tree` 从 decomposed queue 转为 `development-plans-archive-closed-wave31-batch`。
- `docs/development/latest-dev-docs-entry-manifest.json` 记录同一批 `moved_file_batch`，`entries=13`。
- `docs/development/development-plans/README.md` 列出 195 个 content moved 文件及其旧 compatibility paths。

## 封口读数

```text
OK docs_root_content_plan=passed plans=2 entries=13 unsafe_moves=0
OK docs_root_migration_manifest=passed manifests=2 entries=13
OK docs_root_navigation_drift=audit status=clean surfaces=3 anchors=10 missing_refs=0 shared_surfaces=4 shared_missing_refs=0 unsafe_moves=0 decomposed_moves=0
```

## 验证命令

```bash
python3 scripts/checkers/check_docs_root_navigation_drift.py
python3 scripts/checkers/check_docs_root_navigation_drift.py --require-clean --verbose
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_docs_root_migration_manifest.py
python3 scripts/check_latest_dev_docs_structure.py --link-path development/latest-dev-docs/README.md --link-path development/latest-dev-docs/MERGED_OVERVIEW.md --link-path development/latest-dev-docs/development-plans/INDEX.md --link-path development/latest-dev-docs/development-plans/CURRENT_DEV/INDEX.md
```
