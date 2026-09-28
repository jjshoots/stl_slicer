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

/** Axes the planner may cut along; a missing field means all three (the backend default). */
export function enabledAxes(value: PartitionSpec): Axis[] {
  return value.axes ?? AXES
}

interface CutListInputProps {
  axis: Axis
  values: number[]
  disabled?: boolean
  onCommit(values: number[]): void
}

function CutListInput({ axis, values, disabled = false, onCommit }: CutListInputProps): ReactElement {
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
  const label = `${axis.toUpperCase()} cuts (mm)`
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        className="mono"
        aria-label={label}
        value={text}
        placeholder={disabled ? 'off' : 'auto'}
        disabled={disabled}
        title={disabled ? `Cutting along ${axis.toUpperCase()} is off` : undefined}
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
  const axesId = useId()
  const [marginText, setMarginText] = useState(String(value.bed_margin))
  const [prevMargin, setPrevMargin] = useState(value.bed_margin)
  if (value.bed_margin !== prevMargin) {
    setPrevMargin(value.bed_margin)
    setMarginText(String(value.bed_margin))
  }
  const cuts = value.cuts ?? null
  const axes = enabledAxes(value)
  const setAxis = (axis: Axis, on: boolean): void => {
    const next = AXES.filter((a) => (a === axis ? on : axes.includes(a)))
    if (next.length === 0) return
    // Explicit cuts on an excluded axis are meaningless; clear them so the spec stays consistent.
    const nextCuts = cuts !== null && !on ? { ...cuts, [axis]: [] } : cuts
    onChange({ ...value, axes: next, cuts: nextCuts })
  }
  return (
    <div>
      <div className="field-row">
        {AXES.map((axis) => {
          const on = axes.includes(axis)
          const label = `Cut along ${axis.toUpperCase()}`
          const id = `${axesId}-${axis}`
          return (
            <div key={axis} className="field-inline">
              <input
                id={id}
                type="checkbox"
                aria-label={label}
                checked={on}
                disabled={on && axes.length === 1}
                title={on && axes.length === 1 ? 'At least one axis must stay on' : undefined}
                onChange={(e) => setAxis(axis, e.target.checked)}
              />
              <label htmlFor={id}>{label}</label>
            </div>
          )
        })}
      </div>
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
                disabled={!axes.includes(axis)}
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
