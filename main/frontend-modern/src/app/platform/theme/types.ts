export const APP_THEMES = ['light', 'dark', 'brand'] as const
export type AppTheme = (typeof APP_THEMES)[number]

export const DEFAULT_APP_THEME: AppTheme = 'dark'

export function isAppTheme(value: string): value is AppTheme {
  return APP_THEMES.includes(value as AppTheme)
}

export type ThemeTokens = {
  background: {
    app: string
    subtle: string
  }
  surface: {
    base: string
    raised: string
  }
  border: {
    default: string
    strong: string
  }
  text: {
    primary: string
    secondary: string
  }
  accent: {
    primary: string
    contrast: string
  }
  status: {
    success: string
    warning: string
    danger: string
  }
  interactive: {
    hover: string
    focus: string
    active: string
  }
}

