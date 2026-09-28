import type { Axis, Vec3 } from '../api/types'

/** Minimum padding (mm) added on each side of a cut-plane quad. */
export const PLANE_MIN_PAD = 10
/** Padding as a fraction of the largest plan extent. */
export const PLANE_PAD_FRACTION = 0.05

/** Padding applied on each side of a cut-plane quad: max(5% of the largest extent, 10 mm). */
export function planePad(size: Vec3): number {
  return Math.max(PLANE_PAD_FRACTION * Math.max(...size), PLANE_MIN_PAD)
}

/**
 * Width/height of the cut-plane quad for `axis`, in the plane geometry's local XY after rotation
 * (x-cut: [z, y], y-cut: [x, z], z-cut: [x, y]). Padded on both sides so thin plans (e.g. a
 * 15 mm plate) still show visible planes.
 */
export function quadExtent(axis: Axis, size: Vec3): [number, number] {
  const [sx, sy, sz] = size
  const pad = 2 * planePad(size)
  if (axis === 'x') return [sz + pad, sy + pad]
  if (axis === 'y') return [sx + pad, sz + pad]
  return [sx + pad, sy + pad]
}
