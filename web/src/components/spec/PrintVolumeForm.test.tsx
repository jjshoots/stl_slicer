import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import type { ReactElement } from 'react'
import { describe, expect, it } from 'vitest'
import type { PrinterPreset, PrintVolume } from '../../api/types'
import { PrintVolumeForm } from './PrintVolumeForm'

const presets: PrinterPreset[] = [
  { name: 'Bambu Lab A1', print_volume: { x: 256, y: 256, z: 256 } },
  { name: 'Bambu Lab P1S', print_volume: { x: 256, y: 256, z: 256 } },
  { name: 'Prusa MK4', print_volume: { x: 250, y: 210, z: 220 } },
]

function Harness(): ReactElement {
  const [value, setValue] = useState<PrintVolume>({ x: 250, y: 210, z: 220 })
  return <PrintVolumeForm value={value} presets={presets} onChange={setValue} />
}

describe('PrintVolumeForm preset selection', () => {
  it('keeps showing the chosen preset when several share a volume', () => {
    render(<Harness />)
    const select = screen.getByLabelText('Printer preset') as HTMLSelectElement
    expect(select.value).toBe('Prusa MK4')
    fireEvent.change(select, { target: { value: 'Bambu Lab P1S' } })
    expect(select.value).toBe('Bambu Lab P1S')
  })

  it('falls back to the first preset with a matching volume when the volume is edited to match', () => {
    render(<Harness />)
    const select = screen.getByLabelText('Printer preset') as HTMLSelectElement
    fireEvent.change(select, { target: { value: 'Bambu Lab P1S' } })
    fireEvent.change(screen.getByLabelText('X (mm)'), { target: { value: '200' } })
    expect(select.value).toBe('')
    fireEvent.change(screen.getByLabelText('X (mm)'), { target: { value: '256' } })
    expect(select.value).toBe('Bambu Lab P1S')
  })
})
