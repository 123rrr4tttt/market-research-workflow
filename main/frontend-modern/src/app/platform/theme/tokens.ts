import type { AppTheme, ThemeTokens } from './types'

export const THEME_TOKENS: Record<AppTheme, ThemeTokens> = {
  light: {
    background: { app: '#f4f6f8', subtle: '#eef2f7' },
    surface: { base: '#ffffff', raised: '#f9fbff' },
    border: { default: '#d9e1ec', strong: '#b9c5d5' },
    text: { primary: '#102135', secondary: '#49617a' },
    accent: { primary: '#2457ff', contrast: '#ffffff' },
    status: { success: '#1f9d55', warning: '#c97700', danger: '#c53f3f' },
    interactive: { hover: '#eaf0ff', focus: '#9cb6ff', active: '#dce6ff' },
  },
  dark: {
    background: { app: '#121820', subtle: '#1a2230' },
    surface: { base: '#1d2636', raised: '#243149' },
    border: { default: '#31415c', strong: '#476186' },
    text: { primary: '#f0f5ff', secondary: '#b7c8e5' },
    accent: { primary: '#5e8eff', contrast: '#08172f' },
    status: { success: '#22b573', warning: '#e6a400', danger: '#ef5757' },
    interactive: { hover: '#2b3850', focus: '#8aa9ff', active: '#35496a' },
  },
  brand: {
    background: { app: '#f5f8ff', subtle: '#e9efff' },
    surface: { base: '#ffffff', raised: '#f6f9ff' },
    border: { default: '#cfdcf8', strong: '#a9c0ef' },
    text: { primary: '#102b53', secondary: '#395a8f' },
    accent: { primary: '#0b66ff', contrast: '#ffffff' },
    status: { success: '#1f9d55', warning: '#c97700', danger: '#c53f3f' },
    interactive: { hover: '#e7f0ff', focus: '#8bb5ff', active: '#d6e6ff' },
  },
}

export function applyThemeTokens(theme: AppTheme, target: HTMLElement = document.documentElement) {
  const tokens = THEME_TOKENS[theme]
  target.setAttribute('data-app-theme', theme)
  applyTokenGroup(target, 'background', tokens.background)
  applyTokenGroup(target, 'surface', tokens.surface)
  applyTokenGroup(target, 'border', tokens.border)
  applyTokenGroup(target, 'text', tokens.text)
  applyTokenGroup(target, 'accent', tokens.accent)
  applyTokenGroup(target, 'status', tokens.status)
  applyTokenGroup(target, 'interactive', tokens.interactive)
}

function applyTokenGroup(target: HTMLElement, group: string, values: Record<string, string>) {
  for (const [token, value] of Object.entries(values)) {
    target.style.setProperty(`--app-${group}-${toKebabCase(token)}`, value)
  }
}

function toKebabCase(value: string): string {
  return value.replace(/[A-Z]/g, (char) => `-${char.toLowerCase()}`)
}

