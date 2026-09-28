import { describe, expect, it } from 'vitest'
import { formatLength, formatMm, formatNumberList, formatPercent, formatSize, formatVolume, humanizeCode, parseNumberList } from './format'

describe('format', () => {
  it('formatVolume switches to cm³ at 1000 mm³', () => {
    expect(formatVolume(999)).toBe('999.0 mm³')
    expect(formatVolume(1000)).toBe('1.00 cm³')
    expect(formatVolume(12345)).toBe('12.35 cm³')
    expect(formatVolume(Number.NaN)).toBe('—')
  })

  it('formatLength appends mm', () => {
    expect(formatLength(3.14159)).toBe('3.1 mm')
    expect(formatLength(2, 0)).toBe('2 mm')
    expect(formatLength(0)).toBe('0.0 mm')
    expect(formatLength(Number.NaN)).toBe('—')
    expect(formatMm).toBe(formatLength)
  })

  it('formatSize renders W × D × H with a single trailing unit', () => {
    expect(formatSize([1, 2.25, 3])).toBe('1.0 × 2.3 × 3.0 mm')
    expect(formatSize([36, 36, 36])).toBe('36.0 × 36.0 × 36.0 mm')
    expect(formatSize([220, 220, 250], 0)).toBe('220 × 220 × 250 mm')
    expect(formatSize([1, Number.NaN, 3])).toBe('—')
  })

  it('formatPercent clamps to [0, 100]', () => {
    expect(formatPercent(0.425)).toBe('43%')
    expect(formatPercent(-0.2)).toBe('0%')
    expect(formatPercent(1.7)).toBe('100%')
  })

  it('parseNumberList drops blanks and junk', () => {
    expect(parseNumberList('10, 20.5 ;abc  -3,,')).toEqual([10, 20.5, -3])
    expect(parseNumberList('   ')).toEqual([])
    expect(formatNumberList([1, 2.5])).toBe('1, 2.5')
  })

  it('humanizeCode', () => {
    expect(humanizeCode('cell_oversize')).toBe('Cell oversize')
    expect(humanizeCode('no_contact_for_joint')).toBe('No contact for joint')
  })
})
