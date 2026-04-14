import { APP_STORAGE_KEYS } from '../storageKeys'
import { createPersistedStore } from '../state/createPersistedStore'
import { DEFAULT_APP_THEME, isAppTheme, type AppTheme } from './types'

const themeStore = createPersistedStore<AppTheme>({
  storageKey: APP_STORAGE_KEYS.theme,
  defaultValue: DEFAULT_APP_THEME,
  parse: (value) => (isAppTheme(value) ? value : null),
})

export function getAppTheme(): AppTheme {
  return themeStore.get()
}

export function setAppTheme(next: AppTheme) {
  themeStore.set(next)
}

export function subscribeAppTheme(listener: () => void) {
  return themeStore.subscribe(listener)
}

export function useAppTheme(): AppTheme {
  return themeStore.useValue()
}
