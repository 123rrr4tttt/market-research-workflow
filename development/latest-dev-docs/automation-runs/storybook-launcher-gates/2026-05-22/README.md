# Storybook / Launcher Gates Evidence

> Date: 2026-05-22
> Branch: `codex/devdocs-storybook-launcher-gates`
> Worktree: `/Users/wangyiliang/market-research-workflow.worktrees/storybook-launcher-gates`

## Gate Summary

| Gate | Status | Evidence |
| --- | --- | --- |
| Storybook static build | `passed` | [logs/storybook-build.log](./logs/storybook-build.log) |
| Storybook MCP config | `passed` | [logs/storybook-mcp-config.log](./logs/storybook-mcp-config.log) |
| Storybook MCP endpoint | `passed` | [logs/storybook-mcp-curl.log](./logs/storybook-mcp-curl.log) |
| Launcher-first dry-run gate | `passed` | [launcher-first-dry-run.json](./launcher-first-dry-run.json), [logs/launcher-first-dry-run.log](./logs/launcher-first-dry-run.log) |
| Launcher docker status | `passed` | [logs/launcher-docker-status.log](./logs/launcher-docker-status.log) |
| Changed Markdown link check | `passed` | [logs/markdown-link-check.log](./logs/markdown-link-check.log) |
| Git diff whitespace check | `passed` | [logs/git-diff-check.log](./logs/git-diff-check.log) |

## Commands Run

```bash
npm --prefix main/frontend-modern run storybook:build
```

```bash
npm --prefix main/frontend-modern run storybook -- --ci
curl -i -sS --max-time 5 http://127.0.0.1:6006/mcp
curl -I -sS --max-time 5 http://127.0.0.1:6006/mcp
```

```bash
scripts/gates/run_launcher_first_dry_run_gate.sh \
  "$PWD" \
  "$PWD/development/latest-dev-docs/automation-runs/storybook-launcher-gates/2026-05-22/launcher-first-dry-run.json"
```

```bash
bash scripts/platform-macos.sh docker-status
```

```bash
git diff --check
```

## Notes

- `storybook:build` completed successfully and wrote `main/frontend-modern/storybook-static`; that output is generated and remains untracked.
- The MCP endpoint GET probe behaved as a long-lived request and timed out after 5 seconds with no bytes. The HEAD probe returned `405 Method Not Allowed` with `allow: GET, POST, DELETE, OPTIONS`, proving the addon endpoint is mounted.
- `bash scripts/platform-macos.sh docker-status` is read-only and returned running app services: `backend`, `celery-worker`, `db`, `es`, `frontend-modern`, and `redis`.
- `scripts/build-macos-launcher.sh` was not run in this gate because the current script deletes and rewrites both `tools/macos/Market Research Workflow.app` and `$HOME/Desktop/Market Research Workflow.app`. The added dry-run gate validates the launcher-first routing and macOS build entry without mutating those app bundles.
