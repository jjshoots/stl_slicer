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
