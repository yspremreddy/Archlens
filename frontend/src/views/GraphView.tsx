import { useState, type FormEvent } from 'react'
import { queryGraph } from '../api/client'
import type { GraphDirection } from '../api/types'
import { useAsyncAction } from '../hooks/useAsyncAction'
import { GraphPathView } from '../components/GraphPathView'

export function GraphView() {
  const [component, setComponent] = useState('')
  const [direction, setDirection] = useState<GraphDirection>('downstream')
  const action = useAsyncAction((signal, c: string, d: GraphDirection) => queryGraph(c, { direction: d }, signal))

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!component.trim()) return
    await action.run(component, direction)
  }

  return (
    <section aria-labelledby="graph-heading">
      <h2 id="graph-heading">Component graph</h2>
      <p className="status-text">Explore relationships extracted from uploaded architecture docs and diagrams.</p>

      <form onSubmit={handleSubmit} className="card">
        <div className="field">
          <label htmlFor="component-name">Component name</label>
          <input
            id="component-name"
            type="text"
            value={component}
            onChange={(e) => setComponent(e.target.value)}
            placeholder="e.g. event-collector"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="direction-select">Direction</label>
          <select id="direction-select" value={direction} onChange={(e) => setDirection(e.target.value as GraphDirection)}>
            <option value="downstream">downstream</option>
            <option value="upstream">upstream</option>
            <option value="both">both</option>
          </select>
        </div>
        <button type="submit" className="btn" disabled={action.loading}>
          {action.loading ? 'Querying…' : 'Query graph'}
        </button>
      </form>

      <div aria-live="polite">
        {action.error && <p className="error-banner">{action.error}</p>}
        {action.data && (
          <div className="card">
            {!action.data.component_found && <p>Component not found in the graph.</p>}
            {action.data.component_found && (
              <>
                <p>
                  {action.data.path_count} path(s) found for <strong>{action.data.component}</strong> (
                  {action.data.direction})
                </p>
                <GraphPathView paths={action.data.paths} />
              </>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
