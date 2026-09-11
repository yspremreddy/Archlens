import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CitationList } from './CitationList'
import type { Citation } from '../api/types'

const citation: Citation = {
  document_id: 'doc-1',
  document_filename: 'payment-service.md',
  document_content_hash: 'a'.repeat(64),
  chunk_id: 'chunk-1',
  chunk_index: 0,
  chunk_content_hash: 'b'.repeat(64),
  start_offset: 0,
  end_offset: 100,
  modality: 'text',
  page_number: null,
  bbox: null,
}

describe('CitationList', () => {
  it('renders a message when there are no citations', () => {
    render(<CitationList citations={[]} />)
    expect(screen.getByText('No citations.')).toBeInTheDocument()
  })

  it('renders one entry per citation with filename and hashes', () => {
    render(<CitationList citations={[citation]} />)
    expect(screen.getByText('payment-service.md')).toBeInTheDocument()
    expect(screen.getByText(/chunk #0/)).toBeInTheDocument()
  })
})
