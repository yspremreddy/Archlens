import type { Citation } from '../api/types'

/** One piece of retrieved evidence, shown consistently everywhere a
 * citation appears (Review verdicts, Evidence search results). Shows the
 * actual chunk text — not just hashes — so a reader can judge the
 * evidence without leaving the page. */
export function EvidenceCard({
  citation,
  supportNote,
  score,
}: {
  citation: Citation
  supportNote?: string
  score?: number
}) {
  return (
    <li className="evidence-card">
      <div className="evidence-card-header">
        <strong>{citation.document_filename}</strong>
        <span className="status-text">
          chunk #{citation.chunk_index}
          {citation.modality !== 'text' ? ` · ${citation.modality}` : ''}
          {citation.page_number != null ? ` · page ${citation.page_number}` : ''}
        </span>
      </div>

      {citation.text ? (
        <p className="evidence-snippet">{citation.text}</p>
      ) : (
        <p className="status-text">No text preview available for this evidence.</p>
      )}

      {supportNote && <p className="evidence-support-note">{supportNote}</p>}
      {score != null && <p className="status-text">Relevance score: {score.toFixed(3)}</p>}

      <details className="evidence-hashes">
        <summary>Provenance (hashes)</summary>
        <dl className="meta-list">
          <div>
            <dt>Document hash</dt>
            <dd>
              <code>{citation.document_content_hash}</code>
            </dd>
          </div>
          <div>
            <dt>Chunk hash</dt>
            <dd>
              <code>{citation.chunk_content_hash}</code>
            </dd>
          </div>
        </dl>
      </details>
    </li>
  )
}
