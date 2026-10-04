const CONTROL_PANEL_MIN_WIDTH = 280
const CONTROL_PANEL_MAX_WIDTH = 720
const FLOATING_PANEL_MIN_HEIGHT = 120
const FLOATING_PANEL_MAX_HEIGHT = 920
export const NODE_SIZE_MIN_APPROX = 0.2
const NODE_BASE_SIZE_MULTIPLIER = 4

export function clampControlPanelWidth(value: number, viewportWidth: number) {
  const viewportBound = Math.max(CONTROL_PANEL_MIN_WIDTH, viewportWidth - 28)
  const maxAllowed = Math.min(CONTROL_PANEL_MAX_WIDTH, viewportBound)
  return Math.max(CONTROL_PANEL_MIN_WIDTH, Math.min(maxAllowed, Math.round(value)))
}

export function clampFloatingPanelWidth(value: number, viewportWidth: number) {
  const maxAllowed = Math.max(40, viewportWidth - 28)
  return Math.max(16, Math.min(maxAllowed, Math.round(value)))
}

export function clampFloatingPanelHeight(value: number, viewportHeight: number) {
  const maxAllowed = Math.max(FLOATING_PANEL_MIN_HEIGHT, viewportHeight - 24)
  return Math.max(16, Math.min(Math.max(FLOATING_PANEL_MAX_HEIGHT, maxAllowed), Math.round(value)))
}

export function computeNodeVisualSize(
  centralScore: number,
  centralMinValue: number,
  centralRangeValue: number,
  neighborScore: number,
  neighborMinValue: number,
  neighborRangeValue: number,
  nodeScale: number,
  centralContrast: number,
  neighborContrast: number,
) {
  const centralNorm = Math.max(0, (centralScore - centralMinValue) / Math.max(1e-12, centralRangeValue))
  const neighborNorm = Math.max(0, (neighborScore - neighborMinValue) / Math.max(1e-12, neighborRangeValue))
  const scaleT = Math.max(0, nodeScale / 100)
  const centralStrength = Math.max(0, centralContrast / 100)
  const neighborStrength = Math.max(0, neighborContrast / 100)
  const minPx = NODE_SIZE_MIN_APPROX + scaleT * 4
  const maxPx = NODE_SIZE_MIN_APPROX + scaleT * 30
  const centralContrastExponent = 1 + centralStrength * 0.9
  const neighborContrastExponent = 1 + neighborStrength * 0.9
  const centralEnhanced = Math.pow(centralNorm, centralContrastExponent)
  const neighborEnhanced = Math.pow(neighborNorm, neighborContrastExponent)
  const blendedContribution = Math.max(0, (centralStrength * centralEnhanced + neighborStrength * neighborEnhanced) / 2)
  const size = (minPx + (maxPx - minPx) * blendedContribution) * NODE_BASE_SIZE_MULTIPLIER
  return Math.max(NODE_SIZE_MIN_APPROX, size)
}

export function percentile(values: number[], p: number) {
  if (!values.length) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const t = Math.max(0, Math.min(1, p))
  const idx = t * (sorted.length - 1)
  const lo = Math.floor(idx)
  const hi = Math.ceil(idx)
  const w = idx - lo
  return sorted[lo] * (1 - w) + sorted[hi] * w
}

export function normalizeMapValues(input: Map<string, number>) {
  const values = Array.from(input.values())
  const min = values.length ? Math.min(...values) : 0
  const max = values.length ? Math.max(...values) : 1
  const range = Math.max(max - min, 1e-12)
  const out = new Map<string, number>()
  input.forEach((value, key) => {
    out.set(key, Math.max(0, Math.min(1, (value - min) / range)))
  })
  return out
}
