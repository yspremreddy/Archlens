import 'fake-indexeddb/auto'
import { beforeEach, describe, expect, it } from 'vitest'
import { cacheResult, getCachedResult, getRecentEntries } from './cache'

beforeEach(async () => {
  indexedDB = new IDBFactory()
})

describe('cache (IndexedDB)', () => {
  it('stores and retrieves an entry by id', async () => {
    await cacheResult({ id: 'search:foo', kind: 'search', query: 'foo', result: { hit: true }, timestamp: Date.now() })
    const entry = await getCachedResult('search:foo')
    expect(entry?.query).toBe('foo')
    expect(entry?.result).toEqual({ hit: true })
  })

  it('lists recent entries newest-first', async () => {
    await cacheResult({ id: 'a', kind: 'search', query: 'a', result: {}, timestamp: 1 })
    await cacheResult({ id: 'b', kind: 'search', query: 'b', result: {}, timestamp: 2 })
    const recent = await getRecentEntries(10)
    expect(recent[0].id).toBe('b')
    expect(recent[1].id).toBe('a')
  })
})
