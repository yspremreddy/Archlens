import { useRef, useState, type FormEvent } from 'react'
import { extractGraph, uploadDocument } from '../api/client'
import { useAsyncAction } from '../hooks/useAsyncAction'

export function UploadView() {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [graphStatus, setGraphStatus] = useState<string | null>(null)
  const upload = useAsyncAction((signal, file: File) => uploadDocument(file, signal))

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const file = fileInputRef.current?.files?.[0]
    if (!file) return
    await upload.run(file)
  }

  async function handleExtractGraph(documentId: string) {
    setGraphStatus('Extracting…')
    try {
      const result = await extractGraph(documentId)
      setGraphStatus(
        `Extracted ${result.components_upserted} component(s), ${result.relationships_upserted} relationship(s).`,
      )
    } catch (err) {
      setGraphStatus(err instanceof Error ? err.message : 'Graph extraction failed')
    }
  }

  return (
    <section aria-labelledby="upload-heading">
      <h2 id="upload-heading">Upload an artifact</h2>
      <p className="status-text">
        Accepts architecture docs (.md, .markdown, .txt) or diagrams (.png, .jpg, .jpeg, .pdf).
      </p>

      <form onSubmit={handleSubmit} className="card">
        <div className="field">
          <label htmlFor="file-input">Document or diagram file</label>
          <input
            id="file-input"
            type="file"
            ref={fileInputRef}
            accept=".md,.markdown,.txt,.png,.jpg,.jpeg,.pdf"
            onChange={(e) => setSelectedName(e.target.files?.[0]?.name ?? null)}
            required
          />
        </div>
        <button type="submit" className="btn" disabled={upload.loading}>
          {upload.loading ? 'Uploading…' : 'Upload'}
        </button>
        {upload.loading && (
          <button type="button" className="btn btn-secondary" style={{ marginInlineStart: '0.5rem' }} onClick={upload.cancel}>
            Cancel
          </button>
        )}
        <p aria-live="polite" className="status-text">
          {selectedName ? `Selected: ${selectedName}` : ''}
        </p>
      </form>

      <div aria-live="polite">
        {upload.error && <p className="error-banner">{upload.error}</p>}
        {upload.data && (
          <div className="card">
            <h3>Upload result</h3>
            <p>
              <strong>{upload.data.original_filename}</strong> — status: {upload.data.status}
            </p>
            {upload.data.error_message && <p className="error-banner">{upload.data.error_message}</p>}
            <p className="status-text">
              content hash: <code>{upload.data.content_hash}</code>
            </p>
            {upload.data.status === 'ingested' && (
              <>
                <button className="btn btn-secondary" onClick={() => handleExtractGraph(upload.data!.id)}>
                  Extract graph relationships
                </button>
                {graphStatus && <p role="status">{graphStatus}</p>}
              </>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
