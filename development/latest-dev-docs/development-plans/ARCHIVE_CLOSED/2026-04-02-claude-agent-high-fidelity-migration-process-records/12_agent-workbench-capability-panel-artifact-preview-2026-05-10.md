# Agent Workbench Capability Panel And Artifact Preview

Date: 2026-05-10 PST
Source plan: `02_claude-code-level-agent-interaction-todo-2026-05-10.md`

## Scope Completed

This pass continues the P4 frontend workbench closure after the backend S-01 through S-10 replay gate turned green.

Implemented:

- Added a live capability panel in the right workbench, backed by `/agent-chat/capabilities`.
- Split capability display into read-only and governed groups so users can see which tools need approval.
- Added typed frontend API/types for `AgentChatCapabilitiesResult` and `AgentChatCapabilityItem`.
- Converted artifact listing into selectable artifact cards.
- Added an artifact preview panel that shows artifact identity, type/status, and a compact content/metadata preview.
- Verified desktop and mobile layout has no horizontal overflow and renders workbench/capabilities/artifacts/tool calls.

## Main Files

- `main/frontend-modern/src/pages/AgentChatPage.tsx`
- `main/frontend-modern/src/pages/agent-chat.css`
- `main/frontend-modern/src/lib/api.ts`
- `main/frontend-modern/src/lib/types.ts`

## Validation

Commands run:

```bash
cd main/frontend-modern
npm run build
```

Result: passed.

Headless Playwright smoke against `http://127.0.0.1:5173/#agent-chat.html`:

```json
{
  "desktop": {
    "hasWorkbench": true,
    "hasCapabilities": true,
    "hasArtifacts": true,
    "hasToolCalls": true,
    "bodyOverflowX": false,
    "overflowing": []
  },
  "mobile": {
    "bodyOverflowX": false,
    "hasCapabilities": true,
    "hasArtifacts": true,
    "hasWorkbench": true
  },
  "errors": []
}
```

Note: the in-app Browser plugin had no active browser pane during this verification, so the UI smoke used local headless Playwright.

## Mainline Satisfaction Update

- P4-05 is materially satisfied as an artifact preview panel inside the workbench.
- P4-08 is materially satisfied by the capability panel and read-only/governed grouping.
- P4-10 remains partial: the mobile layout is non-overflowing, but explicit tab switching between conversation/tools/artifacts is still not implemented.
