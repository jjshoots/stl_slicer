import { describe, expect, it } from 'vitest'
import { planePad, quadExtent } from './planes'

describe('quadExtent', () => {
  it('pads thin plate planes by 5% of the largest extent', () => {
    const size: [number, number, number] = [1500, 627, 15]
    expect(planePad(size)).toBeCloseTo(75)
    const [xw, xh] = quadExtent('x', size)
    expect(xw).toBeCloseTo(15 + 150)
    expect(xh).toBeCloseTo(627 + 150)
    const [yw, yh] = quadExtent('y', size)
    expect(yw).toBeCloseTo(1500 + 150)
    expect(yh).toBeCloseTo(15 + 150)
    const [zw, zh] = quadExtent('z', size)
    expect(zw).toBeCloseTo(1500 + 150)
    expect(zh).toBeCloseTo(627 + 150)
  })

  it('pads a large cube by 5% on each side', () => {
    const size: [number, number, number] = [400, 400, 400]
    for (const axis of ['x', 'y', 'z'] as const) {
      const [w, h] = quadExtent(axis, size)
      expect(w).toBeCloseTo(400 * 1.1)
      expect(h).toBeCloseTo(400 * 1.1)
    }
  })

  it('uses the 10 mm minimum pad for small plans', () => {
    const size: [number, number, number] = [20, 20, 20]
    expect(quadExtent('z', size)).toEqual([40, 40])
  })
})
