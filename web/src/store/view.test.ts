import { beforeEach, describe, expect, it } from 'vitest'
import { useViewStore } from './view'

const store = () => useViewStore.getState()

beforeEach(() => {
  useViewStore.setState({ ...useViewStore.getInitialState(), hidden: new Set<string>() })
})

describe('view store', () => {
  it('toggleHidden adds then removes', () => {
    store().toggleHidden('a')
    expect(store().hidden.has('a')).toBe(true)
    store().toggleHidden('a')
    expect(store().hidden.has('a')).toBe(false)
  })

  it('toggleHidden produces a new Set', () => {
    const before = store().hidden
    store().toggleHidden('a')
    expect(store().hidden).not.toBe(before)
  })

  it('select sets and clears the selection', () => {
    store().select('a')
    expect(store().selected).toBe('a')
    store().select(null)
    expect(store().selected).toBeNull()
  })

  it('setExplode clamps to [0, 1]', () => {
    store().setExplode(0.4)
    expect(store().explode).toBe(0.4)
    store().setExplode(2)
    expect(store().explode).toBe(1)
    store().setExplode(-1)
    expect(store().explode).toBe(0)
  })

  it('resetPieces clears hidden and selected', () => {
    store().toggleHidden('a')
    store().select('b')
    store().setExplode(0.5)
    store().resetPieces()
    expect(store().hidden.size).toBe(0)
    expect(store().selected).toBeNull()
    expect(store().explode).toBe(0.5)
  })
})
