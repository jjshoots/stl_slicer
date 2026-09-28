import { useId, useState } from 'react'
import type { ReactElement } from 'react'
import type { Axis, AxisCuts, PartitionSpec } from '../../api/types'
import { formatNumberList, parseNumberList } from '../../lib/format'

export interface PartitionFormProps {
  value: PartitionSpec
  onChange(value: PartitionSpec): void
}

const AXES: Axis[] = ['x', 'y', 'z']
const EMPTY_CUTS: AxisCuts = { x: [], y: [], z: [] }

interface CutListInputProps {
  axis: Axis
  values: number[]
  onCommit(values: number[]): void
}

function CutListInput({ axis, values, onCommit }: CutListInputProps): ReactElement {
  const id = useId()
  const [text, setText] = useState(formatNumberList(values))
  const [prev, setPrev] = useState(values)
  if (values !== prev) {
    setPrev(values)
    setText(formatNumberList(values))
  }
  const commit = (): void => {
    const sorted = [...new Set(parseNumberList(text))].sort((a, b) => a - b)
    setText(formatNumberList(sorted))
    onCommit(sorted)
  }
  const label = `${axis.toUpperCase()} cuts`
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        className="mono"
        aria-label={label}
        value={text}
        placeholder="auto"
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter') commit()
        }}
      />
    </div>
  )
}

export function PartitionForm({ value, onChange }: PartitionFormProps): ReactElement {
  const marginId = useId()
  const explicitId = useId()
  const [marginText, setMarginText] = useState(String(value.bed_margin))
  const [prevMargin, setPrevMargin] = useState(value.bed_margin)
  if (value.bed_margin !== prevMargin) {
    setPrevMargin(value.bed_margin)
    setMarginText(String(value.bed_margin))
  }
  const cuts = value.cuts ?? null
  return (
    <div>
      <div className="field">
        <label htmlFor={marginId}>Bed margin (mm)</label>
        <input
          id={marginId}
          type="number"
          aria-label="Bed margin"
          min={0}
          step={0.5}
          value={marginText}
          onChange={(e) => {
            const next = e.target.value
            setMarginText(next)
            const n = next.trim() === '' ? NaN : Number(next)
            if (Number.isFinite(n) && n >= 0) {
              setPrevMargin(n)
              onChange({ ...value, bed_margin: n })
            }
          }}
        />
      </div>
      <div className="field-inline">
        <input
          id={explicitId}
          type="checkbox"
          checked={cuts !== null}
          onChange={(e) => onChange({ ...value, cuts: e.target.checked ? EMPTY_CUTS : null })}
        />
        <label htmlFor={explicitId}>Explicit cut positions</label>
      </div>
      {cuts !== null && (
        <>
          <div className="field-row">
            {AXES.map((axis) => (
              <CutListInput
                key={axis}
                axis={axis}
                values={cuts[axis] ?? []}
                onCommit={(list) => onChange({ ...value, cuts: { ...cuts, [axis]: list } })}
              />
            ))}
          </div>
          <p className="hint">Comma-separated positions in model mm; empty = automatic</p>
        </>
      )}
    </div>
  )
}
