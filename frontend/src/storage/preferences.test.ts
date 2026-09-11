import { beforeEach, describe, expect, it } from 'vitest'
import { getPreferredRetrievalMode, getTheme, setPreferredRetrievalMode, setTheme } from './preferences'

beforeEach(() => {
  window.localStorage.clear()
})

describe('preferences (Web Storage)', () => {
  it('defaults to light theme when nothing stored', () => {
    expect(getTheme()).toBe('light')
  })

  it('round-trips a theme preference', () => {
    setTheme('dark')
    expect(getTheme()).toBe('dark')
  })

  it('defaults retrieval mode to hybrid', () => {
    expect(getPreferredRetrievalMode()).toBe('hybrid')
  })

  it('round-trips a retrieval mode preference', () => {
    setPreferredRetrievalMode('lexical')
    expect(getPreferredRetrievalMode()).toBe('lexical')
  })
})
