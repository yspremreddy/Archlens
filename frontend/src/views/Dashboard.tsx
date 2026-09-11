import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'
import type { HealthResponse } from '../api/types'
import { getRecentEntries, type CacheEntry } from '../storage/cache'

export function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [recent, setRecent] = useState<CacheEntry[]>([])

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal)
      .then(setHealth)
      .catch((err) => setHealthError(err instanceof Error ? err.message : 'Health check failed'))
    getRecentEntries(5).then(setRecent)
    return () => controller.abort()
  }, [])

  return (
    <section aria-labelledby="dashboard-heading">
      <h2 id="dashboard-heading">Dashboard</h2>

      <div className="card">
        <h3>Backend status</h3>
        {healthError && <p className="error-banner">{healthError}</p>}
        {!healthError && !health && <p className="status-text">Checking…</p>}
        {health && (
          <p>
            API: <strong>{health.status}</strong> · Database:{' '}
            <strong>{health.database ? 'connected' : 'unavailable'}</strong>
          </p>
        )}
      </div>

      <div className="card">
        <h3>What ArchLens does</h3>
        <p>
          Upload architecture documents or diagrams, then ask review questions. ArchLens
          retrieves relevant evidence (hybrid lexical + vector search, reranked), optionally
          traverses a component relationship graph, and produces a PASS / FAIL / UNKNOWN /
          CONFLICT finding — every claim traceable back to a specific document chunk.
        </p>
        <p>Use the tabs above: Upload a document, run a Review question, browse Search results, inspect the Graph, or view measured Evaluation results.</p>
      </div>

      <div className="card">
        <h3>Recently viewed (cached locally)</h3>
        {recent.length === 0 && <p className="status-text">Nothing cached yet in this browser.</p>}
        {recent.length > 0 && (
          <ul className="result-list">
            {recent.map((entry) => (
              <li key={entry.id}>
                <strong>{entry.kind}</strong>: {entry.query}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}
