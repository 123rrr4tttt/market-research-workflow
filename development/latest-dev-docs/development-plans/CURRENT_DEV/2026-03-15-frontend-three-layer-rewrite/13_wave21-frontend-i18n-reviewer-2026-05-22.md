# Wave21 Frontend I18N Reviewer - Frontend Three-Layer Rewrite

Date: 2026-05-22

Scope: `main/frontend-modern` - whether this wave can be closed for migration under i18n + three-layer rewrite boundaries.

## 结论

推荐状态：**`retained_partial`**。

`check:process-page-i18n-slice` 通过，说明 `ProcessPage` 切片层面已迁移到 `MESSAGE_CATALOGS`；但全局三层重写仍未收口，仍保留半重构入口与未迁移业务文案，因此不建议 `closed`。

## 证据

1. Process 页 i18n 门禁通过
```bash
npm --prefix main/frontend-modern run -s check:process-page-i18n-slice
```
输出：
```json
{
  "status": "ok",
  "gate_type": "process_page_i18n_slice",
  "page": "src/pages/ProcessPage.tsx",
  "catalog_namespace": "processPage",
  "required_keys": 68,
  "retired_page_snippets": 35,
  "failures": []
}
```

2. `ProcessPage` 已无中文内联文案，i18n 键与 helper 使用完整（含 `useAppLocale`、`toLocaleString(locale)`、`formatTemplate(...)`）。
- `main/frontend-modern/src/pages/ProcessPage.tsx` key 与 i18n 调用路径在静态 grep 中已命中大量 `processPage.*` 文案；`rg -nP "[\\p{Han}]"` 对该文件无中文命中。

3. `three-layer rewrite` 的三层路由与 legacy 适配仍存在“半重构”行为
- `main/frontend-modern/src/app/kernel/routes.ts`：`resolveKernelRoute` 对 legacy hash 与未知路由路径有明确降级逻辑（`source: 'legacy'`、`source: 'unknown'`）。
- `main/frontend-modern/src/app/kernel/FrontendKernelApp.tsx:69`：`route.source === 'unknown'` 时回退到 `<AppShell />`。
- `main/frontend-modern/src/app/shell/AppShell.tsx:39`：通过 `resolveShellModeFromHash` 与 `window.location.hash` 驱动页面模块；`AppShell` 仍承载历史兼容/页面切换行为，非纯“compat adapter”。
- `main/frontend-modern/src/app/shell/AppShell.tsx:186`：调用 `renderKernelModuleContent(..., shellMode: 'legacy-shell')`，说明 kernel/page 混合仍是 active runtime path。
- `main/frontend-modern/src/app/shell/AppShell.tsx:393`：仍直接挂载 `FigmaSideNav`。

4. 全局业务文案迁移仍未完成（非门禁阻断，但决定迁档边界）
```bash
npm --prefix main/frontend-modern run -s check:business-string-audit
```
输出（核心字段）：
```json
{
  "status": "ok",
  "gate_type": "audit_readiness",
  "full_business_string_migration_complete": false,
  "modules": 31,
  "remaining_migration_gaps": {
    "total": 1936,
    "by_file": {
      "src/pages/ProcessPage.tsx": 115,
      "src/pages/OpsPage.tsx": 179,
      "src/app/kernel/AdminLayerShell.tsx": 34
    }
  }
}
```

`Wave12` evidence 也明确说明“full business-string migration remains open / AppShell retirement and page container/view splitting remain outside slice”。

## 剩余 blockers

- 全局迁档未闭口：`full_business_string_migration_complete: false` 且仍有 1936 项剩余可见文案。
- 兼容路径未下沉到单一 adapter：legacy 解析仍在核心路由链路中存在并可回退到 `AppShell`。
- `AppShell` 仍为非纯兼容层并承担 shell/导航相关逻辑（包含内联状态提示与交互分支）。
- 页面切片为独立收口，不等于三层重构收口：`ProcessPage` 本身闭合，但其他关键管理/可视化页仍未形成统一封口。

## 验证命令

按你的要求已执行：

```bash
npm --prefix main/frontend-modern run -s check:process-page-i18n-slice
npm --prefix main/frontend-modern run -s check:business-string-audit
npm --prefix main/frontend-modern run -s lint  # 未执行，本次仅执行 reviewer 要求门禁 + 依赖齐套时的验证命令
git diff --check
```

如果你后续要把该切片状态改为 `closed`，需先通过一次 `frontend-three-layer` 级别的兼容收口验证：
- `AppShell` 仅剩 compatibility adapter 职责，
- unknown/legacy 路径不再作为主渲染分发路径，
- 全局文案迁移回填到可验收阈值（`full_business_string_migration_complete: true`）。
