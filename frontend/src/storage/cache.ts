// Local caching of past search/answer/review results via raw IndexedDB
// (no wrapper library — CLAUDE.md rule 8, keep it simple/dependency-free).
// Purely a client-side convenience: lets a user revisit recent results
// offline or instantly, without re-querying the backend. Never treated
// as a source of truth — every cached row keeps the same citations the
// API returned, so provenance is preserved even when read from cache.

const DB_NAME = 'archlens-cache'
const DB_VERSION = 1
const STORE = 'queries'
const MAX_ENTRIES = 50

export interface CacheEntry {
  id: string // `${kind}:${query}`
  kind: 'search' | 'answer' | 'review'
  query: string
  result: unknown
  timestamp: number
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB unavailable'))
      return
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id' })
        store.createIndex('timestamp', 'timestamp')
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function cacheResult(entry: CacheEntry): Promise<void> {
  try {
    const db = await openDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).put(entry)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
    await pruneOldEntries(db)
    db.close()
  } catch {
    // best-effort cache; never block the UI on storage failures
  }
}

export async function getCachedResult(id: string): Promise<CacheEntry | undefined> {
  try {
    const db = await openDb()
    const result = await new Promise<CacheEntry | undefined>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const req = tx.objectStore(STORE).get(id)
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error)
    })
    db.close()
    return result
  } catch {
    return undefined
  }
}

export async function getRecentEntries(limit = 10): Promise<CacheEntry[]> {
  try {
    const db = await openDb()
    const entries = await new Promise<CacheEntry[]>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const req = tx.objectStore(STORE).index('timestamp').openCursor(null, 'prev')
      const out: CacheEntry[] = []
      req.onsuccess = () => {
        const cursor = req.result
        if (cursor && out.length < limit) {
          out.push(cursor.value as CacheEntry)
          cursor.continue()
        } else {
          resolve(out)
        }
      }
      req.onerror = () => reject(req.error)
    })
    db.close()
    return entries
  } catch {
    return []
  }
}

async function pruneOldEntries(db: IDBDatabase): Promise<void> {
  const tx = db.transaction(STORE, 'readwrite')
  const store = tx.objectStore(STORE)
  const countReq = store.count()
  await new Promise<void>((resolve) => {
    countReq.onsuccess = () => resolve()
    countReq.onerror = () => resolve()
  })
  if ((countReq.result ?? 0) <= MAX_ENTRIES) return
  const index = store.index('timestamp')
  const toDelete = countReq.result - MAX_ENTRIES
  let deleted = 0
  await new Promise<void>((resolve) => {
    const cursorReq = index.openCursor()
    cursorReq.onsuccess = () => {
      const cursor = cursorReq.result
      if (cursor && deleted < toDelete) {
        cursor.delete()
        deleted += 1
        cursor.continue()
      } else {
        resolve()
      }
    }
    cursorReq.onerror = () => resolve()
  })
}
