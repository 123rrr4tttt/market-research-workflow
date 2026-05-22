# LLM Designer UI Replica Brief (From xyflow React Examples)

## Source Scope
- Source root: `external_refs/reference_pool/xyflow/examples/react`
- Focus: reusable UI layout structure, interaction patterns, and style primitives for a modern node-graph workflow UI
- Output intent: provide a direct replica brief for designer + frontend implementation

## 1) Layout Partitions

### A. Global App Shell (Top Nav + Content Canvas)
- Structure:
  - Top header with brand link + example selector
  - Main content area rendered by route outlet
- Replica notes:
  - Keep header as fixed-height top band with subtle bottom border
  - Use full-height root (`html/body/#root: 100%`) and flex column app shell
- Example paths:
  - `external_refs/reference_pool/xyflow/examples/react/src/App/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/App/header.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/index.css`

### B. Split Workspace (Canvas + Sidebar Inspector/Palette)
- Structure:
  - Mobile: vertical stack (canvas then sidebar)
  - Desktop (`>=768px`): horizontal split, sidebar fixed width (20%, max 180-250px)
- Replica notes:
  - Sidebar contains description + controls/data list
  - Canvas wrapper should be `flex-grow: 1` and always full height
- Example paths:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/DragNDrop/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/DragNDrop/Sidebar.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/DragNDrop/dnd.module.css`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Provider/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Provider/Sidebar.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Provider/provider.module.css`

### C. In-Canvas Floating Control Zones
- Structure:
  - Absolute floating control groups inside flow viewport (`top-left`, `top-right`, `bottom-right`)
  - Built-in `Panel` plus custom absolute containers both used
- Replica notes:
  - Reserve z-layer for utility controls (`z-index: 4`)
  - Use compact horizontal button clusters and toggle groups
- Example paths:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Interaction/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/SaveRestore/Controls.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/SaveRestore/save.module.css`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Layouting/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/UseOnSelectionChange/index.tsx`

### D. Multi-Canvas Comparison Layout
- Structure:
  - 2+ canvases in a single row, equal width, vertical divider/border
- Replica notes:
  - Useful for A/B graph state comparison and synchronized interaction demos
- Example paths:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Backgrounds/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Backgrounds/style.module.css`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/MultiFlows/multiflows.module.css`

### E. Overlay Diagnostics Layer
- Structure:
  - DevTools toggle buttons in panel
  - Non-interactive annotation overlays (`pointer-events: none`) for node metrics / change log
- Replica notes:
  - Keep debug overlay visually separated from primary canvas interactions
- Example paths:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/DevTools/DevTools/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/DevTools/DevTools/NodeInspector.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/DevTools/DevTools/ChangeLogger.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/DevTools/DevTools/style.css`

## 2) Interaction Checklist (Replicable)

- Node palette drag-and-drop to create node on canvas coordinate transform
  - Paths:
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/DragNDrop/index.tsx`
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/DragNDrop/Sidebar.tsx`
- Connect/reconnect edges with validation feedback (valid/invalid state)
  - Paths:
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/Validation/index.tsx`
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/Validation/validation.module.css`
- Runtime behavior toggles (draggable/connectable/selectable/pan/zoom mode)
  - Paths:
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/Interaction/index.tsx`
- Save/restore flow state and add node from utility controls
  - Paths:
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/SaveRestore/Controls.tsx`
- Context/selection instrumentation (selection logger, dev overlays)
  - Paths:
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/UseOnSelectionChange/index.tsx`
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/DevTools/DevTools/index.tsx`
- Layout actions (vertical/horizontal auto-layout, fit-view, marker switch)
  - Paths:
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/Layouting/index.tsx`
- Minimap interactions (pannable/zoomable/click callbacks)
  - Paths:
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/InteractiveMinimap/index.tsx`
- Node/edge toolbars for contextual action exposure
  - Paths:
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/NodeToolbar/index.tsx`
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/EdgeToolbar/index.tsx`
- Mobile/touch handle optimization with enlarged hit target + animated connect state
  - Paths:
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/TouchDevice/index.tsx`
    - `external_refs/reference_pool/xyflow/examples/react/src/examples/TouchDevice/touch-device.css`

## 3) Style Token Suggestions

Use these tokens as an implementation baseline (extracting common values/patterns from examples):

```css
:root {
  --ui-font-family-base: sans-serif;
  --ui-font-family-mono: monospace, sans-serif;

  --ui-color-text-primary: #111;
  --ui-color-text-secondary: #555;
  --ui-color-surface-base: #fff;
  --ui-color-surface-subtle: #fcfcfc;
  --ui-color-surface-muted: #f4f4f4;
  --ui-color-border-subtle: #eee;
  --ui-color-border-default: #ddd;
  --ui-color-border-strong: #333;
  --ui-color-accent: #ee3a73;
  --ui-color-success: #55dd99;
  --ui-color-danger: #ff6060;

  --ui-radius-sm: 4px;
  --ui-radius-md: 5px;
  --ui-radius-lg: 10px;
  --ui-space-1: 5px;
  --ui-space-2: 10px;
  --ui-space-3: 15px;
  --ui-space-4: 20px;

  --ui-font-size-xs: 10px;
  --ui-font-size-sm: 11px;
  --ui-font-size-md: 12px;
  --ui-z-overlay: 4;
  --ui-z-toast: 999;

  --ui-duration-fast: 0.3s;
  --ui-duration-pulse: 1600ms;
}
```

Token source examples:
- Borders/background/spacing/fonts:
  - `external_refs/reference_pool/xyflow/examples/react/src/index.css`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/DragNDrop/dnd.module.css`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Provider/provider.module.css`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/DevTools/DevTools/style.css`
- State colors and connection feedback:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Validation/validation.module.css`
- Motion and animated affordance:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/TouchDevice/touch-device.css`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Edges/CustomEdge3.css`
- Overlay elevation and transition:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/CancelConnection/Timer.module.css`

## 4) Example File Path Index (Quick Mapping)

- App shell and routing:
  - `external_refs/reference_pool/xyflow/examples/react/src/App/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/App/header.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/index.css`
- Split workspace:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/DragNDrop/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Provider/index.tsx`
- Floating panel controls:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Interaction/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Layouting/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/SaveRestore/Controls.tsx`
- Toolbars and minimap:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/NodeToolbar/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/EdgeToolbar/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/InteractiveMinimap/index.tsx`
- Debug and overlays:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/DevTools/DevTools/index.tsx`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/CancelConnection/Timer.module.css`
- Visual state and motion:
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Validation/validation.module.css`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/TouchDevice/touch-device.css`
  - `external_refs/reference_pool/xyflow/examples/react/src/examples/Edges/CustomEdge3.css`
