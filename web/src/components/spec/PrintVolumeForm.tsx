import { useId, useState } from 'react'
import type { ReactElement } from 'react'
import type { PrinterPreset, PrintVolume } from '../../api/types'

export interface PrintVolumeFormProps {
  value: PrintVolume
  presets: PrinterPreset[]
  onChange(value: PrintVolume): void
}

type AxisKey = keyof PrintVolume

const AXES: AxisKey[] = ['x', 'y', 'z']

interface AxisInputProps {
  axis: AxisKey
  value: number
  onChange(value: number): void
}

function AxisInput({ axis, value, onChange }: AxisInputProps): ReactElement {
  const id = useId()
  const [text, setText] = useState(String(value))
  const [prev, setPrev] = useState(value)
  if (value !== prev) {
    setPrev(value)
    setText(String(value))
  }
  const label = `${axis.toUpperCase()} (mm)`
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        aria-label={label}
        min={1}
        step={1}
        value={text}
        onChange={(e) => {
          const next = e.target.value
          setText(next)
          const n = next.trim() === '' ? NaN : Number(next)
          if (Number.isFinite(n) && n > 0) {
            setPrev(n)
            onChange(n)
          }
        }}
      />
    </div>
  )
}

function sameVolume(a: PrintVolume, b: PrintVolume): boolean {
  return a.x === b.x && a.y === b.y && a.z === b.z
}

export function PrintVolumeForm({ value, presets, onChange }: PrintVolumeFormProps): ReactElement {
  const presetId = useId()
  // Several presets share a volume (every 256 mm Bambu machine), so remember the name the user
  // picked and keep showing it while the volume still matches; otherwise fall back to the first
  // preset with this volume.
  const [chosen, setChosen] = useState<string | null>(null)
  const chosenPreset = presets.find((p) => p.name === chosen)
  const match =
    chosenPreset && sameVolume(chosenPreset.print_volume, value)
      ? chosenPreset
      : presets.find((p) => sameVolume(p.print_volume, value))
  return (
    <div>
      <div className="field">
        <label htmlFor={presetId}>Printer</label>
        <select
          id={presetId}
          aria-label="Printer preset"
          value={match ? match.name : ''}
          onChange={(e) => {
            const preset = presets.find((p) => p.name === e.target.value)
            setChosen(preset ? preset.name : null)
            if (preset) onChange(preset.print_volume)
          }}
        >
          <option value="">Custom</option>
          {presets.map((p) => (
            <option key={p.name} value={p.name}>
              {p.name}
            </option>
          ))}
        </select>
      </div>
      <div className="field-row">
        {AXES.map((axis) => (
          <AxisInput key={axis} axis={axis} value={value[axis]} onChange={(n) => onChange({ ...value, [axis]: n })} />
        ))}
      </div>
    </div>
  )
}
