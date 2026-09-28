import { useId, useRef, useState } from 'react'
import type { ReactElement } from 'react'

export interface UploadFormProps {
  uploading: boolean
  error: string | null
  onUpload(file: File, scale: number): void
}

export function UploadForm({ uploading, error, onUpload }: UploadFormProps): ReactElement {
  const fileId = useId()
  const scaleId = useId()
  const fileRef = useRef<HTMLInputElement>(null)
  const [pickedName, setPickedName] = useState<string | null>(null)
  const [scaleText, setScaleText] = useState('1')
  const scale = Number(scaleText)
  const scaleValid = scaleText.trim() !== '' && Number.isFinite(scale) && scale > 0
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        // Read from the input at submit time: some file pickers set `files` without a change event.
        const file = fileRef.current?.files?.[0] ?? null
        if (file && scaleValid && !uploading) onUpload(file, scale)
      }}
    >
      <div className="field">
        <label htmlFor={fileId}>File</label>
        <input
          id={fileId}
          type="file"
          accept=".stl,.obj,.3mf,.glb"
          ref={fileRef}
          onChange={(e) => setPickedName(e.target.files?.[0]?.name ?? null)}
        />
      </div>
      <div className="field">
        <label htmlFor={scaleId}>Scale</label>
        <input
          id={scaleId}
          type="number"
          aria-label="Scale"
          min={0.0001}
          step="any"
          value={scaleText}
          onChange={(e) => setScaleText(e.target.value)}
        />
      </div>
      <button type="submit" className="btn primary block" disabled={uploading || !scaleValid}>
        {uploading ? 'Uploading…' : 'Upload'}
      </button>
      {pickedName === null && !error && <p className="hint">Choose an STL, OBJ, 3MF or GLB file.</p>}
      {error && <p className="error">{error}</p>}
    </form>
  )
}
