import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PieceInfo, SliceWarning } from '../../api/types'
import { PiecesList } from './PiecesList'

function piece(id: string, fits: boolean): PieceInfo {
  return {
    piece_id: id,
    cell: { i: 0, j: 0, k: 0 },
    component: 0,
    bounds: { min: [0, 0, 0], max: [10, 20, 30] },
    volume: 6000,
    triangle_count: 12,
    component_count: 1,
    fits_bed: fits,
    print_offset: [0, 0, 0],
  }
}

const PIECES = [piece('p_0_0_0', true), piece('p_1_0_0', false)]

function setup(opts: { selected?: string | null; hidden?: string[]; warnings?: SliceWarning[]; pieces?: PieceInfo[] } = {}) {
  const onSelect = vi.fn()
  const onToggleHidden = vi.fn()
  render(
    <PiecesList
      pieces={opts.pieces ?? PIECES}
      selected={opts.selected ?? null}
      hidden={new Set(opts.hidden ?? [])}
      warnings={opts.warnings ?? []}
      onSelect={onSelect}
      onToggleHidden={onToggleHidden}
    />,
  )
  return { onSelect, onToggleHidden }
}

function row(id: string): HTMLElement {
  const el = screen.getByText(id).closest('li')
  if (!el) throw new Error(`row ${id} not found`)
  return el
}

describe('PiecesList', () => {
  it('selects a piece on row click', () => {
    const { onSelect } = setup()
    fireEvent.click(row('p_0_0_0'))
    expect(onSelect).toHaveBeenCalledWith('p_0_0_0')
  })

  it('deselects when clicking the selected row', () => {
    const { onSelect } = setup({ selected: 'p_1_0_0' })
    expect(row('p_1_0_0').className).toContain('selected')
    fireEvent.click(row('p_1_0_0'))
    expect(onSelect).toHaveBeenCalledWith(null)
  })

  it('toggles visibility without selecting', () => {
    const { onSelect, onToggleHidden } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Hide p_0_0_0' }))
    expect(onToggleHidden).toHaveBeenCalledWith('p_0_0_0')
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('marks hidden pieces', () => {
    setup({ hidden: ['p_1_0_0'] })
    expect(row('p_1_0_0').className).toContain('hidden')
    expect(row('p_0_0_0').className).not.toContain('hidden')
    expect(screen.queryByRole('button', { name: 'Show p_1_0_0' })).not.toBeNull()
  })

  it('shows fits-bed badges', () => {
    setup()
    expect(row('p_1_0_0').textContent).toContain('too big')
    expect(row('p_0_0_0').textContent).toContain('fits bed')
  })

  it('renders warnings under the matching piece', () => {
    setup({ warnings: [{ code: 'piece_oversize', message: 'exceeds bed', subject: 'p_1_0_0' }] })
    const warn = row('p_1_0_0').querySelector('.piece-warn')
    expect(warn).not.toBeNull()
    expect(warn?.textContent).toBe('Piece oversize: exceeds bed')
    expect(row('p_0_0_0').querySelector('.piece-warn')).toBeNull()
  })

  it('shows an empty state', () => {
    setup({ pieces: [] })
    expect(screen.queryByText(/No pieces yet/)).not.toBeNull()
    expect(screen.queryByRole('list')).toBeNull()
  })

  it('prints piece size and volume with units', () => {
    setup()
    expect(row('p_0_0_0').querySelector('.piece-meta')?.textContent).toBe('10.0 × 20.0 × 30.0 mm · 6.00 cm³')
  })
})
