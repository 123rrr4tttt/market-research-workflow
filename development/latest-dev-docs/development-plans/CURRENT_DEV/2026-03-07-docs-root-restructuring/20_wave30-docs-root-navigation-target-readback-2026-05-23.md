# Wave30 Docs Root Navigation Target Readback

日期：2026-05-23

状态：`partial` / `retained_partial` / `wave30_verified`

## 结论

Wave30 关闭了 docs-root 目录自身的 target-root navigation 缺口，但不迁出 `CURRENT_DEV`。

`scripts/checkers/check_docs_root_navigation_drift.py` 现在区分 target-root 缺口与共享导航漂移：target-root `missing_refs=0`，说明本目录负责的 `docs/development` 与 `docs/architecture` 入口不再缺引用；共享 `README` / `MERGED_OVERVIEW` 仍有 `shared_missing_refs=14`，且还有 `decomposed_moves=1`，所以目录级封口条件未满足。

## 仓内已封证据

- `docs/development/README.md`、`docs/development/development-plans/README.md` 与 `docs/development/development-plans/main/index.md` 已接入 latest-dev-docs content plan 与 entry manifest。
- `docs/development/latest-dev-docs-content-plan.json` 与 `docs/development/latest-dev-docs-entry-manifest.json` 已补 readback marker。
- `scripts/checkers/check_docs_root_navigation_drift.py` 输出 target-root `missing_refs=0`，不再把共享漂移混入 docs-root target 缺口。

## 仍需封口条件

- `shared_navigation_missing_refs_not_zero`
- `merged_overview_shared_drift_not_zero`
- `decomposed_archive_move_queue_not_empty`

## 验证命令

```bash
python3 scripts/checkers/check_docs_root_navigation_drift.py
python3 scripts/checkers/check_docs_root_content_plan.py
python3 scripts/check_docs_root_migration_manifest.py
```
