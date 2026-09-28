import type { Bounds, CellIndex, CutPlan, Vec3 } from '../api/types'

export function boundsCenter(b: Bounds): Vec3 {
  return [(b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, (b.min[2] + b.max[2]) / 2]
}

export function boundsSize(b: Bounds): Vec3 {
  return [b.max[0] - b.min[0], b.max[1] - b.min[1], b.max[2] - b.min[2]]
}

export function cellKey(cell: CellIndex): string {
  return `x${cell.i}_y${cell.j}_z${cell.k}`
}

function findCell(plan: CutPlan, cell: CellIndex) {
  return plan.cells.find((c) => c.index.i === cell.i && c.index.j === cell.j && c.index.k === cell.k)
}

/** Explode offset for a piece: (cell centre − plan centre) × factor. Zero if the cell is unknown. */
export function explodeOffset(cell: CellIndex, plan: CutPlan, factor: number): Vec3 {
  const c = findCell(plan, cell)
  if (!c) return [0, 0, 0]
  const cc = boundsCenter(c.bounds)
  const pc = boundsCenter(plan.bounds)
  return [(cc[0] - pc[0]) * factor, (cc[1] - pc[1]) * factor, (cc[2] - pc[2]) * factor]
}
