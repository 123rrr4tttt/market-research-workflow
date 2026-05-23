# Wave30 Crawler Manage I18N Slice

日期：2026-05-23

状态：`partial` / `retained_partial` / `wave30_verified`

## 结论

Wave30 将 `CrawlerManagePage` 的业务文案迁入 i18n catalog，并新增 focused slice checker；该 slice 已封住，但 `2026-03-15-frontend-three-layer-rewrite` 仍不迁档。

原因是三层重写的目录级 blocker 不是单页文案，而是全局 business-string/page-shell/AppShell 迁移。当前 `check:business-string-audit` 仍报告 1724 个 broader gaps，所以继续保留 `partial`。

## 仓内已封证据

- `main/frontend-modern/src/pages/CrawlerManagePage.tsx` 改为使用 catalog-backed `t(...)` 文案。
- `main/frontend-modern/src/app/platform/i18n/catalog.ts` 新增 `crawlerManagePage` namespace。
- `main/frontend-modern/scripts/check_crawler_manage_i18n_slice.mjs` 固化本 slice 的 no-inline-business-string gate。

## 仍需封口条件

- `frontend_business_string_audit_global_gaps_not_zero`
- `remaining_page_shell_migration_not_zero`
- `app_shell_compat_layer_not_retired`

## 验证命令

```bash
node main/frontend-modern/scripts/check_crawler_manage_i18n_slice.mjs
npm --prefix main/frontend-modern run check:business-string-audit
```
