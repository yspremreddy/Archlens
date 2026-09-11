// Mirrors app/retrieval/schemas.py, app/generation/schemas.py,
// app/policy/schemas.py, app/graph/schemas.py. Kept hand-in-sync with the
// backend Pydantic models — there is no paid/codegen tool wired up for
// this (CLAUDE.md rule 8: no new major frameworks), so a backend schema
// change must be mirrored here by hand.

export type RetrievalMode = 'hybrid' | 'lexical' | 'vector'
export type Verdict = 'PASS' | 'FAIL' | 'UNKNOWN' | 'CONFLICT'
export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type GraphDirection = 'downstream' | 'upstream' | 'both'

export interface SearchFiltersIn {
  document_id?: string | null
  filename_contains?: string | null
  uploaded_after?: string | null
  uploaded_before?: string | null
  modality?: string | null
}

export interface Citation {
  document_id: string
  document_filename: string
  document_content_hash: string
  chunk_id: string
  chunk_index: number
  chunk_content_hash: string
  start_offset: number | null
  end_offset: number | null
  modality: string
  page_number: number | null
  bbox: Record<string, number> | null
  text: string
}

export interface SearchResultItem {
  text: string
  citation: Citation
  score: number
  lexical_rank: number | null
  vector_rank: number | null
  retrieval_methods: string[]
}

export interface SearchResponse {
  query: string
  mode: RetrievalMode
  result_count: number
  results: SearchResultItem[]
}

export interface AnswerResponse {
  question: string
  answer: string
  mode: RetrievalMode
  llm_provider: string
  llm_model: string
  citations: Citation[]
  groundedness_score: number
  is_grounded: boolean
  is_abstention: boolean
  finding_id: string | null
  retrieved_count: number
}

export interface GraphHopOut {
  source: string
  target: string
  relationship_type: string
  citation: Citation | null
}

export interface GraphPathOut {
  components: string[]
  hops: GraphHopOut[]
}

export interface ReviewResponse {
  question: string
  verdict: Verdict
  severity: Severity
  confidence: number
  recommendation: string
  citations: Citation[]
  graph_paths: GraphPathOut[]
  agent_steps: number
  hit_step_bound: boolean
  finding_id: string
}

export interface GraphQueryResponse {
  component: string
  direction: GraphDirection
  max_hops: number
  component_found: boolean
  path_count: number
  paths: GraphPathOut[]
}

export interface DocumentUploadResponse {
  id: string
  status: string
  original_filename: string
  content_hash: string
  error_message: string | null
}

export interface HealthResponse {
  status: 'ok' | 'degraded'
  database: boolean
}

export interface GraphExtractResponse {
  document_id: string
  components_upserted: number
  relationships_upserted: number
  owner_linked: boolean
}

export interface StatsResponse {
  documents: number
  chunks: number
  reviews: number
  components: number
  evaluations: number | null
}
