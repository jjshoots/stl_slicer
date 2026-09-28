import type { ReactElement } from 'react'
import type { PieceInfo, SliceWarning, Vec3 } from '../../api/types'
import { pieceColor } from '../../lib/colors'
import { formatSize, formatVolume, humanizeCode } from '../../lib/format'

export interface PiecesListProps {
  pieces: PieceInfo[]
  selected: string | null
  hidden: Set<string>
  warnings: SliceWarning[]
  onSelect(id: string | null): void
  onToggleHidden(id: string): void
}

function pieceMeta(p: PieceInfo): string {
  const { min, max } = p.bounds
  const size: Vec3 = [max[0] - min[0], max[1] - min[1], max[2] - min[2]]
  const parts = [formatSize(size), formatVolume(p.volume)]
  if (p.component_count > 1) parts.push(`${p.component_count} parts`)
  return parts.join(' · ')
}

export function PiecesList({
  pieces,
  selected,
  hidden,
  warnings,
  onSelect,
  onToggleHidden,
}: PiecesListProps): ReactElement {
  return (
    <section className="section">
      <h2 className="section-title">
        Pieces <span className="count">{pieces.length}</span>
      </h2>
      {pieces.length === 0 ? (
        <p className="muted">No pieces yet — run Slice.</p>
      ) : (
        <ul className="pieces">
          {pieces.map((p, index) => {
            const id = p.piece_id
            const isSelected = selected === id
            const isHidden = hidden.has(id)
            const cls = ['piece-row', isSelected && 'selected', isHidden && 'hidden'].filter(Boolean).join(' ')
            const pieceWarnings = warnings.filter((w) => w.subject === id)
            return (
              <li key={id} className={cls} role="button" aria-pressed={isSelected} onClick={() => onSelect(isSelected ? null : id)}>
                <span className="piece-swatch" style={{ background: pieceColor(index) }} />
                <div className="piece-main">
                  <div className="piece-id">{id}</div>
                  <div className="piece-meta">{pieceMeta(p)}</div>
                  {pieceWarnings.map((w, i) => (
                    <div key={i} className="piece-warn">
                      {humanizeCode(w.code)}: {w.message}
                    </div>
                  ))}
                </div>
                {p.fits_bed ? <span className="badge ok">fits bed</span> : <span className="badge err">too big</span>}
                <button
                  type="button"
                  className="btn icon"
                  aria-label={isHidden ? `Show ${id}` : `Hide ${id}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    onToggleHidden(id)
                  }}
                >
                  {isHidden ? '◌' : '◉'}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
