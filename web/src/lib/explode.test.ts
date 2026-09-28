import { describe, expect, it } from 'vitest'
import type { CutPlan } from '../api/types'
import { boundsCenter, boundsSize, cellKey, explodeOffset } from './explode'

const plan: CutPlan = {
  bounds: { min: [0, 0, 0], max: [20, 10, 10] },
  limits: { max_cell: [10, 10, 10], min_cell: 1 },
  cuts: { x: [10], y: [], z: [] },
  cells: [
    { index: { i: 0, j: 0, k: 0 }, bounds: { min: [0, 0, 0], max: [10, 10, 10] } },
    { index: { i: 1, j: 0, k: 0 }, bounds: { min: [10, 0, 0], max: [20, 10, 10] } },
  ],
  interfaces: [],
  warnings: [],
}

describe('explode', () => {
  it('boundsCenter and boundsSize', () => {
    const b = { min: [-2, 0, 4], max: [2, 6, 10] } as CutPlan['bounds']
    expect(boundsCenter(b)).toEqual([0, 3, 7])
    expect(boundsSize(b)).toEqual([4, 6, 6])
  })

  it('cellKey', () => {
    expect(cellKey({ i: 1, j: 2, k: 3 })).toBe('x1_y2_z3')
  })

  it('offsets by (cell centre - plan centre) x factor', () => {
    expect(explodeOffset({ i: 0, j: 0, k: 0 }, plan, 1)).toEqual([-5, 0, 0])
    expect(explodeOffset({ i: 1, j: 0, k: 0 }, plan, 0.5)).toEqual([2.5, 0, 0])
  })

  it('returns zeros for an unknown cell', () => {
    expect(explodeOffset({ i: 5, j: 0, k: 0 }, plan, 1)).toEqual([0, 0, 0])
  })

  it('returns zeros for factor 0', () => {
    expect(explodeOffset({ i: 1, j: 0, k: 0 }, plan, 0).map(Math.abs)).toEqual([0, 0, 0])
  })
})
