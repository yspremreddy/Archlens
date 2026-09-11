import { useState, type FormEvent } from 'react'
import { answer as answerApi, search as searchApi } from '../api/client'
import type { RetrievalMode } from '../api/types'
import { useAsyncAction } from '../hooks/useAsyncAction'
import { CitationList } from '../components/CitationList'
import { EvidenceCard } from '../components/EvidenceCard'
import { getPreferredRetrievalMode, setPreferredRetrievalMode } from '../storage/preferences'
import { cacheResult } from '../storage/cache'

export function SearchView() {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<RetrievalMode>(() => getPreferredRetrievalMode() as RetrievalMode)
  const search = useAsyncAction((signal, q: string, m: RetrievalMode) => searchApi(q, { mode: m }, signal))
  const answer = useAsyncAction((signal, q: string, m: RetrievalMode) => answerApi(q, { mode: m }, signal))

  function handleModeChange(next: RetrievalMode) {
    setMode(next)
    setPreferredRetrievalMode(next)
  }

  async function handleSearch(e: FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    const result = await search.run(query, mode)
    if (result) cacheResult({ id: `search:${query}`, kind: 'search', query, result, timestamp: Date.now() })
  }

  async function handleAsk() {
    if (!query.trim()) return
    const result = await answer.run(query, mode)
    if (result) cacheResult({ id: `answer:${query}`, kind: 'answer', query, result, timestamp: Date.now() })
  }

  return (
    <section id="evidence" aria-labelledby="evidence-heading" className="page-section">
      <h2 id="evidence-heading">Evidence Search</h2>
      <p className="section-description">
        Search your architecture documents to find evidence related to a component, requirement,
        or question.
      </p>

      <form onSubmit={handleSearch} className="card">
        <div className="field">
          <label htmlFor="search-query">Search query</label>
          <input
            id="search-query"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. what happens to billing postal codes?"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="mode-select">Retrieval mode</label>
          <select id="mode-select" value={mode} onChange={(e) => handleModeChange(e.target.value as RetrievalMode)}>
            <option value="hybrid">hybrid (lexical + vector)</option>
            <option value="lexical">lexical only</option>
            <option value="vector">vector only</option>
          </select>
        </div>
        <button type="submit" className="btn" disabled={search.loading}>
          {search.loading ? 'Searching…' : 'Search'}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ marginInlineStart: '0.5rem' }}
          onClick={handleAsk}
          disabled={answer.loading}
        >
          {answer.loading ? 'Asking…' : 'Ask (generate answer)'}
        </button>
      </form>

      <div aria-live="polite">
        {search.error && <p className="error-banner">{search.error}</p>}
        {answer.error && <p className="error-banner">{answer.error}</p>}

        {answer.data && (
          <div className="card">
            <h3>Generated answer</h3>
            <p>{answer.data.answer}</p>
            <p className="status-text">
              provider: {answer.data.llm_provider}/{answer.data.llm_model} · grounded:{' '}
              {answer.data.is_grounded ? 'yes' : 'no'} ({(answer.data.groundedness_score * 100).toFixed(0)}%)
              {answer.data.is_abstention ? ' · abstained' : ''}
            </p>
            <h4>Citations</h4>
            <CitationList citations={answer.data.citations} />
          </div>
        )}

        {search.data && (
          <div className="card">
            <h3>
              Results ({search.data.result_count}) — mode: {search.data.mode}
            </h3>
            {search.data.result_count === 0 ? (
              <p className="status-text">No matching evidence found for this query.</p>
            ) : (
              <ul className="evidence-list">
                {search.data.results.map((r, i) => (
                  <EvidenceCard citation={r.citation} score={r.score} key={`${r.citation.chunk_id}-${i}`} />
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
