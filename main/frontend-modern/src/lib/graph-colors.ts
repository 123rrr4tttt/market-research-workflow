export type PaletteKey = 'bcp_unified' | 'bupu_fine' | 'spectral_fine' | 'viridis_fine'

type PaletteSpec = {
  label: string
  anchors: string[]
  steps: number
}

type PaletteChannel = 'node' | 'edge' | 'chip'
type AssignLegendColorOptions = {
  rotation?: number
  spread?: number
  contrast?: number
  domainExpand?: number
}

const COLOR_THEME_SPECS: Record<PaletteKey, PaletteSpec> = {
  bcp_unified: {
    label: '蓝-青-紫（统一）',
    anchors: ['#0B3C8C', '#1F6FDB', '#28A9E0', '#5ED0E3', '#7D83E8', '#9A5EEB'],
    steps: 28,
  },
  bupu_fine: {
    label: 'BuPu（ColorBrewer）',
    anchors: ['#f7fcfd', '#bfd3e6', '#8c96c6', '#88419d', '#4d004b'],
    steps: 24,
  },
  spectral_fine: {
    label: '红橙黄蓝青绿（Spectral）',
    anchors: ['#9e0142', '#f46d43', '#ffffbf', '#66c2a5', '#3288bd', '#5e4fa2'],
    steps: 28,
  },
  viridis_fine: {
    label: 'Viridis（细分）',
    anchors: ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725'],
    steps: 24,
  },
}

function hexToRgb(hex: string) {
  const raw = String(hex || '').replace('#', '')
  return {
    r: parseInt(raw.slice(0, 2), 16) || 0,
    g: parseInt(raw.slice(2, 4), 16) || 0,
    b: parseInt(raw.slice(4, 6), 16) || 0,
  }
}

function rgbToHex(r: number, g: number, b: number) {
  return `#${Math.round(r).toString(16).padStart(2, '0')}${Math.round(g).toString(16).padStart(2, '0')}${Math.round(b).toString(16).padStart(2, '0')}`
}

function srgbToLinear(value: number) {
  const v = value / 255
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
}

function linearToSrgb(value: number) {
  const v = Math.max(0, Math.min(1, value))
  const mapped = v <= 0.0031308 ? 12.92 * v : 1.055 * (v ** (1 / 2.4)) - 0.055
  return Math.round(mapped * 255)
}

function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t
}

function interpolateHexLinearRgb(from: string, to: string, t: number) {
  const a = hexToRgb(from)
  const b = hexToRgb(to)
  const ar = srgbToLinear(a.r)
  const ag = srgbToLinear(a.g)
  const ab = srgbToLinear(a.b)
  const br = srgbToLinear(b.r)
  const bg = srgbToLinear(b.g)
  const bb = srgbToLinear(b.b)
  return rgbToHex(
    linearToSrgb(lerp(ar, br, t)),
    linearToSrgb(lerp(ag, bg, t)),
    linearToSrgb(lerp(ab, bb, t)),
  )
}

function interpolatePalette(anchors: string[], steps: number) {
  const normalized = anchors
    .map((x) => String(x || '').trim())
    .filter(Boolean)
  if (!normalized.length) return ['#7dd3fc']
  if (normalized.length === 1) return [normalized[0]]
  const size = Math.max(2, steps)
  const out: string[] = []
  for (let i = 0; i < size; i += 1) {
    const pos = i / (size - 1)
    const span = pos * (normalized.length - 1)
    const idx = Math.min(normalized.length - 2, Math.floor(span))
    const localT = span - idx
    out.push(interpolateHexLinearRgb(normalized[idx], normalized[idx + 1], localT))
  }
  return out
}

function colorAt(anchors: string[], tRaw: number) {
  const normalized = anchors
    .map((x) => String(x || '').trim())
    .filter(Boolean)
  if (!normalized.length) return '#7dd3fc'
  if (normalized.length === 1) return normalized[0]
  const t = Math.max(0, Math.min(1, tRaw))
  const span = t * (normalized.length - 1)
  const idx = Math.min(normalized.length - 2, Math.floor(span))
  const localT = span - idx
  return interpolateHexLinearRgb(normalized[idx], normalized[idx + 1], localT)
}

function gcd(a: number, b: number): number {
  let x = Math.abs(Math.trunc(a))
  let y = Math.abs(Math.trunc(b))
  while (y !== 0) {
    const t = x % y
    x = y
    y = t
  }
  return x || 1
}

function coprimeStep(n: number) {
  if (n <= 2) return 1
  let step = Math.max(1, Math.floor(n * 0.61803398875))
  while (gcd(step, n) !== 1) step += 1
  return step
}

function channelPhase(channel: PaletteChannel) {
  if (channel === 'node') return 0.09
  if (channel === 'edge') return 0.41
  return 0.71
}

function channelCurve(channel: PaletteChannel, t: number) {
  if (channel === 'edge') return Math.pow(t, 0.92)
  if (channel === 'chip') return Math.pow(t, 1.06)
  return t
}

export const GRAPH_COLOR_THEMES: Record<PaletteKey, { label: string; colors: string[]; anchors: string[] }> =
  Object.fromEntries(
    Object.entries(COLOR_THEME_SPECS).map(([key, spec]) => [
      key,
      {
        label: spec.label,
        colors: interpolatePalette(spec.anchors, spec.steps),
        anchors: [...spec.anchors],
      },
    ]),
  ) as Record<PaletteKey, { label: string; colors: string[]; anchors: string[] }>

export function assignLegendColors(
  keys: string[],
  paletteKey: PaletteKey,
  channel: PaletteChannel,
  options?: AssignLegendColorOptions,
): Record<string, string> {
  const uniqueKeys = Array.from(new Set(keys.map((x) => String(x || '')).filter(Boolean)))
  const out: Record<string, string> = {}
  if (!uniqueKeys.length) return out
  const theme = GRAPH_COLOR_THEMES[paletteKey] || GRAPH_COLOR_THEMES.bcp_unified
  const n = uniqueKeys.length
  const step = coprimeStep(n)
  const phase = channelPhase(channel)
  const rotation = Number.isFinite(options?.rotation) ? Number(options?.rotation) : 0
  const spreadRaw = Number.isFinite(options?.spread) ? Number(options?.spread) : 1
  const spread = Math.max(0.16, Math.min(2.4, spreadRaw))
  const contrastRaw = Number.isFinite(options?.contrast) ? Number(options?.contrast) : 0.5
  const contrast = Math.max(0, Math.min(1, contrastRaw))
  const domainExpandRaw = Number.isFinite(options?.domainExpand) ? Number(options?.domainExpand) : 0.5
  const domainExpand = Math.max(0, Math.min(1, domainExpandRaw))
  const domainWidth = Math.max(0.24, Math.min(1, 0.36 + domainExpand * 0.64))
  const domainStart = (phase + rotation - domainWidth / 2 + 1) % 1
  const contrastPow = 1.45 - contrast * 0.9
  uniqueKeys.forEach((key, index) => {
    const rank = n <= 1 ? 0 : (index * step) % n
    const base = n <= 1 ? 0.5 : rank / (n - 1)
    const centered = base * 2 - 1
    const contrasted = Math.sign(centered) * Math.pow(Math.abs(centered), contrastPow)
    const contrastBase = (contrasted + 1) / 2
    const scoped = (contrastBase - 0.5) * spread + 0.5
    const scopedClamped = Math.max(0, Math.min(1, scoped))
    const wrapped = (domainStart + scopedClamped * domainWidth) % 1
    out[key] = colorAt(theme.anchors, channelCurve(channel, wrapped))
  })
  return out
}
