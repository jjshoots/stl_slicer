import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PartitionSpec } from '../../api/types'
import { PartitionForm, enabledAxes } from './PartitionForm'

function box(label: string): HTMLInputElement {
  return screen.getByLabelText(label) as HTMLInputElement
}

describe('PartitionForm cut axes', () => {
  it('defaults all three axes on and treats a missing field as all on', () => {
    expect(enabledAxes({ cuts: null, bed_margin: 2 })).toEqual(['x', 'y', 'z'])
    render(<PartitionForm value={{ cuts: null, bed_margin: 2 }} onChange={vi.fn()} />)
    for (const a of ['X', 'Y', 'Z']) {
      expect(box(`Cut along ${a}`).checked).toBe(true)
      expect(box(`Cut along ${a}`).disabled).toBe(false)
    }
  })

  it('unchecking an axis writes partition.axes without it', () => {
    const onChange = vi.fn()
    render(<PartitionForm value={{ cuts: null, bed_margin: 2, axes: ['x', 'y', 'z'] }} onChange={onChange} />)
    fireEvent.click(box('Cut along Y'))
    expect(onChange).toHaveBeenCalledWith({ cuts: null, bed_margin: 2, axes: ['x', 'z'] })
  })

  it('re-checking an axis keeps canonical x, y, z order', () => {
    const onChange = vi.fn()
    render(<PartitionForm value={{ cuts: null, bed_margin: 2, axes: ['z'] }} onChange={onChange} />)
    fireEvent.click(box('Cut along X'))
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ axes: ['x', 'z'] }))
  })

  it('the last enabled axis cannot be unchecked', () => {
    const onChange = vi.fn()
    render(<PartitionForm value={{ cuts: null, bed_margin: 2, axes: ['z'] }} onChange={onChange} />)
    expect(box('Cut along Z').disabled).toBe(true)
    expect(box('Cut along X').disabled).toBe(false)
    fireEvent.click(box('Cut along Z'))
    expect(onChange).not.toHaveBeenCalled()
  })

  it('disables and clears explicit cuts for an unchecked axis', () => {
    const onChange = vi.fn()
    const value: PartitionSpec = { cuts: { x: [10], y: [20], z: [30] }, bed_margin: 2, axes: ['x', 'y', 'z'] }
    const { rerender } = render(<PartitionForm value={value} onChange={onChange} />)
    fireEvent.click(box('Cut along Y'))
    expect(onChange).toHaveBeenCalledWith({
      cuts: { x: [10], y: [], z: [30] },
      bed_margin: 2,
      axes: ['x', 'z'],
    })
    rerender(<PartitionForm value={onChange.mock.calls[0][0] as PartitionSpec} onChange={onChange} />)
    const y = box('Y cuts (mm)')
    expect(y.disabled).toBe(true)
    expect(y.value).toBe('')
    expect(box('X cuts (mm)').disabled).toBe(false)
    expect(box('X cuts (mm)').value).toBe('10')
  })

  it('labels the explicit-cut inputs and bed margin in mm', () => {
    render(<PartitionForm value={{ cuts: { x: [], y: [], z: [] }, bed_margin: 2 }} onChange={vi.fn()} />)
    expect(screen.getByText('Bed margin (mm)')).not.toBeNull()
    for (const a of ['X', 'Y', 'Z']) expect(screen.getByText(`${a} cuts (mm)`)).not.toBeNull()
  })
})
