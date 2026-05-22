# Graph Visual Evidence - Wave2 F (2026-05-22)

Scope: Wave2 subagent F, graph visual evidence only. This lane intentionally did not edit the GraphPage e2e spec owned by the parallel E lane.

## Result

Storybook build and a lightweight Playwright visual probe were run against existing GraphPage and graph-kit stories. The evidence package includes build logs, probe metrics, and screenshots for the mocked GraphPage canvas, GraphPage shell/template-builder path, graph-kit legend, graph-kit node card, graph-kit toolbar, and a force3d canvas probe.

One small story helper was adjusted: `ShellTemplateBuilder` now waits for the lazy kernel shell to render `编辑模式` before asserting. This removes the transient Storybook play error observed during the first visual probe and keeps the story aligned with the asynchronous shell render path.

## Verification

Commands run from `/Users/wangyiliang/market-research-workflow.worktrees/graph-visual-evidence`:

```bash
npm --prefix main/frontend-modern run storybook:build
python3 -m http.server 6206 --bind 127.0.0.1
node --input-type=module <playwright visual probe>
```

Validation status:

- `storybook:build`: passed. See `logs/storybook-build.log`.
- Playwright visual probe: completed against `http://127.0.0.1:6206/iframe.html`.
- 2D GraphPage story: captured one visible canvas at `1416x680`, `dataUrlLength=29718`.
- GraphPage shell template builder story: captured one visible canvas at `1156x680`, `dataUrlLength=28426`.
- force3d probe: after clicking `3D模式`, detected projection engine value `force3d`, one `.gv2-chart--force3d canvas`, and a `1416x678` canvas.

## Artifacts

| Artifact | Purpose |
| --- | --- |
| `logs/storybook-build.log` | Full Storybook production build log. |
| `logs/playwright-graph-visual-probe.log` | Browser console events captured during the visual probe. |
| `graph-visual-probe.json` | Structured story, canvas, force3d, and console metrics. |
| `screenshots/graphpage-container-default.png` | Mocked GraphPage market graph story. |
| `screenshots/graphpage-shell-template-builder.png` | Kernel shell path for graph template builder. |
| `screenshots/graphpage-3d-webgl-probe.png` | Force3d canvas probe after switching from 2D. |
| `screenshots/graphlegend-default.png` | graph-kit legend story. |
| `screenshots/graphnodecard-default.png` | graph-kit node-card story. |
| `screenshots/graphtoolbar-default.png` | graph-kit toolbar story. |

## Findings

- The Storybook production build includes GraphPage and `react-force-graph-3d` chunks and completes successfully.
- The existing mocked GraphPage story renders a non-empty 2D canvas and stable control panels.
- The force3d path can be reached from the Storybook iframe and renders a visible canvas under headless Chromium with SwiftShader flags.
- `window.__graph3dDebug` is not present in this production Storybook build because the debug hook is gated by `import.meta.env.DEV`; this evidence therefore proves canvas reachability/visibility, not dev-mode scene stats.
- Retained warnings in the visual probe are limited to a static-resource 404, upstream `THREE.Clock` deprecation warnings, and WebGL `ReadPixels` performance warnings.

## Remaining Risk

This lane does not close the full GraphPage runtime/e2e topic. It does not prove real backend data, rapid engine-switch stress, or the dev-only `window.__graph3dDebug.getVisibilityStats()` scene counters. Those should remain with the graph e2e/runtime validation lane.
