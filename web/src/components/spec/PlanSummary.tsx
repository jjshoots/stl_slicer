import type { ReactElement } from 'react'
import type { Axis, Bounds, CutPlan, MeshAsset, SliceWarning, Vec3 } from '../../api/types'
import { formatMm, formatNumberList, formatSize, formatVolume, humanizeCode } from '../../lib/format'

export interface PlanSummaryProps {
  model: MeshAsset | null
  plan: CutPlan | null
  error: string | null
}

const AXES: Axis[] = ['x', 'y', 'z']

function boundsSize(b: Bounds): Vec3 {
  return [b.max[0] - b.min[0], b.max[1] - b.min[1], b.max[2] - b.min[2]]
}

function Warnings({ items }: { items: SliceWarning[] }): ReactElement | null {
  if (items.length === 0) return null
  return (
    <ul className="warnings">
      {items.map((w, i) => (
        <li key={`${w.code}-${w.subject ?? ''}-${i}`}>
          <span className="code">{humanizeCode(w.code)}</span>
          {w.message}
          {w.subject && <span className="muted"> ({w.subject})</span>}
        </li>
      ))}
    </ul>
  )
}

export function PlanSummary({ model, plan, error }: PlanSummaryProps): ReactElement {
  if (model === null) return <p className="muted">Upload a model to see the cut plan.</p>
  return (
    <div>
      <dl className="stats">
        <dt>file</dt>
        <dd className="mono">{model.filename}</dd>
        <dt>triangles</dt>
        <dd>{model.triangle_count.toLocaleString()}</dd>
        <dt>size (mm)</dt>
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
          </dl>
          <Warnings items={plan.warnings ?? []} />
        </>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  )
}

function FragmentCuts({ axis, positions }: { axis: Axis; positions: number[] }): ReactElement {
  const title = positions.length > 0 ? positions.map((p) => formatMm(p)).join(', ') : 'none'
  return (
    <>
      <dt>{axis} cuts</dt>
      <dd title={title}>
        {positions.length}
        {positions.length > 0 && <span className="mono muted"> @ {formatNumberList(positions.map((p) => Number(p.toFixed(1))))}</span>}
      </dd>
    </>
  )
}
