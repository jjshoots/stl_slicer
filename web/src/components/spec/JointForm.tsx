import { useId, useState } from 'react'
import type { ComponentType, ReactElement } from 'react'
import type { JointKind, JointSpec, MaleSide } from '../../api/types'
import { DEFAULT_JOINTS } from '../../store/data'

interface JointFieldsProps<S extends JointSpec> {
  value: S
  onChange(value: S): void
}

export interface JointFormProps {
  value: JointSpec
  maleSide: MaleSide
  onChange(value: JointSpec): void
  onMaleSideChange(side: MaleSide): void
}

interface NumberFieldProps {
  label: string
  value: number
  min?: number
  step?: number
  onChange(value: number): void
}

/** Number input that keeps intermediate text locally and commits only finite numbers. */
function NumberField({ label, value, min, step, onChange }: NumberFieldProps): ReactElement {
  const id = useId()
  const [text, setText] = useState(String(value))
  const [prev, setPrev] = useState(value)
  if (value !== prev) {
    setPrev(value)
    setText(String(value))
  }
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="number"
        aria-label={label}
        min={min}
        step={step}
        value={text}
        onChange={(e) => {
          const next = e.target.value
          setText(next)
          const n = next.trim() === '' ? NaN : Number(next)
          if (Number.isFinite(n)) {
            setPrev(n)
            onChange(n)
          }
        }}
      />
    </div>
  )
}

function NoJointFields(_props: JointFieldsProps<Extract<JointSpec, { kind: 'none' }>>): ReactElement {
  return <p className="hint muted">Pieces are cut flat; no registration features.</p>
}

function DowelFields({ value, onChange }: JointFieldsProps<Extract<JointSpec, { kind: 'dowel' }>>): ReactElement {
  return (
    <>
      <div className="field-row">
        <NumberField label="Diameter" value={value.diameter} min={0} step={0.5} onChange={(diameter) => onChange({ ...value, diameter })} />
        <NumberField label="Depth" value={value.depth} min={0} step={0.5} onChange={(depth) => onChange({ ...value, depth })} />
      </div>
      <div className="field-row">
        <NumberField label="Clearance" value={value.clearance} min={0} step={0.05} onChange={(clearance) => onChange({ ...value, clearance })} />
        <NumberField label="Edge margin" value={value.edge_margin} min={0} step={0.5} onChange={(edge_margin) => onChange({ ...value, edge_margin })} />
        <NumberField label="Spacing" value={value.spacing} min={0} step={1} onChange={(spacing) => onChange({ ...value, spacing })} />
      </div>
    </>
  )
}

function DovetailFields({ value, onChange }: JointFieldsProps<Extract<JointSpec, { kind: 'dovetail' }>>): ReactElement {
  return (
    <>
      <div className="field-row">
        <NumberField label="Neck width" value={value.neck_width} min={0} step={0.5} onChange={(neck_width) => onChange({ ...value, neck_width })} />
        <NumberField label="Head width" value={value.head_width} min={0} step={0.5} onChange={(head_width) => onChange({ ...value, head_width })} />
        <NumberField label="Depth" value={value.depth} min={0} step={0.5} onChange={(depth) => onChange({ ...value, depth })} />
      </div>
      {value.head_width <= value.neck_width && <p className="error">Head width must exceed neck width</p>}
      <div className="field-row">
        <NumberField label="Clearance" value={value.clearance} min={0} step={0.05} onChange={(clearance) => onChange({ ...value, clearance })} />
        <NumberField label="Edge margin" value={value.edge_margin} min={0} step={0.5} onChange={(edge_margin) => onChange({ ...value, edge_margin })} />
        <NumberField label="Spacing" value={value.spacing} min={0} step={1} onChange={(spacing) => onChange({ ...value, spacing })} />
      </div>
    </>
  )
}

type JointOf<K extends JointKind> = Extract<JointSpec, { kind: K }>

/** Adding a joint kind = one entry here + one fields component. */
const JOINT_FORMS: { [K in JointKind]: ComponentType<JointFieldsProps<JointOf<K>>> } = {
  none: NoJointFields,
  dowel: DowelFields,
  dovetail: DovetailFields,
}

const KIND_LABELS: { [K in JointKind]: string } = {
  none: 'None',
  dowel: 'Dowel pins',
  dovetail: 'Sliding dovetail',
}

const KINDS = Object.keys(KIND_LABELS) as JointKind[]

function isJointKind(s: string): s is JointKind {
  return (KINDS as string[]).includes(s)
}

function renderFields<K extends JointKind>(kind: K, value: JointOf<K>, onChange: (v: JointOf<K>) => void): ReactElement {
  const Fields: ComponentType<JointFieldsProps<JointOf<K>>> = JOINT_FORMS[kind]
  return <Fields key={kind} value={value} onChange={onChange} />
}

export function JointForm({ value, maleSide, onChange, onMaleSideChange }: JointFormProps): ReactElement {
  const kindId = useId()
  const sideId = useId()
  return (
    <div>
      <div className="field">
        <label htmlFor={kindId}>Kind</label>
        <select
          id={kindId}
          aria-label="Joint kind"
          value={value.kind}
          onChange={(e) => {
            const kind = e.target.value
            if (isJointKind(kind) && kind !== value.kind) onChange(DEFAULT_JOINTS[kind])
          }}
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {KIND_LABELS[k]}
            </option>
          ))}
        </select>
      </div>
      {renderFields(value.kind, value, onChange)}
      {value.kind !== 'none' && (
        <div className="field">
          <label htmlFor={sideId}>Male side</label>
          <select
            id={sideId}
            aria-label="Male side"
            value={maleSide}
            onChange={(e) => onMaleSideChange(e.target.value === 'upper' ? 'upper' : 'lower')}
          >
            <option value="lower">Lower cell</option>
            <option value="upper">Upper cell</option>
          </select>
        </div>
      )}
    </div>
  )
}
