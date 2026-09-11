import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ReviewView } from './ReviewView'
import type { ReviewResponse } from '../api/types'

const mockReviewResponse: ReviewResponse = {
  question: 'does payment-api have rate limiting?',
  verdict: 'FAIL',
  severity: 'high',
  confidence: 0.8,
  recommendation: 'Add rate limiting to the checkout endpoint.',
  citations: [
    {
      document_id: 'doc-1',
      document_filename: 'payment-service.md',
      document_content_hash: 'a'.repeat(64),
      chunk_id: 'chunk-1',
      chunk_index: 0,
      chunk_content_hash: 'b'.repeat(64),
      start_offset: 0,
      end_offset: 50,
      modality: 'text',
      page_number: null,
      bbox: null,
      text: 'payment-api currently has no documented rate limiting on the checkout endpoint.',
    },
  ],
  graph_paths: [],
  agent_steps: 2,
  hit_step_bound: false,
  finding_id: 'finding-1',
}

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      json: async () => mockReviewResponse,
    })) as unknown as typeof fetch,
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ReviewView', () => {
  it('submits a question and renders the verdict and citations', async () => {
    const user = userEvent.setup()
    render(<ReviewView />)

    await user.type(screen.getByLabelText('Question'), 'does payment-api have rate limiting?')
    await user.click(screen.getByRole('button', { name: /run review/i }))

    await waitFor(() => expect(screen.getByText('FAIL')).toBeInTheDocument())
    expect(screen.getByText('payment-service.md')).toBeInTheDocument()
    expect(screen.getByText(/Add rate limiting/)).toBeInTheDocument()
  })
})
