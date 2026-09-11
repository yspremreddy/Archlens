import { useState, type FormEvent } from 'react'
import { review as reviewApi } from '../api/client'
import { useAsyncAction } from '../hooks/useAsyncAction'
import { CitationList } from '../components/CitationList'
import { GraphPathView } from '../components/GraphPathView'
import { cacheResult } from '../storage/cache'

export function ReviewView() {
  const [question, setQuestion] = useState('')
  const action = useAsyncAction((signal, q: string) => reviewApi(q, {}, signal))

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!question.trim()) return
    const result = await action.run(question)
    if (result) {
      cacheResult({
        id: `review:${question}`,
        kind: 'review',
        query: question,
        result,
        timestamp: Date.now(),
      })
    }
  }

  return (
    <section aria-labelledby="review-heading">
      <h2 id="review-heading">Architecture review</h2>
      <p className="status-text">
        Ask a compliance/risk question. ArchLens searches evidence, optionally traverses the
        component graph, and returns a verdict with citations.
      </p>

      <form onSubmit={handleSubmit} className="card">
        <div className="field">
          <label htmlFor="review-question">Question</label>
          <input
            id="review-question"
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. does payment-api have rate limiting on the checkout endpoint?"
            required
          />
        </div>
        <button type="submit" className="btn" disabled={action.loading}>
          {action.loading ? 'Reviewing…' : 'Run review'}
        </button>
        {action.loading && (
          <button type="button" className="btn btn-secondary" style={{ marginInlineStart: '0.5rem' }} onClick={action.cancel}>
            Cancel
          </button>
        )}
      </form>

      <div aria-live="polite">
        {action.error && <p className="error-banner">{action.error}</p>}
        {action.data && (
          <div className="card">
            <h3>
              Verdict: <span className={`verdict-badge verdict-${action.data.verdict}`}>{action.data.verdict}</span>
              <span className="severity-badge">severity: {action.data.severity}</span>
            </h3>
            <p>Confidence: {(action.data.confidence * 100).toFixed(0)}%</p>
            <p>{action.data.recommendation}</p>
            <p className="status-text">
              Agent steps: {action.data.agent_steps}
              {action.data.hit_step_bound ? ' (hit step bound)' : ''}
            </p>

            <h4>Evidence</h4>
            <CitationList citations={action.data.citations} />

            {action.data.graph_paths.length > 0 && (
              <>
                <h4>Graph evidence</h4>
                <GraphPathView paths={action.data.graph_paths} />
              </>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
