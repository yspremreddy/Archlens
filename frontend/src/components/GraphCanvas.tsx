import { useRef, useState, type PointerEvent, type ReactNode, type WheelEvent } from 'react'

const MIN_ZOOM = 0.4
const MAX_ZOOM = 3
const ZOOM_STEP = 0.2

/** Pan/zoom viewport around whatever graph content is passed as
 * children (the actual paths/nodes/edges are still rendered exactly as
 * before by <GraphPathView> — this only adds the ability to move around
 * a large graph, it does not touch how the graph itself is drawn). */
export function GraphCanvas({ children }: { children: ReactNode }) {
  const [zoom, setZoom] = useState(1)
  const [pan, setPan] = useState({ x: 0, y: 0 })
  const dragState = useRef<{ startX: number; startY: number; panX: number; panY: number } | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  function clampZoom(z: number) {
    return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, z))
  }

  function handleWheel(e: WheelEvent<HTMLDivElement>) {
    e.preventDefault()
    setZoom((z) => clampZoom(z - Math.sign(e.deltaY) * ZOOM_STEP))
  }

  function handlePointerDown(e: PointerEvent<HTMLDivElement>) {
    dragState.current = { startX: e.clientX, startY: e.clientY, panX: pan.x, panY: pan.y }
    setIsDragging(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }

  function handlePointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!dragState.current) return
    const dx = e.clientX - dragState.current.startX
    const dy = e.clientY - dragState.current.startY
    setPan({ x: dragState.current.panX + dx, y: dragState.current.panY + dy })
  }

  function handlePointerUp() {
    dragState.current = null
    setIsDragging(false)
  }

  function reset() {
    setZoom(1)
    setPan({ x: 0, y: 0 })
  }

  return (
    <div className="graph-canvas-wrap">
      <div className="graph-canvas-controls">
        <button type="button" className="btn btn-secondary" onClick={() => setZoom((z) => clampZoom(z - ZOOM_STEP))} aria-label="Zoom out">
          −
        </button>
        <button type="button" className="btn btn-secondary" onClick={() => setZoom((z) => clampZoom(z + ZOOM_STEP))} aria-label="Zoom in">
          +
        </button>
        <button type="button" className="btn btn-secondary" onClick={reset}>
          Reset view
        </button>
        <span className="status-text">{Math.round(zoom * 100)}% · drag to pan, scroll to zoom</span>
      </div>
      <div
        className="graph-canvas-viewport"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
        style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
      >
        <div
          className="graph-canvas-content"
          style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})` }}
        >
          {children}
        </div>
      </div>
    </div>
  )
}
