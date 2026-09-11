import { useState, type FormEvent } from 'react'
import { queryGraph } from '../api/client'
import type { GraphDirection } from '../api/types'
import { useAsyncAction } from '../hooks/useAsyncAction'
import { GraphPathView } from '../components/GraphPathView'
import { GraphCanvas } from '../components/GraphCanvas'

export function GraphView() {
  const [component, setComponent] = useState('')
  const [direction, setDirection] = useState<GraphDirection>('downstream')
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const action = useAsyncAction((signal, c: string, d: GraphDirection) => queryGraph(c, { direction: d }, signal))

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (!component.trim()) return
    setSelectedNode(null)
    await action.run(component, direction)
  }

  return (
    <section id="graph" aria-labelledby="graph-heading" className="page-section">
      <h2 id="graph-heading">Component Graph</h2>
      <p className="section-description">
        Explore how services, databases, and other architecture components are connected.
      </p>

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
        {action.data && (!action.data.component_found || action.data.path_count === 0) && (
          <div className="card">
            <p>No architecture relationships available yet.</p>
            <p className="status-text">
              "{action.data.component}" {action.data.component_found
                ? 'was found, but has no relationships to other components yet.'
                : "wasn't found in the graph."}{' '}
              Upload a document mentioning it and extract its relationships from the Upload
              section first.
            </p>
          </div>
        )}
        {action.data && action.data.component_found && action.data.path_count > 0 && (
          <div className="card">
            <p>
              {action.data.path_count} path(s) found for <strong>{action.data.component}</strong> (
              {action.data.direction})
              {selectedNode && (
                <>
                  {' '}
                  · selected: <strong>{selectedNode}</strong>
                </>
              )}
            </p>
            <GraphCanvas>
              <GraphPathView paths={action.data.paths} selectedNode={selectedNode} onSelectNode={setSelectedNode} />
            </GraphCanvas>
          </div>
        )}
        {!action.data && !action.error && (
          <p className="status-text">No architecture relationships available yet.</p>
        )}
      </div>
    </section>
  )
}
