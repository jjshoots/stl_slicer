import { useId, useState } from 'react'
import type { ReactElement } from 'react'

export interface UploadFormProps {
  uploading: boolean
  error: string | null
  onUpload(file: File, scale: number): void
}

export function UploadForm({ uploading, error, onUpload }: UploadFormProps): ReactElement {
  const fileId = useId()
  const scaleId = useId()
  const [file, setFile] = useState<File | null>(null)
  const [scaleText, setScaleText] = useState('1')
  const scale = Number(scaleText)
  const scaleValid = scaleText.trim() !== '' && Number.isFinite(scale) && scale > 0
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (file && scaleValid && !uploading) onUpload(file, scale)
      }}
    >
      <div className="field">
        <label htmlFor={fileId}>File</label>
        <input
          id={fileId}
          type="file"
          accept=".stl,.obj,.3mf,.glb"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>
      <div className="field">
        <label htmlFor={scaleId}>Scale</label>
        <input
          id={scaleId}
          type="number"
          aria-label="Scale"
          min={0.0001}
          step={0.1}
          value={scaleText}
          onChange={(e) => setScaleText(e.target.value)}
        />
      </div>
      <button type="submit" className="btn primary block" disabled={uploading || file === null || !scaleValid}>
        {uploading ? 'Uploading…' : 'Upload'}
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  )
}
