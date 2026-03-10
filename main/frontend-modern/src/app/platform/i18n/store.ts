import { APP_STORAGE_KEYS } from '../storageKeys'
import { createPersistedStore } from '../state/createPersistedStore'
import { DEFAULT_APP_LOCALE, isAppLocale, type AppLocale } from './types'

const localeStore = createPersistedStore<AppLocale>({
  storageKey: APP_STORAGE_KEYS.locale,
  defaultValue: DEFAULT_APP_LOCALE,
  parse: (value) => (isAppLocale(value) ? value : null),
})

export function getAppLocale(): AppLocale {
  return localeStore.get()
}

export function setAppLocale(next: AppLocale) {
  localeStore.set(next)
}

export function subscribeAppLocale(listener: () => void) {
  return localeStore.subscribe(listener)
}

export function useAppLocale(): AppLocale {
  return localeStore.useValue()
}
