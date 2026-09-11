import { useEffect, useRef, useState, type FormEvent } from 'react'
import { extractGraph, uploadDocument } from '../api/client'
import { useAsyncAction } from '../hooks/useAsyncAction'

const TEXT_PREVIEW_EXTENSIONS = ['.md', '.markdown', '.txt', '.json', '.csv']
const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/jpg']
const TEXT_PREVIEW_MAX_CHARS = 2000

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function isTextPreviewable(file: File): boolean {
  const lower = file.name.toLowerCase()
  return TEXT_PREVIEW_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

/** Client-side preview of the file the user just selected/uploaded — no
 * server round-trip needed, since the browser already holds the bytes.
 * Images render directly; PDFs use the browser's native PDF viewer via
 * an <iframe>; text-like files are read and shown as plain text (capped,
 * so a large file doesn't freeze the UI); everything else supported by
 * the backend (falls back to filename/type/size only). */
function FilePreview({ file }: { file: File }) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null)
  const [textPreview, setTextPreview] = useState<string | null>(null)
  const [textTruncated, setTextTruncated] = useState(false)

  useEffect(() => {
    if (IMAGE_TYPES.includes(file.type) || file.type === 'application/pdf') {
      const url = URL.createObjectURL(file)
      setObjectUrl(url)
      return () => URL.revokeObjectURL(url)
    }

    setObjectUrl(null)
    if (isTextPreviewable(file)) {
      let cancelled = false
      file.text().then((content) => {
        if (cancelled) return
        setTextTruncated(content.length > TEXT_PREVIEW_MAX_CHARS)
        setTextPreview(content.slice(0, TEXT_PREVIEW_MAX_CHARS))
      })
      return () => {
        cancelled = true
      }
    }
    return undefined
  }, [file])

  if (IMAGE_TYPES.includes(file.type) && objectUrl) {
    return (
      <img
        src={objectUrl}
        alt={`Preview of uploaded file ${file.name}`}
        className="file-preview-image"
      />
    )
  }

  if (file.type === 'application/pdf' && objectUrl) {
    return (
      <iframe
        src={objectUrl}
        title={`Preview of uploaded PDF ${file.name}`}
        className="file-preview-pdf"
      />
    )
  }

  if (textPreview !== null) {
    return (
      <div className="file-preview-text-wrap">
        <pre className="file-preview-text">{textPreview}</pre>
        {textTruncated && <p className="status-text">Preview truncated — showing the first {TEXT_PREVIEW_MAX_CHARS} characters.</p>}
      </div>
    )
  }

  return <p className="status-text">No preview available for this file type.</p>
}

export function UploadView() {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [graphStatus, setGraphStatus] = useState<string | null>(null)
  const upload = useAsyncAction((signal, file: File) => uploadDocument(file, signal))

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const file = fileInputRef.current?.files?.[0]
    if (!file) return
    setGraphStatus(null)
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
    <section id="upload" aria-labelledby="upload-heading" className="page-section">
      <h2 id="upload-heading">Upload</h2>
      <p className="section-description">
        Upload architecture documents or diagrams that ArchLens can use as evidence when
        answering review questions.
      </p>
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
            onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
            required
          />
        </div>
        <button type="submit" className="btn" disabled={upload.loading}>
          {upload.loading ? 'Uploading…' : 'Upload'}
        </button>
        {upload.loading && (
          <button
            type="button"
            className="btn btn-secondary"
            style={{ marginInlineStart: '0.5rem' }}
            onClick={upload.cancel}
          >
            Cancel
          </button>
        )}
      </form>

      {selectedFile && (
        <div className="card">
          <h3>File preview</h3>
          <dl className="meta-list">
            <div>
              <dt>Filename</dt>
              <dd>{selectedFile.name}</dd>
            </div>
            <div>
              <dt>Type</dt>
              <dd>{selectedFile.type || 'unknown'}</dd>
            </div>
            <div>
              <dt>Size</dt>
              <dd>{formatBytes(selectedFile.size)}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd>
                {upload.loading
                  ? 'Uploading…'
                  : upload.data?.original_filename === selectedFile.name
                    ? upload.data.status
                    : 'Not yet uploaded'}
              </dd>
            </div>
          </dl>
          <FilePreview
            file={selectedFile}
            key={`${selectedFile.name}-${selectedFile.size}-${selectedFile.lastModified}`}
          />
        </div>
      )}

      <div aria-live="polite">
        {upload.error && <p className="error-banner">{upload.error}</p>}
        {upload.data && (
          <div className="card">
            <h3>Upload result</h3>
            {upload.data.status === 'ingested' ? (
              <p className="success-banner">
                <strong>{upload.data.original_filename}</strong> was uploaded and indexed
                successfully — it's now searchable as evidence.
              </p>
            ) : (
              <p>
                <strong>{upload.data.original_filename}</strong> — status: {upload.data.status}
              </p>
            )}
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
