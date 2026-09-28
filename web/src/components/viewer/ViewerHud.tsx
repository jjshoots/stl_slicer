import type { ReactElement } from 'react'
import type { PrintVolume, Vec3 } from '../../api/types'
import { formatSize } from '../../lib/format'

export interface ViewerHudProps {
  /** Model bounding-box size (W × D × H) in model millimetres; absent before an upload. */
  modelSize?: Vec3
  /** Number of pieces in the current result; absent until a slice has finished. */
  pieceCount?: number
  bed: PrintVolume
}

/** Non-interactive top-left readout: model size, and once sliced the piece count and bed size. */
export function ViewerHud({ modelSize, pieceCount, bed }: ViewerHudProps): ReactElement | null {
  if (!modelSize) return null
  return (
    <div className="viewer-hud" aria-hidden="true">
      <div>
        <span className="muted">model </span>
        <span className="mono">{formatSize(modelSize)}</span>
      </div>
      {pieceCount !== undefined && (
        <div>
          <span className="mono">{pieceCount}</span>
          <span className="muted"> {pieceCount === 1 ? 'piece' : 'pieces'} · bed </span>
          <span className="mono">{formatSize([bed.x, bed.y, bed.z], 0)}</span>
        </div>
      )}
    </div>
  )
}
