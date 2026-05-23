# Wave31 Frontend I18N Concentrated Slices

日期：2026-05-23

状态：`partial` / `retained_partial` / `wave31_verified`

## 结论

Wave31 按封口优先波次集中处理 frontend three-layer 的最大 i18n blocker，但不迁出 `CURRENT_DEV`。

本轮把 global business-string audit 的 remaining migration gaps 从 Wave30 的 `1724` 降到 `1080`，并保持 `npm --prefix main/frontend-modern run build` 通过。剩余 gap 仍属于仓内全量迁移范围，不是外部阻塞，也不能标成 retired。

## 已落地切片

| Page | Wave30/baseline gaps | Wave31 gaps | Result |
|---|---:|---:|---|
| `IngestPage.tsx` | 97 | 0 | page-level audit gap 清零 |
| `OpsPage.tsx` | 179 | 47 | 主要 shell/status/action 文案已进 catalog |
| `WritingWorkbenchPage.tsx` | 171 | 58 | toolbar / panel / writeback / quick-action 文案已进 catalog |
| `LlmDesignerPage.tsx` | 230 | 65 | visible shell/sidebar/canvas/runtime/result 文案已进 catalog |
| `AgentChatPage.tsx` | 220 | 141 | runtime/workbench/task/source/approval/artifact 文案已进 catalog |
| `GraphPage.tsx` | 476 | 418 | loading/error/toolbar/view/color/filter 文案已进 catalog |

## 仍需封口条件

- `GraphPage.tsx` 仍是最大单页 blocker：`418` gaps。
- `ResourcePage.tsx` 仍有 `95` gaps。
- `SettingsPage.tsx` 仍有 `62` gaps。
- shared/kernel surfaces 仍有跨层文案 gaps，不能只按单页切片归档。

## 验证命令

```bash
npm --prefix main/frontend-modern run check:business-string-audit
npm --prefix main/frontend-modern run build
npm --prefix main/frontend-modern run check:graph-page-i18n-slice
npm --prefix main/frontend-modern run check:agent-chat-i18n-slice
npm --prefix main/frontend-modern run check:llm-designer-page-i18n-slice
npm --prefix main/frontend-modern run check:ops-page-i18n-slice
npm --prefix main/frontend-modern run check:writing-workbench-contract
```
