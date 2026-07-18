import { useRef, useState, type DragEvent } from 'react'
import { ingestApi } from '../api/endpoints'
import { extractErrorMessage } from '../api/client'

interface Props {
  onClose: () => void
}

const ALLOWED = ['.pdf', '.docx', '.txt']

export default function UploadDialog({ onClose }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const [status, setStatus] = useState<{ ok: boolean; message: string } | null>(null)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function pickFile(f: File | null | undefined) {
    if (!f) return
    const ext = f.name.slice(f.name.lastIndexOf('.')).toLowerCase()
    if (!ALLOWED.includes(ext)) {
      setStatus({ ok: false, message: `Unsupported file type: ${ext}. Allowed: ${ALLOWED.join(', ')}` })
      return
    }
    setStatus(null)
    setFile(f)
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    pickFile(e.dataTransfer.files?.[0])
  }

  async function handleUpload() {
    if (!file) return
    setUploading(true)
    setProgress(0)
    setStatus(null)
    try {
      const res = await ingestApi.upload(file, setProgress)
      setStatus({ ok: true, message: `${res.file_name}: ${res.total_chunks} chunks indexed.` })
      setFile(null)
    } catch (err) {
      setStatus({ ok: false, message: extractErrorMessage(err) })
    } finally {
      setUploading(false)
      setProgress(null)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md rounded-2xl border border-neutral-800 bg-neutral-900 p-6 shadow-2xl"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-neutral-100">Upload document</h2>
          <button
            onClick={onClose}
            className="rounded-md px-2 py-1 text-neutral-500 transition hover:bg-neutral-800 hover:text-neutral-300"
          >
            ✕
          </button>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${
            dragOver ? 'border-violet-500 bg-violet-950/20' : 'border-neutral-800 hover:border-neutral-700'
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept={ALLOWED.join(',')}
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0])}
          />
          <span className="text-2xl">📄</span>
          {file ? (
            <p className="text-sm font-medium text-neutral-200">{file.name}</p>
          ) : (
            <>
              <p className="text-sm font-medium text-neutral-300">Drop a file here or click to browse</p>
              <p className="text-xs text-neutral-600">PDF, DOCX, or TXT — up to 20MB</p>
            </>
          )}
        </div>

        {progress !== null && (
          <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-neutral-800">
            <div
              className="h-full rounded-full bg-violet-500 transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}

        {status && (
          <div
            className={`mt-4 rounded-lg border px-3 py-2 text-sm ${
              status.ok
                ? 'border-emerald-900/50 bg-emerald-950/40 text-emerald-400'
                : 'border-red-900/50 bg-red-950/50 text-red-400'
            }`}
          >
            {status.message}
          </div>
        )}

        <button
          onClick={handleUpload}
          disabled={!file || uploading}
          className="mt-4 w-full rounded-lg bg-violet-600 px-3 py-2.5 text-sm font-medium text-white transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {uploading ? 'Uploading…' : 'Upload & index'}
        </button>
      </div>
    </div>
  )
}
