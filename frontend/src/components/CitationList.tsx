import type { Citation } from '../api/types'

export function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return <p className="status-text">No citations.</p>
  }
  return (
    <ul className="citation-list" aria-label="Evidence citations">
      {citations.map((c, i) => (
        <li className="citation-item" key={`${c.chunk_id}-${i}`}>
          <div>
            <strong>{c.document_filename}</strong>{' '}
            <span className="status-text">
              (chunk #{c.chunk_index}
              {c.modality !== 'text' ? `, ${c.modality}` : ''}
              {c.page_number != null ? `, page ${c.page_number}` : ''})
            </span>
          </div>
          <div>
            <code>doc hash: {c.document_content_hash.slice(0, 16)}…</code>
          </div>
          <div>
            <code>chunk hash: {c.chunk_content_hash.slice(0, 16)}…</code>
          </div>
        </li>
      ))}
    </ul>
  )
}
