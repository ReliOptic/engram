// Tests for the Skeleton primitive.

import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Skeleton } from '../Skeleton'

describe('Skeleton', () => {
  it('renders a single placeholder by default', () => {
    const { container } = render(<Skeleton />)
    const divs = container.querySelectorAll('div')
    // Single skeleton => one wrapper-less div
    expect(divs.length).toBe(1)
  })

  it('renders `count` placeholders when count > 1', () => {
    const { container } = render(<Skeleton count={3} />)
    // Wrapper + 3 children = 4 divs total
    expect(container.querySelectorAll('div').length).toBe(4)
  })

  it('applies custom width / height / borderRadius', () => {
    const { container } = render(
      <Skeleton width="100px" height="22px" borderRadius="6px" />,
    )
    const el = container.querySelector('div')!
    expect(el.style.width).toBe('100px')
    expect(el.style.height).toBe('22px')
    expect(el.style.borderRadius).toBe('6px')
  })
})
