// Tests for AgentPanel — three agent cards with status badges.

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AgentPanel } from '../AgentPanel'

describe('AgentPanel', () => {
  it('renders all three agents with names and descriptions', () => {
    render(<AgentPanel />)
    expect(screen.getByText('Analyzer')).toBeInTheDocument()
    expect(screen.getByText('Finder')).toBeInTheDocument()
    expect(screen.getByText('Reviewer')).toBeInTheDocument()
    expect(screen.getByText('Root cause analysis')).toBeInTheDocument()
    expect(screen.getByText('Knowledge search')).toBeInTheDocument()
    expect(screen.getByText('Procedure validation')).toBeInTheDocument()
  })

  it('defaults all agents to Idle when no statuses passed', () => {
    render(<AgentPanel />)
    expect(screen.getAllByText('Idle')).toHaveLength(3)
  })

  it('overrides individual agent statuses', () => {
    render(
      <AgentPanel
        agentStatuses={{
          analyzer: 'thinking',
          finder: 'done',
          reviewer: 'waiting',
        }}
      />,
    )
    expect(screen.getByText('Thinking...')).toBeInTheDocument()
    expect(screen.getByText('Done')).toBeInTheDocument()
    expect(screen.getByText('Waiting')).toBeInTheDocument()
    expect(screen.queryByText('Idle')).not.toBeInTheDocument()
  })

  it('renders the heading "Agents"', () => {
    render(<AgentPanel />)
    expect(screen.getByText('Agents')).toBeInTheDocument()
  })

  it('keeps unspecified agents at Idle while overriding others', () => {
    render(<AgentPanel agentStatuses={{ analyzer: 'processing' }} />)
    expect(screen.getByText('Processing...')).toBeInTheDocument()
    // Finder + Reviewer still Idle
    expect(screen.getAllByText('Idle')).toHaveLength(2)
  })
})
