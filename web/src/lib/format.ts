import type { JointSpec } from '../api/types'

/** A length in millimetres with a sensible number of decimals, e.g. `12.5 mm`. */
export function formatLength(mm: number, digits = 1): string {
  if (!Number.isFinite(mm)) return '—'
  return `${mm.toFixed(digits)} mm`
}

/** @deprecated alias of {@link formatLength}. */
export const formatMm = formatLength

/** Volume in mm³ or cm³ depending on magnitude. */
export function formatVolume(mm3: number): string {
  if (!Number.isFinite(mm3)) return '—'
  if (Math.abs(mm3) >= 1000) return `${(mm3 / 1000).toFixed(2)} cm³`
  return `${mm3.toFixed(1)} mm³`
}

/** A W × D × H size in millimetres, e.g. `36.0 × 36.0 × 36.0 mm`. */
export function formatSize(size: readonly [number, number, number], digits = 1): string {
  if (!size.every((s) => Number.isFinite(s))) return '—'
  return `${size.map((s) => s.toFixed(digits)).join(' × ')} mm`
}

export function formatPercent(fraction: number): string {
  return `${Math.round(Math.min(1, Math.max(0, fraction)) * 100)}%`
}

/** Parse a comma/space separated list of numbers; ignores blanks; invalid tokens are dropped. */
export function parseNumberList(text: string): number[] {
  return text
    .split(/[\s,;]+/)
    .filter((t) => t.length > 0)
    .map(Number)
    .filter((n) => Number.isFinite(n))
}

export function formatNumberList(values: readonly number[]): string {
  return values.join(', ')
}

/** Turn a warning code like `cell_oversize` into `Cell oversize`. */
export function humanizeCode(code: string): string {
  const s = code.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** Trim trailing zeros: `29.5 mm`, `123 mm`. */
function jointNum(v: number): string {
  return String(Number(v.toFixed(1)))
}

function jointMm(v: number): string {
  return `${jointNum(v)} mm`
}

/**
 * Compact one-line joint summary, e.g. `jigsaw · head 29.5 mm · neck 16.2 mm · depth 38.4 mm · spacing 123 mm`.
 * Used for the resolved (auto-sized) joint on the plan.
 */
export function formatJointSummary(joint: JointSpec): string {
  switch (joint.kind) {
    case 'none':
      return 'none'
    case 'dowel':
      return ['dowel', `diameter ${jointMm(joint.diameter)}`, `depth ${jointMm(joint.depth)}`, `spacing ${jointMm(joint.spacing)}`].join(' · ')
    case 'dovetail':
      return [
        'dovetail',
        `head ${jointMm(joint.head_width)}`,
        `neck ${jointMm(joint.neck_width)}`,
        `depth ${jointMm(joint.depth)}`,
        `spacing ${jointMm(joint.spacing)}`,
      ].join(' · ')
    case 'jigsaw':
      return [
        'jigsaw',
        `head ${jointMm(joint.head_diameter)}`,
        `neck ${jointMm(joint.neck_width)}`,
        `depth ${jointMm(joint.depth)}`,
        `spacing ${jointMm(joint.spacing)}`,
      ].join(' · ')
    case 'tab':
    case 'hexpin':
      return [joint.kind, `width ${jointMm(joint.width)}`, `depth ${jointMm(joint.depth)}`, `spacing ${jointMm(joint.spacing)}`].join(' · ')
    case 'tongue':
      return ['tongue', `width ${jointMm(joint.width)}`, `depth ${jointMm(joint.depth)}`].join(' · ')
    case 'magnet':
      return ['magnet', `Ø${jointNum(joint.diameter)} × ${jointMm(joint.height)}`, `spacing ${jointMm(joint.spacing)}`].join(' · ')
  }
}
