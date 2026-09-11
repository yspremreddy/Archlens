import type {
  AnswerResponse,
  DocumentUploadResponse,
  GraphExtractResponse,
  GraphQueryResponse,
  HealthResponse,
  ReviewResponse,
  SearchFiltersIn,
  SearchResponse,
  RetrievalMode,
  GraphDirection,
} from './types'

// Resolved at build time (Vite `import.meta.env`); defaults to the
// FastAPI dev server started via `uvicorn app.main:app` on 8000.
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { signal?: AbortSignal } = {},
): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: options.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err
    throw new ApiError(0, 'Network error: could not reach the ArchLens API. Is the backend running?')
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(response.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return response.json() as Promise<T>
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request('/health', { signal })
}

export function uploadDocument(file: File, signal?: AbortSignal): Promise<DocumentUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  return request('/documents', { method: 'POST', body: form, signal })
}

export function extractGraph(documentId: string, signal?: AbortSignal): Promise<GraphExtractResponse> {
  return request(`/documents/${documentId}/graph`, { method: 'POST', signal })
}

export function search(
  query: string,
  opts: { top_k?: number; mode?: RetrievalMode; filters?: SearchFiltersIn } = {},
  signal?: AbortSignal,
): Promise<SearchResponse> {
  return request('/search', {
    method: 'POST',
    body: JSON.stringify({ query, top_k: opts.top_k ?? 10, mode: opts.mode ?? 'hybrid', filters: opts.filters }),
    signal,
  })
}

export function answer(
  question: string,
  opts: { top_k?: number; mode?: RetrievalMode; filters?: SearchFiltersIn } = {},
  signal?: AbortSignal,
): Promise<AnswerResponse> {
  return request('/answer', {
    method: 'POST',
    body: JSON.stringify({ question, top_k: opts.top_k ?? 5, mode: opts.mode ?? 'hybrid', filters: opts.filters }),
    signal,
  })
}

export function review(
  question: string,
  opts: { top_k?: number; max_hops?: number; max_steps?: number; filters?: SearchFiltersIn } = {},
  signal?: AbortSignal,
): Promise<ReviewResponse> {
  return request('/review', {
    method: 'POST',
    body: JSON.stringify({
      question,
      top_k: opts.top_k ?? 8,
      max_hops: opts.max_hops ?? 3,
      max_steps: opts.max_steps ?? 4,
      filters: opts.filters,
    }),
    signal,
  })
}

export function queryGraph(
  component: string,
  opts: { direction?: GraphDirection; max_hops?: number } = {},
  signal?: AbortSignal,
): Promise<GraphQueryResponse> {
  return request('/graph/query', {
    method: 'POST',
    body: JSON.stringify({ component, direction: opts.direction ?? 'downstream', max_hops: opts.max_hops ?? 3 }),
    signal,
  })
}
