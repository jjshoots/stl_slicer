import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { DowelJointSpec, DovetailJointSpec, JigsawJointSpec } from '../../api/types'
import { DEFAULT_JOINTS } from '../../store/data'
import { AUTO_HINT, JointForm, jigsawErrors } from './JointForm'

/** Manual (auto off) variants of the defaults for the field-editing tests below. */
const MANUAL = {
  dowel: { ...DEFAULT_JOINTS.dowel, auto: false },
  dovetail: { ...DEFAULT_JOINTS.dovetail, auto: false },
  jigsaw: { ...DEFAULT_JOINTS.jigsaw, auto: false },
}

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
    const value: DowelJointSpec = { kind: 'dowel', auto: false, diameter: 5, depth: 7, clearance: 0.2, edge_margin: 4, spacing: 30 }
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
    const value: DovetailJointSpec = { ...MANUAL.dovetail, neck_width: 10, head_width: 10 }
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
    const value = MANUAL.dowel
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
      auto: true,
      neck_width: 8,
      head_diameter: 14,
      depth: 18,
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
    expect(inputValue('Depth')).toBe('18')
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

    const value: JigsawJointSpec = { ...MANUAL.jigsaw, neck_width: 14, depth: 7 }
    render(<JointForm value={value} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />)
    expect(screen.getByText('Head diameter must exceed neck width')).not.toBeNull()
    expect(screen.getByText('Depth must exceed half the head diameter')).not.toBeNull()
  })

  it('editing a jigsaw field emits the patched spec', () => {
    const onChange = vi.fn()
    render(<JointForm value={MANUAL.jigsaw} maleSide="lower" onChange={onChange} onMaleSideChange={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Head diameter'), { target: { value: '16' } })
    expect(onChange).toHaveBeenCalledWith({ ...MANUAL.jigsaw, head_diameter: 16 })
  })
})

describe('JointForm auto size', () => {
  const RESOLVED_JIGSAW: JigsawJointSpec = {
    kind: 'jigsaw',
    auto: false,
    neck_width: 16.2,
    head_diameter: 29.5,
    depth: 38.4,
    clearance: 0.15,
    edge_margin: 3,
    spacing: 123,
  }

  function autoCheckbox(): HTMLInputElement {
    return screen.getByLabelText('Auto size') as HTMLInputElement
  }

  it('has no Auto size checkbox for kind none', () => {
    render(<JointForm value={DEFAULT_JOINTS.none} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />)
    expect(screen.queryByLabelText('Auto size')).toBeNull()
  })

  it('is on by default for every sized kind, disables the inputs and shows the hint', () => {
    for (const kind of ['dowel', 'dovetail', 'jigsaw'] as const) {
      const { container, unmount } = render(
        <JointForm value={DEFAULT_JOINTS[kind]} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />,
      )
      expect(DEFAULT_JOINTS[kind].auto).toBe(true)
      expect(autoCheckbox().checked).toBe(true)
      const inputs = container.querySelectorAll('input[type="number"]')
      expect(inputs.length).toBeGreaterThan(0)
      for (const input of inputs) expect((input as HTMLInputElement).disabled).toBe(true)
      expect(screen.getByText(AUTO_HINT)).not.toBeNull()
      unmount()
    }
  })

  it('shows the spec numbers while no plan exists yet', () => {
    render(<JointForm value={DEFAULT_JOINTS.jigsaw} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />)
    expect(inputValue('Head diameter')).toBe('14')
    expect(inputValue('Depth')).toBe('18')
  })

  it('shows the resolved values from the plan while auto is on', () => {
    render(
      <JointForm
        value={DEFAULT_JOINTS.jigsaw}
        resolvedJoint={RESOLVED_JIGSAW}
        maleSide="lower"
        onChange={vi.fn()}
        onMaleSideChange={vi.fn()}
      />,
    )
    expect(inputValue('Head diameter')).toBe('29.5')
    expect(inputValue('Neck width')).toBe('16.2')
    expect(inputValue('Depth')).toBe('38.4')
    expect(inputValue('Spacing')).toBe('123')
  })

  it('ignores a resolved joint of a different kind', () => {
    render(
      <JointForm
        value={DEFAULT_JOINTS.dowel}
        resolvedJoint={RESOLVED_JIGSAW}
        maleSide="lower"
        onChange={vi.fn()}
        onMaleSideChange={vi.fn()}
      />,
    )
    expect(inputValue('Diameter')).toBe('8')
  })

  it('turning auto off copies the resolved values into the spec and sets auto false', () => {
    const onChange = vi.fn()
    render(
      <JointForm
        value={DEFAULT_JOINTS.jigsaw}
        resolvedJoint={RESOLVED_JIGSAW}
        maleSide="lower"
        onChange={onChange}
        onMaleSideChange={vi.fn()}
      />,
    )
    fireEvent.click(autoCheckbox())
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledWith({ ...RESOLVED_JIGSAW, auto: false })
  })

  it('turning auto off without a plan keeps the spec numbers', () => {
    const onChange = vi.fn()
    render(<JointForm value={DEFAULT_JOINTS.dowel} maleSide="lower" onChange={onChange} onMaleSideChange={vi.fn()} />)
    fireEvent.click(autoCheckbox())
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_JOINTS.dowel, auto: false })
  })

  it('turning auto back on sets auto true and leaves the numbers', () => {
    const onChange = vi.fn()
    const value: DowelJointSpec = { ...MANUAL.dowel, diameter: 11 }
    const { container } = render(
      <JointForm value={value} maleSide="lower" onChange={onChange} onMaleSideChange={vi.fn()} />,
    )
    expect(autoCheckbox().checked).toBe(false)
    for (const input of container.querySelectorAll('input[type="number"]')) {
      expect((input as HTMLInputElement).disabled).toBe(false)
    }
    expect(screen.queryByText(AUTO_HINT)).toBeNull()
    fireEvent.click(autoCheckbox())
    expect(onChange).toHaveBeenCalledWith({ ...value, auto: true })
  })

  it('does not run inline validation while auto is on', () => {
    const dovetail: DovetailJointSpec = { ...DEFAULT_JOINTS.dovetail, neck_width: 10, head_width: 10 }
    const a = render(<JointForm value={dovetail} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />)
    expect(a.container.querySelectorAll('.error').length).toBe(0)
    a.unmount()

    const jigsaw: JigsawJointSpec = { ...DEFAULT_JOINTS.jigsaw, neck_width: 14, depth: 7 }
    const b = render(<JointForm value={jigsaw} maleSide="lower" onChange={vi.fn()} onMaleSideChange={vi.fn()} />)
    expect(b.container.querySelectorAll('.error').length).toBe(0)
  })
})
