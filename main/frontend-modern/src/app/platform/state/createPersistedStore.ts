import { useSyncExternalStore } from 'react'
import { getLocalString, setLocalString } from '../../../lib/localStore'

type StoreListener = () => void

type PersistedStoreOptions<T> = {
  storageKey: string
  defaultValue: T
  parse: (value: string) => T | null
}

export type PersistedStore<T> = {
  get: () => T
  set: (next: T) => void
  subscribe: (listener: StoreListener) => () => void
  useValue: () => T
}

export function createPersistedStore<T>(options: PersistedStoreOptions<T>): PersistedStore<T> {
  const listeners = new Set<StoreListener>()
  let state: T = readInitialState(options)

  const get = () => state

  const set = (next: T) => {
    if (Object.is(next, state)) return
    state = next
    setLocalString(options.storageKey, String(next))
    listeners.forEach((listener) => listener())
  }

  const subscribe = (listener: StoreListener) => {
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }

  const useValue = () => useSyncExternalStore(subscribe, get, get)

  return { get, set, subscribe, useValue }
}

function readInitialState<T>(options: PersistedStoreOptions<T>): T {
  const raw = getLocalString(options.storageKey, '')
  const parsed = options.parse(raw)
  if (parsed != null) return parsed
  return options.defaultValue
}
