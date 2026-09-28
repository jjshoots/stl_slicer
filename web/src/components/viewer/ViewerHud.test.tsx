import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ViewerHud } from './ViewerHud'

const bed = { x: 220, y: 220, z: 250 }

describe('ViewerHud', () => {
  it('renders nothing without a model', () => {
    const { container } = render(<ViewerHud bed={bed} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows the model size in mm before a result exists', () => {
    const { container } = render(<ViewerHud modelSize={[72, 36, 36.25]} bed={bed} />)
    expect(container.textContent).toBe('model 72.0 × 36.0 × 36.3 mm')
    expect(container.textContent).not.toContain('bed')
  })

  it('adds the piece count and bed size once sliced', () => {
    const { container } = render(<ViewerHud modelSize={[72, 36, 36]} pieceCount={4} bed={bed} />)
    expect(container.textContent).toBe('model 72.0 × 36.0 × 36.0 mm4 pieces · bed 220 × 220 × 250 mm')
  })

  it('is non-interactive', () => {
    const { container } = render(<ViewerHud modelSize={[1, 1, 1]} bed={bed} />)
    expect(container.querySelector('.viewer-hud')?.getAttribute('aria-hidden')).toBe('true')
  })
})
