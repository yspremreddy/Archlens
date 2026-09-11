import type { GraphPathOut } from '../api/types'

// Hand-rolled inline-SVG rendering of graph paths returned by /review or
// /graph/query — no charting/graph-viz library (CLAUDE.md rule 8). Each
// path is drawn as a horizontal chain of component nodes connected by
// labeled, directional edges. Nodes are clickable (node selection) —
// panning/zooming is handled by the wrapping <GraphCanvas> in
// views/GraphView.tsx, not here, so this component still renders the
// exact same data/shapes it always did.
export function GraphPathView({
  paths,
  selectedNode,
  onSelectNode,
}: {
  paths: GraphPathOut[]
  selectedNode?: string | null
  onSelectNode?: (name: string) => void
}) {
  if (paths.length === 0) {
    return <p className="status-text">No graph paths returned.</p>
  }

  return (
    <div>
      {paths.map((path, pi) => {
        const nodeWidth = 150
        const nodeGap = 60
        const width = path.components.length * nodeWidth + (path.components.length - 1) * nodeGap
        const height = 90
        return (
          <figure key={pi} style={{ margin: '0 0 1.5rem' }}>
            <svg
              className="graph-svg"
              viewBox={`0 0 ${Math.max(width, 200)} ${height}`}
              role="img"
              aria-labelledby={`graph-path-${pi}-title`}
            >
              <title id={`graph-path-${pi}-title`}>
                Graph path: {path.components.join(' → ')}
              </title>
              {path.hops.map((hop, hi) => {
                const x1 = hi * (nodeWidth + nodeGap) + nodeWidth
                const x2 = (hi + 1) * (nodeWidth + nodeGap)
                const y = height / 2
                return (
                  <g key={hi}>
                    <line x1={x1} y1={y} x2={x2 - 4} y2={y} stroke="currentColor" strokeWidth={2} markerEnd="url(#arrow)" />
                    <text x={(x1 + x2) / 2} y={y - 8} textAnchor="middle" fontSize="11">
                      {hop.relationship_type}
                    </text>
                  </g>
                )
              })}
              <defs>
                <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto">
                  <path d="M0,0 L8,4 L0,8 z" fill="currentColor" />
                </marker>
              </defs>
              {path.components.map((name, ni) => {
                const x = ni * (nodeWidth + nodeGap)
                const y = height / 2 - 18
                const isSelected = selectedNode === name
                return (
                  <g
                    key={ni}
                    onClick={() => onSelectNode?.(name)}
                    style={{ cursor: onSelectNode ? 'pointer' : 'default' }}
                    tabIndex={onSelectNode ? 0 : undefined}
                    role={onSelectNode ? 'button' : undefined}
                    aria-pressed={onSelectNode ? isSelected : undefined}
                    onKeyDown={(e) => {
                      if (onSelectNode && (e.key === 'Enter' || e.key === ' ')) {
                        e.preventDefault()
                        onSelectNode(name)
                      }
                    }}
                  >
                    <rect
                      x={x}
                      y={y}
                      width={nodeWidth}
                      height={36}
                      rx={6}
                      fill={isSelected ? 'var(--accent)' : 'var(--surface)'}
                      stroke="currentColor"
                      strokeWidth={isSelected ? 2 : 1}
                    />
                    <text
                      x={x + nodeWidth / 2}
                      y={y + 22}
                      textAnchor="middle"
                      fontSize="12"
                      fill={isSelected ? 'var(--accent-contrast)' : 'currentColor'}
                    >
                      {name}
                    </text>
                  </g>
                )
              })}
            </svg>
            <figcaption className="status-text">{path.components.join(' → ')}</figcaption>
          </figure>
        )
      })}
    </div>
  )
}
