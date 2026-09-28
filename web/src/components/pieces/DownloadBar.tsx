import type { ReactElement } from 'react'
import type { Job } from '../../api/types'
import { formatPercent, formatVolume } from '../../lib/format'

export interface DownloadBarProps {
  explode: number
  onExplode(v: number): void
  showPlanes: boolean
  onShowPlanes(v: boolean): void
  job: Job | null
  canSlice: boolean
  onSlice(): void
  onCancel(): void
  downloadUrl: string | null
}

function JobStatusView({ job, onCancel }: { job: Job; onCancel(): void }): ReactElement | null {
  switch (job.status) {
    case 'queued':
    case 'running':
      return (
        <div className="progress-row">
          <div className="progress">
            <div className="bar" style={{ width: `${job.progress * 100}%` }} />
          </div>
          <span className="progress-label">
            {job.step} {formatPercent(job.progress)}
          </span>
          <button type="button" className="btn small danger" onClick={onCancel}>
            Cancel
          </button>
        </div>
      )
    case 'failed':
      return <span className="error">Failed: {job.error}</span>
    case 'cancelled':
      return <span className="muted">Cancelled</span>
    case 'done': {
      const stats = job.result?.stats
      return stats ? (
        <span className="muted">
          {stats.piece_count} pieces · {formatVolume(stats.output_volume)} in {stats.duration_s.toFixed(1)} s
        </span>
      ) : null
    }
  }
}

export function DownloadBar({
  explode,
  onExplode,
  showPlanes,
  onShowPlanes,
  job,
  canSlice,
  onSlice,
  onCancel,
  downloadUrl,
}: DownloadBarProps): ReactElement {
  const busy = job !== null && (job.status === 'queued' || job.status === 'running')
  return (
    <div className="downloadbar">
      <label className="control">
        Explode
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={explode}
          aria-label="Explode"
          onChange={(e) => onExplode(Number(e.target.value))}
        />
      </label>
      <label className="control">
        <input type="checkbox" checked={showPlanes} onChange={(e) => onShowPlanes(e.target.checked)} />
        Show cut planes
      </label>
      <div className="grow">{job && <JobStatusView job={job} onCancel={onCancel} />}</div>
      <button type="button" className="btn primary" disabled={!canSlice || busy} onClick={onSlice}>
        Slice
      </button>
      {downloadUrl && (
        <a className="btn" href={downloadUrl} download>
          Download ZIP
        </a>
      )}
    </div>
  )
}
