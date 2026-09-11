// User preferences persisted via Web Storage (localStorage). Small,
// synchronous, per-browser — appropriate for UI preferences, not for
// data that needs to survive across devices or be queried.

export type ThemePreference = 'light' | 'dark'

const THEME_KEY = 'archlens.theme'
const RETRIEVAL_MODE_KEY = 'archlens.retrievalMode'

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSet(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // storage unavailable (private mode, quota) — preference just won't persist
  }
}

export function getTheme(): ThemePreference {
  const stored = safeGet(THEME_KEY)
  return stored === 'dark' ? 'dark' : 'light'
}

export function setTheme(theme: ThemePreference): void {
  safeSet(THEME_KEY, theme)
}

export function getPreferredRetrievalMode(): string {
  return safeGet(RETRIEVAL_MODE_KEY) ?? 'hybrid'
}

export function setPreferredRetrievalMode(mode: string): void {
  safeSet(RETRIEVAL_MODE_KEY, mode)
}
