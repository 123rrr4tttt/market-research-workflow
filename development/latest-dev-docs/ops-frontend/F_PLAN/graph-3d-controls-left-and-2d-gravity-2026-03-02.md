# Graph 3D Controls Left + 2D Gravity (2026-03-02)

## Scope
- Move graph control panel to the left side in 3D mode.
- Keep 2D mode behavior unchanged (panel remains on the right).
- Add `2D 全局引力` slider and map it to ECharts force `gravity`.

## Code Changes
- `main/frontend-modern/src/pages/GraphPage.tsx`
  - Add conditional class `is-left-3d` for control panel in `projection3d`.
  - Add `gravityPercent` into `visualDraft` / `visualApplied` state.
  - Add `2D全局引力` slider in `视图调节`.
  - Apply gravity in force config:
    - `gravity = clamp(0, 0.6, 0.1 * gravityPercent / 100)`.
- `main/frontend-modern/src/index.css`
  - Add `.gv2-floating-controls.is-left-3d` to anchor panel left.
  - Move resizer handle to the right edge in `.is-left-3d`.
  - Add mobile override for `.is-left-3d`.

## Validation
- Build command: `cd main/frontend-modern && npm run -s build`
- Result: success.

## Notes
- This is a layout/physics parameter change only; no API or backend changes.
