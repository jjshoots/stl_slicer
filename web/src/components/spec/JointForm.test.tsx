import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { DowelJointSpec, DovetailJointSpec, JigsawJointSpec } from '../../api/types'
import { DEFAULT_JOINTS } from '../../store/data'
import { JointForm, jigsawErrors } from './JointForm'

const DOWEL_LABELS = ['Diameter', 'Depth', 'Clearance', 'Edge margin', 'Spacing']
const DOVETAIL_LABELS = ['Neck width', 'Head width', 'Depth', 'Clearance', 'Edge margin', 'Spacing']
const JIGSAW_LABELS = ['Neck width', 'Head diameter', 'Depth', 'Clearance', 'Edge margin', 'Spacing']
const JIGSAW_HELP = 'Puzzle-piece knobs in the cut plane; pieces drop in along the slide axis (Z for X/Y cuts)'

function inputValue(label: string): string {
  return (screen.getByLabelText(label) as HTMLInputElement).value
}

describe('JointForm', () => {
  it('renders no numeric fields and no male side for kind none', () => {
    const { container } = render(
      <JointForm value={DEFAULT_JOINTS.none} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />,
    )
    expect(container.querySelectorAll('input[type="number"]').length).toBe(0)
    expect(screen.queryByLabelText('Male side')).toBeNull()
    for (const label of [...DOWEL_LABELS, ...DOVETAIL_LABELS]) {
      expect(screen.queryByLabelText(label)).toBeNull()
    }
  })

  it('renders exactly the dowel fields with prop values and the male side select', () => {
    const value: DowelJointSpec = { kind: 'dowel', diameter: 5, depth: 7, clearance: 0.2, edge_margin: 4, spacing: 30 }
    const { container } = render(
      <JointForm value={value} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />,
    )
    expect(container.querySelectorAll('input[type="number"]').length).toBe(DOWEL_LABELS.length)
    expect(inputValue('Diameter')).toBe('5')
    expect(inputValue('Depth')).toBe('7')
    expect(inputValue('Clearance')).toBe('0.2')
    expect(inputValue('Edge margin')).toBe('4')
    expect(inputValue('Spacing')).toBe('30')
    expect(screen.queryByLabelText('Neck width')).toBeNull()
    expect(screen.queryByLabelText('Male side')).not.toBeNull()
  })

  it('renders dovetail fields and flags head width <= neck width', () => {
    const value: DovetailJointSpec = { ...DEFAULT_JOINTS.dovetail, neck_width: 10, head_width: 10 }
    const { container } = render(
      <JointForm value={value} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />,
    )
    expect(container.querySelectorAll('input[type="number"]').length).toBe(DOVETAIL_LABELS.length)
    for (const label of DOVETAIL_LABELS) expect(screen.queryByLabelText(label)).not.toBeNull()
    expect(inputValue('Neck width')).toBe('10')
    expect(screen.queryByText('Head width must exceed neck width')).not.toBeNull()
  })

  it('does not flag a valid dovetail', () => {
    render(<JointForm value={DEFAULT_JOINTS.dovetail} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />)
    expect(screen.queryByText('Head width must exceed neck width')).toBeNull()
  })

  it('switching kind emits the default spec for that kind', () => {
    const onChange = vi.fn()
    render(<JointForm value={DEFAULT_JOINTS.dowel} maleSide="lower" onChange={onChange} onMaleSideChange={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Joint kind'), { target: { value: 'dovetail' } })
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith(DEFAULT_JOINTS.dovetail)
  })

  it('editing a number field emits the patched spec', () => {
    const onChange = vi.fn()
    const value = DEFAULT_JOINTS.dowel
    render(<JointForm value={value} maleSide="lower" onChange={onChange} onMaleSideChange={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Diameter'), { target: { value: '10' } })
    expect(onChange).toHaveBeenCalledWith({ ...value, diameter: 10 })
  })

  it('changing male side calls onMaleSideChange', () => {
    const onMaleSideChange = vi.fn()
    render(
      <JointForm value={DEFAULT_JOINTS.dowel} maleSide="lower" onChange={vi.fn()} onMaleSideChange={onMaleSideChange} />,
    )
    fireEvent.change(screen.getByLabelText('Male side'), { target: { value: 'upper' } })
    expect(onMaleSideChange).toHaveBeenCalledWith('upper')
  })

  it('shows every joint dimension with a mm unit in its visible label', () => {
    render(<JointForm value={DEFAULT_JOINTS.dowel} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />)
    for (const label of DOWEL_LABELS) expect(screen.getByText(`${label} (mm)`)).not.toBeNull()
  })

  it('lists Jigsaw knobs in the kind select and switching to it emits the backend defaults', () => {
    const onChange = vi.fn()
    render(<JointForm value={DEFAULT_JOINTS.none} maleSide="lower" onChange={onChange} onMaleSideChange={vi.fn()} />)
    expect(screen.getByRole('option', { name: 'Jigsaw knobs' })).not.toBeNull()
    fireEvent.change(screen.getByLabelText('Joint kind'), { target: { value: 'jigsaw' } })
    expect(onChange).toHaveBeenCalledWith({
      kind: 'jigsaw',
      neck_width: 8,
      head_diameter: 14,
      depth: 12,
      clearance: 0.15,
      edge_margin: 3,
      spacing: 60,
    })
  })

  it('renders exactly the jigsaw fields, the help line and the male side select', () => {
    const { container } = render(
      <JointForm value={DEFAULT_JOINTS.jigsaw} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />,
    )
    expect(container.querySelectorAll('input[type="number"]').length).toBe(JIGSAW_LABELS.length)
    for (const label of JIGSAW_LABELS) {
      expect(screen.queryByLabelText(label)).not.toBeNull()
      expect(screen.getByText(`${label} (mm)`)).not.toBeNull()
    }
    expect(inputValue('Head diameter')).toBe('14')
    expect(inputValue('Depth')).toBe('12')
    expect(screen.queryByLabelText('Head width')).toBeNull()
    expect(screen.getByText(JIGSAW_HELP)).not.toBeNull()
    expect(screen.queryByLabelText('Male side')).not.toBeNull()
    expect(container.querySelectorAll('.error').length).toBe(0)
  })

  it('flags head diameter <= neck width and depth <= head diameter / 2 like the backend', () => {
    expect(jigsawErrors(DEFAULT_JOINTS.jigsaw)).toEqual([])
    expect(jigsawErrors({ ...DEFAULT_JOINTS.jigsaw, head_diameter: 8 })).toEqual(['Head diameter must exceed neck width'])
    expect(jigsawErrors({ ...DEFAULT_JOINTS.jigsaw, depth: 7 })).toEqual(['Depth must exceed half the head diameter'])
    expect(jigsawErrors({ ...DEFAULT_JOINTS.jigsaw, head_diameter: 8, depth: 4 })).toHaveLength(2)

    const value: JigsawJointSpec = { ...DEFAULT_JOINTS.jigsaw, neck_width: 14, depth: 7 }
    render(<JointForm value={value} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />)
    expect(screen.getByText('Head diameter must exceed neck width')).not.toBeNull()
    expect(screen.getByText('Depth must exceed half the head diameter')).not.toBeNull()
  })

  it('editing a jigsaw field emits the patched spec', () => {
    const onChange = vi.fn()
    render(<JointForm value={DEFAULT_JOINTS.jigsaw} maleSide="lower" onChange={onChange} onMaleSideChange={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Head diameter'), { target: { value: '16' } })
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_JOINTS.jigsaw, head_diameter: 16 })
  })
})
