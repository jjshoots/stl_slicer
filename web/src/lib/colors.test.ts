import { describe, expect, it } from 'vitest'
import { PALETTE, pieceColor } from './colors'

describe('colors', () => {
  it('has 12 distinct palette entries', () => {
    expect(PALETTE).toHaveLength(12)
    expect(new Set(PALETTE).size).toBe(12)
  })

  it('pieceColor wraps modulo 12', () => {
    expect(pieceColor(0)).toBe(PALETTE[0])
    expect(pieceColor(12)).toBe(PALETTE[0])
    expect(pieceColor(13)).toBe(PALETTE[1])
    expect(pieceColor(-1)).toBe(PALETTE[11])
  })
})
