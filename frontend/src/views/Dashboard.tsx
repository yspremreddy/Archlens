import { useEffect, useState } from 'react'
import { getHealth, getStats } from '../api/client'
import type { StatsResponse } from '../api/types'
import { useAsyncAction } from '../hooks/useAsyncAction'
import { getRecentEntries, type CacheEntry } from '../storage/cache'

// Root-cause fix for the "signal is aborted without reason" message that
// used to appear even while the API/database were healthy: this section
// previously ran its own ad-hoc `fetch().then().catch()` in a `useEffect`
// with no StrictMode/abort awareness. In development, React 18 StrictMode
// intentionally mounts every component twice (mount → cleanup → mount)
// to surface exactly this class of bug. The first mount's cleanup called
// `controller.abort()` on a request that hadn't resolved yet; the browser
// then rejects that fetch with a DOMException named "AbortError" whose
// default message (per the WHATWG spec, when no explicit reason is
// passed to `abort()`) is literally "signal is aborted without reason".
// The old `.catch()` treated that abort exactly like a real network
// failure and stored it in `error` state — so the (successful) second
// mount's health check would resolve `health` correctly while the stale
// abort error from the first mount stayed on screen right next to it.
//
// `useAsyncAction` (used everywhere else in this app) already handles
// this correctly: it explicitly checks `err.name === 'AbortError'` and
// treats it as a no-op, never surfacing it as a user-facing error. Using
// it here too — instead of a second, ad-hoc fetch implementation — fixes
// the root cause (an aborted/superseded request being treated as a
// failure) rather than papering over the symptom (hiding the message).
export function Dashboard() {
  const health = useAsyncAction((signal) => getHealth(signal))
  const stats = useAsyncAction((signal) => getStats(signal))
  const [recent, setRecent] = useState<CacheEntry[]>([])

  useEffect(() => {
    health.run()
    stats.run()
    getRecentEntries(5).then(setRecent)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <section id="overview" aria-labelledby="overview-heading" className="page-section">
      <h2 id="overview-heading">Overview</h2>
      <p className="section-description">
        See the current status of ArchLens and get a quick summary of your architecture evidence
        and reviews.
      </p>

      <div className="card">
        <h3>Backend status</h3>
        {health.error && <p className="error-banner">{health.error}</p>}
        {!health.error && !health.data && <p className="status-text">Checking…</p>}
        {health.data && (
          <p>
            API: <strong>{health.data.status}</strong> · Database:{' '}
            <strong>{health.data.database ? 'connected' : 'unavailable'}</strong>
          </p>
        )}
      </div>

      <div className="card">
        <h3>Evidence &amp; review summary</h3>
        {stats.error && <p className="error-banner">{stats.error}</p>}
        <StatGrid stats={stats.data} loading={stats.loading} />
      </div>

      <div className="card">
        <h3>What ArchLens does</h3>
        <p>
          Upload architecture documents or diagrams, then ask review questions. ArchLens finds
          the most relevant evidence, checks the component relationships it knows about, and
          gives you a clear PASS / FAIL / UNKNOWN / CONFLICT result — with the exact source of
          every claim shown alongside it.
        </p>
        <p className="status-text">
          Follow the sections below in order: Upload a document, run a Review question, look at
          the Evidence behind it, explore the Graph of how things connect, then check Evaluation
          for measured accuracy.
        </p>
      </div>

      <div className="card">
        <h3>Recently viewed (cached locally in this browser)</h3>
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

function StatGrid({ stats, loading }: { stats: StatsResponse | null; loading: boolean }) {
  const rows: { label: string; value: number | null | undefined }[] = [
    { label: 'Documents', value: stats?.documents },
    { label: 'Indexed chunks', value: stats?.chunks },
    { label: 'Reviews', value: stats?.reviews },
    { label: 'Components', value: stats?.components },
    { label: 'Evaluations', value: stats?.evaluations },
  ]

  return (
    <dl className="stat-grid">
      {rows.map((row) => (
        <div className="stat-tile" key={row.label}>
          <dt>{row.label}</dt>
          <dd>{loading && !stats ? '…' : typeof row.value === 'number' ? row.value : '—'}</dd>
        </div>
      ))}
    </dl>
  )
}
