/** 12 evenly spaced hues; pieces are coloured by index modulo 12. */
export const PALETTE: readonly string[] = Array.from({ length: 12 }, (_, i) => hsl((i * 30 + 200) % 360, 65, 58))

function hsl(h: number, s: number, l: number): string {
  return `hsl(${h} ${s}% ${l}%)`
}

export function pieceColor(index: number): string {
  const n = PALETTE.length
  return PALETTE[((index % n) + n) % n]
}

export const SELECTED_EMISSIVE = '#ffffff'
export const PLANE_COLOR = '#4fa3ff'
export const CELL_COLOR = '#6a7a8a'
export const BED_COLOR = '#f2b134'
