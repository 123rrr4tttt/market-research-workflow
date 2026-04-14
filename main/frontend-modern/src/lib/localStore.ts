export function getLocalString(key: string, fallback = '') {
  try {
    const value = window.localStorage.getItem(key)
    return value == null ? fallback : value
  } catch {
    return fallback
  }
}

export function setLocalString(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // ignore quota/security errors
  }
}

export function removeLocal(key: string) {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // ignore quota/security errors
  }
}

export function getLocalJson<T>(key: string, fallback: T): T {
  const raw = getLocalString(key, '')
  if (!raw) return fallback
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

export function setLocalJson<T>(key: string, value: T) {
  try {
    setLocalString(key, JSON.stringify(value))
  } catch {
    // ignore serialization/storage errors
  }
}
