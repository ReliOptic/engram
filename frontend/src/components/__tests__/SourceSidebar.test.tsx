// Tests for SourceSidebar — pure presentational component.

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SourceSidebar } from '../SourceSidebar'
import type { SourceRef } from '../../types'

function src(over: Partial<SourceRef> = {}): SourceRef {
  return {
    id: 's-1',
    title: 'Manual ch.8.3',
    type: 'manual',
    relevance: 0.873,
    ...over,
  }
}

describe('SourceSidebar', () => {
  it('renders nothing when sources is empty', () => {
    const { container } = render(<SourceSidebar sources={[]} />)
    expect(container.firstChild).toBeNull()
  })

  it('renders the heading and the items', () => {
    render(<SourceSidebar sources={[src(), src({ id: 's-2', title: 'Case 0847', type: 'case', relevance: 0.42 })]} />)
    expect(screen.getByText('Sources Referenced')).toBeInTheDocument()
    expect(screen.getByText('Manual ch.8.3')).toBeInTheDocument()
    expect(screen.getByText('Case 0847')).toBeInTheDocument()
  })

  it('rounds relevance to integer percent', () => {
    render(<SourceSidebar sources={[src({ relevance: 0.873 })]} />)
    // Manual · 87% match
    expect(screen.getByText(/87% match/)).toBeInTheDocument()
  })

  it('uses the correct icon per type', () => {
    render(
      <SourceSidebar sources={[
        src({ id: '1', type: 'manual', title: 'M' }),
        src({ id: '2', type: 'case', title: 'C' }),
        src({ id: '3', type: 'weekly', title: 'W' }),
      ]} />
    )
    // Icons are emoji text — easiest to find via their containing text presence
    expect(screen.getByText('📘')).toBeInTheDocument()
    expect(screen.getByText('📋')).toBeInTheDocument()
    expect(screen.getByText('📊')).toBeInTheDocument()
  })

  it('falls back to a default icon for unknown types', () => {
    // Cast around the union type to simulate an unexpected value from the API
    const odd = src({ id: 'x', type: 'pdf' as unknown as SourceRef['type'], title: 'X' })
    render(<SourceSidebar sources={[odd]} />)
    expect(screen.getByText('📄')).toBeInTheDocument()
  })
})
