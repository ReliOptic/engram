// Tests for ChatTimeline:
// - Empty state when no messages
// - Renders agent and user bubbles with their labels
// - Highlights @mentions inside content
// - Shows the contributionType tag and addressedTo arrow
// - Renders the silo badge on user messages
// - "Agents are thinking..." indicator appears when isProcessing

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ChatTimeline } from '../ChatTimeline'
import type { AgentMessage } from '../../types'

function msg(over: Partial<AgentMessage> = {}): AgentMessage {
  return {
    id: 'm-1',
    agent: 'analyzer',
    contributionType: 'NEW_EVIDENCE',
    content: 'Root cause identified',
    addressedTo: 'You',
    timestamp: '2026-04-27T10:00:00Z',
    ...over,
  }
}

describe('ChatTimeline', () => {
  it('renders empty state when there are no messages', () => {
    render(<ChatTimeline messages={[]} />)
    expect(
      screen.getByText(/Start a conversation by describing your issue/i),
    ).toBeInTheDocument()
  })

  it('renders an agent bubble with name + tag + addressedTo', () => {
    render(
      <ChatTimeline messages={[msg({ agent: 'analyzer', addressedTo: 'Finder' })]} />,
    )

    expect(screen.getByText('Analyzer')).toBeInTheDocument()
    expect(screen.getByText('NEW_EVIDENCE')).toBeInTheDocument()
    expect(screen.getByText('→ @Finder')).toBeInTheDocument()
    expect(screen.getByText('Root cause identified')).toBeInTheDocument()
  })

  it('renders a user bubble with You label and silo badge', () => {
    render(
      <ChatTimeline
        messages={[
          msg({
            id: 'u-1',
            agent: 'user',
            content: 'Why does Module1 drift after PM?',
            silo: { account: 'ClientA', tool: 'ProductA', component: 'Module1' },
          }),
        ]}
      />,
    )

    expect(screen.getByText('You')).toBeInTheDocument()
    expect(
      screen.getByText('ClientA / ProductA / Module1'),
    ).toBeInTheDocument()
  })

  it('highlights @mentions inside content', () => {
    render(
      <ChatTimeline
        messages={[msg({ content: 'cc @Finder please look at case 0847' })]}
      />,
    )

    // The mention is rendered in a span styled differently — verify it appears verbatim
    expect(screen.getByText('@Finder')).toBeInTheDocument()
    // Surrounding text is split; the leading fragment is also present
    expect(screen.getByText(/please look at case/i)).toBeInTheDocument()
  })

  it('renders multiple bubbles in order', () => {
    render(
      <ChatTimeline
        messages={[
          msg({ id: 'a', agent: 'analyzer', content: 'first' }),
          msg({ id: 'f', agent: 'finder', content: 'second' }),
          msg({ id: 'r', agent: 'reviewer', content: 'third' }),
        ]}
      />,
    )

    expect(screen.getByText('first')).toBeInTheDocument()
    expect(screen.getByText('second')).toBeInTheDocument()
    expect(screen.getByText('third')).toBeInTheDocument()
    expect(screen.getByText('Analyzer')).toBeInTheDocument()
    expect(screen.getByText('Finder')).toBeInTheDocument()
    expect(screen.getByText('Reviewer')).toBeInTheDocument()
  })

  it('shows the thinking indicator when isProcessing', () => {
    render(<ChatTimeline messages={[msg()]} isProcessing />)
    expect(screen.getByText('Agents are thinking...')).toBeInTheDocument()
  })

  it('does NOT show the thinking indicator when not processing', () => {
    render(<ChatTimeline messages={[msg()]} />)
    expect(screen.queryByText('Agents are thinking...')).not.toBeInTheDocument()
  })

  it('omits the contribution-type tag when contributionType is empty', () => {
    render(
      <ChatTimeline messages={[msg({ contributionType: '' })]} />,
    )
    // Should still show the agent name; no NEW_EVIDENCE tag this time
    expect(screen.getByText('Analyzer')).toBeInTheDocument()
    expect(screen.queryByText('NEW_EVIDENCE')).not.toBeInTheDocument()
  })
})
