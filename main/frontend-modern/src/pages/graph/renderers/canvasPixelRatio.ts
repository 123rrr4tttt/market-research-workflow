/**
 * Canvas density for the ECharts graph surfaces.
 *
 * A fixed 1x ratio keeps painting cheap but leaves the canvas upscaled by the
 * browser, which reads as blurry text and hairlines on HiDPI displays. Use the
 * display's own ratio instead, capped so very high densities do not multiply
 * paint cost without a visible gain.
 */
export const GRAPH_CANVAS_MAX_PIXEL_RATIO = 2

export function graphCanvasPixelRatio(): number {
  const ratio = typeof window === 'undefined' ? 1 : Number(window.devicePixelRatio || 1)
  if (!Number.isFinite(ratio) || ratio <= 0) return 1
  return Math.min(ratio, GRAPH_CANVAS_MAX_PIXEL_RATIO)
}
