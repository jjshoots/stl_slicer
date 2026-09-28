import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { CutPlan, JigsawJointSpec, MeshAsset } from '../../api/types'
import { DEFAULT_JOINTS } from '../../store/data'
import { PlanSummary, formatCutPositions } from './PlanSummary'

const model: MeshAsset = {
  model_id: 'm1',
  filename: 'cube.stl',
  scale: 1,
  triangle_count: 12,
  bounds: { min: [0, 0, 0], max: [72, 36, 36] },
  volume: 93312,
  warnings: [],
}

const plan: CutPlan = {
  bounds: model.bounds,
  limits: { max_cell: [50, 50, 50], min_cell: 1 },
  cuts: { x: [0, 36], y: [], z: [] },
  cells: [],
  interfaces: [],
  warnings: [{ code: 'cell_oversize', message: 'cell exceeds the bed along y', subject: 'y' }],
}

describe('PlanSummary', () => {
  it('formats cut positions in mm', () => {
    expect(formatCutPositions([0])).toBe('0.0 mm')
    expect(formatCutPositions([0, 36])).toBe('0.0, 36.0 mm')
  })

  it('shows model size, volume and cut positions with units', () => {
    render(<PlanSummary model={model} plan={plan} error={null} />)
    expect(screen.getByText('72.0 × 36.0 × 36.0 mm')).not.toBeNull()
    expect(screen.getByText('93.31 cm³')).not.toBeNull()
    expect(screen.getByText('@ 0.0, 36.0 mm')).not.toBeNull()
  })

  it('renders CELL_OVERSIZE with its subject axis', () => {
    render(<PlanSummary model={model} plan={plan} error={null} />)
    const item = screen.getByText('cell exceeds the bed along y').closest('li')
    expect(item?.textContent).toContain('Cell oversize')
    expect(item?.textContent).toContain('(Y axis)')
  })

  describe('resolved joint line', () => {
    const resolved: JigsawJointSpec = {
      kind: 'jigsaw',
      auto: false,
      neck_width: 16.2,
      head_diameter: 29.5,
      depth: 38.4,
      clearance: 0.15,
      edge_margin: 3,
      spacing: 123,
    }
    const LINE = 'jigsaw · head 29.5 mm · neck 16.2 mm · depth 38.4 mm · spacing 123 mm'

    it('shows the resolved joint when the spec joint is auto-sized', () => {
      render(<PlanSummary model={model} plan={{ ...plan, resolved_joint: resolved }} error={null} joint={DEFAULT_JOINTS.jigsaw} />)
      expect(screen.getByText('joint')).not.toBeNull()
      expect(screen.getByText(LINE)).not.toBeNull()
    })

    it('hides it when auto is off, when there is no resolved joint, or for kind none', () => {
      const withResolved = { ...plan, resolved_joint: resolved }
      const a = render(
        <PlanSummary model={model} plan={withResolved} error={null} joint={{ ...DEFAULT_JOINTS.jigsaw, auto: false }} />,
      )
      expect(screen.queryByText(LINE)).toBeNull()
      a.unmount()
      const b = render(<PlanSummary model={model} plan={plan} error={null} joint={DEFAULT_JOINTS.jigsaw} />)
      expect(screen.queryByText(LINE)).toBeNull()
      b.unmount()
      render(<PlanSummary model={model} plan={withResolved} error={null} joint={DEFAULT_JOINTS.none} />)
      expect(screen.queryByText(LINE)).toBeNull()
    })
  })
})
