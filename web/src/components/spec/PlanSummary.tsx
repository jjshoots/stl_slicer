import type { ReactElement } from 'react'
import type { Axis, Bounds, CutPlan, JointSpec, MeshAsset, SliceWarning, Vec3 } from '../../api/types'
import { formatJointSummary, formatLength, formatSize, formatVolume, humanizeCode } from '../../lib/format'

export interface PlanSummaryProps {
  model: MeshAsset | null
  plan: CutPlan | null
  error: string | null
  /** The spec's current joint; the resolved line shows only while it is auto-sized. */
  joint?: JointSpec
}

const AXES: Axis[] = ['x', 'y', 'z']

function boundsSize(b: Bounds): Vec3 {
  return [b.max[0] - b.min[0], b.max[1] - b.min[1], b.max[2] - b.min[2]]
}

/** Axis subjects (`x` from CELL_OVERSIZE on an excluded axis) read better upper-cased; piece ids stay verbatim. */
function formatSubject(subject: string): string {
  return (AXES as string[]).includes(subject) ? `${subject.toUpperCase()} axis` : subject
}

function Warnings({ items }: { items: SliceWarning[] }): ReactElement | null {
  if (items.length === 0) return null
  return (
    <ul className="warnings">
      {items.map((w, i) => (
        <li key={`${w.code}-${w.subject ?? ''}-${i}`}>
          <span className="code">{humanizeCode(w.code)}</span>
          {w.message}
          {w.subject && <span className="muted"> ({formatSubject(w.subject)})</span>}
        </li>
      ))}
    </ul>
  )
}

export function PlanSummary({ model, plan, error, joint }: PlanSummaryProps): ReactElement {
  const autoJoint = joint !== undefined && joint.kind !== 'none' && joint.auto === true
  const resolved = plan?.resolved_joint ?? null
  if (model === null) return <p className="muted">Upload a model to see the cut plan.</p>
  return (
    <div>
      <dl className="stats">
        <dt>file</dt>
        <dd className="mono">{model.filename}</dd>
        <dt>triangles</dt>
        <dd>{model.triangle_count.toLocaleString()}</dd>
        <dt>size</dt>
        <dd>{formatSize(boundsSize(model.bounds))}</dd>
        <dt>volume</dt>
        <dd>{formatVolume(model.volume)}</dd>
      </dl>
      <Warnings items={model.warnings ?? []} />
      {plan && (
        <>
          <dl className="stats" style={{ marginTop: 8 }}>
            <dt>cells (upper bound on pieces)</dt>
            <dd>{plan.cells.length}</dd>
            {AXES.map((axis) => (
              <FragmentCuts key={axis} axis={axis} positions={plan.cuts[axis] ?? []} />
            ))}
            <dt>interfaces</dt>
            <dd>{plan.interfaces.length}</dd>
            {autoJoint && resolved && (
              <>
                <dt>joint</dt>
                <dd>{formatJointSummary(resolved)}</dd>
              </>
            )}
          </dl>
          <Warnings items={plan.warnings ?? []} />
        </>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}

/** `2 @ 36.0, 72.0 mm` -- positions are model-frame millimetres. */
export function formatCutPositions(positions: readonly number[]): string {
  return `${positions.map((p) => p.toFixed(1)).join(', ')} mm`
}

function FragmentCuts({ axis, positions }: { axis: Axis; positions: number[] }): ReactElement {
  const title = positions.length > 0 ? positions.map((p) => formatLength(p)).join(', ') : 'none'
  return (
    <>
      <dt>{axis} cuts</dt>
      <dd title={title}>
        {positions.length}
        {positions.length > 0 && <span className="mono muted"> @ {formatCutPositions(positions)}</span>}
      </dd>
    </>
  )
}
