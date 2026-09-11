import type { Citation, Verdict } from '../api/types'
import { EvidenceCard } from './EvidenceCard'

const VERDICT_SUPPORT_NOTES: Record<Verdict, string> = {
  PASS: 'Supports this control being met.',
  FAIL: 'Evidence ArchLens considered when identifying this gap.',
  CONFLICT: 'One of the conflicting statements found in your evidence.',
  UNKNOWN: 'Evidence considered, but it did not clearly confirm or deny this control.',
}

export function CitationList({ citations, verdict }: { citations: Citation[]; verdict?: Verdict }) {
  if (citations.length === 0) {
    return <p className="status-text">No citations.</p>
  }
  const supportNote = verdict ? VERDICT_SUPPORT_NOTES[verdict] : undefined
  return (
    <ul className="evidence-list" aria-label="Evidence citations">
      {citations.map((c, i) => (
        <EvidenceCard citation={c} supportNote={supportNote} key={`${c.chunk_id}-${i}`} />
      ))}
    </ul>
  )
}
