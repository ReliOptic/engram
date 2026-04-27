// Tests for HistorySidebar — session list with grouping, search,
// rename, delete, new chat, and current selection highlighting.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { HistorySidebar } from '../HistorySidebar'
import type { Session } from '../../hooks/useSessions'

function session(over: Partial<Session> = {}): Session {
  return {
    session_id: 's-1',
    title: 'Hello',
    silo_account: 'ClientA',
    silo_tool: 'ProductA',
    silo_component: 'Module1',
    status: 'active',
    created_at: '2026-04-27T10:00:00Z',
    updated_at: '2026-04-27T10:00:00Z',
    message_count: 3,
    ...over,
  }
}

describe('HistorySidebar', () => {
  beforeEach(() => {
    // Pin "now" so date grouping is deterministic.
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-27T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('renders empty state when no sessions exist', () => {
    render(
      <HistorySidebar
        sessions={[]}
        currentSessionId={null}
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(
      screen.getByText('No conversations yet. Start chatting!'),
    ).toBeInTheDocument()
  })

  it('shows "No results found." when search filters everything out', () => {
    render(
      <HistorySidebar
        sessions={[session({ title: 'Hello world' })]}
        currentSessionId={null}
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    fireEvent.change(screen.getByPlaceholderText('Search chats...'), {
      target: { value: 'doesnotmatch' },
    })
    expect(screen.getByText('No results found.')).toBeInTheDocument()
  })

  it('groups sessions by Today / Yesterday / Last 7 Days / Older', () => {
    const sessions: Session[] = [
      session({ session_id: 't', title: 'Today chat', updated_at: '2026-04-27T11:00:00Z' }),
      session({ session_id: 'y', title: 'Yesterday chat', updated_at: '2026-04-26T11:00:00Z' }),
      session({ session_id: 'w', title: 'Last week chat', updated_at: '2026-04-22T11:00:00Z' }),
      session({ session_id: 'o', title: 'Old chat', updated_at: '2026-03-01T11:00:00Z' }),
    ]
    render(
      <HistorySidebar
        sessions={sessions}
        currentSessionId={null}
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText('Today')).toBeInTheDocument()
    expect(screen.getByText('Yesterday')).toBeInTheDocument()
    expect(screen.getByText('Last 7 Days')).toBeInTheDocument()
    expect(screen.getByText('Older')).toBeInTheDocument()
  })

  it('clicking New Chat fires onNewChat', () => {
    const onNewChat = vi.fn()
    render(
      <HistorySidebar
        sessions={[]}
        currentSessionId={null}
        onNewChat={onNewChat}
        onSelect={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByText('New Chat'))
    expect(onNewChat).toHaveBeenCalledOnce()
  })

  it('clicking a session item fires onSelect', () => {
    const onSelect = vi.fn()
    render(
      <HistorySidebar
        sessions={[session({ session_id: 's-x', title: 'Pick me' })]}
        currentSessionId={null}
        onNewChat={vi.fn()}
        onSelect={onSelect}
      />,
    )
    fireEvent.click(screen.getByText('Pick me'))
    expect(onSelect).toHaveBeenCalledWith('s-x')
  })

  it('renders the message-count and silo metadata', () => {
    render(
      <HistorySidebar
        sessions={[session({ message_count: 5, silo_account: 'AcmeCo' })]}
        currentSessionId={null}
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText('5 msgs · AcmeCo')).toBeInTheDocument()
  })

  it('singular "1 msg" with no silo', () => {
    render(
      <HistorySidebar
        sessions={[session({ message_count: 1, silo_account: '' })]}
        currentSessionId={null}
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    expect(screen.getByText('1 msg')).toBeInTheDocument()
  })

  it('search filters by title (case-insensitive)', () => {
    render(
      <HistorySidebar
        sessions={[
          session({ session_id: 'a', title: 'Bug in Module1' }),
          session({ session_id: 'b', title: 'Feature request' }),
        ]}
        currentSessionId={null}
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
      />,
    )
    fireEvent.change(screen.getByPlaceholderText('Search chats...'), {
      target: { value: 'BUG' },
    })
    expect(screen.getByText('Bug in Module1')).toBeInTheDocument()
    expect(screen.queryByText('Feature request')).not.toBeInTheDocument()
  })

  it('rename: opens menu, switches to input, submits on Enter', () => {
    const onRename = vi.fn()
    render(
      <HistorySidebar
        sessions={[session({ session_id: 's-r', title: 'Old' })]}
        currentSessionId={null}
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
        onRename={onRename}
      />,
    )
    fireEvent.click(screen.getByText('···'))      // open menu
    fireEvent.click(screen.getByText('Rename'))   // start renaming

    const input = screen.getByDisplayValue('Old') as HTMLInputElement
    fireEvent.change(input, { target: { value: 'Brand new' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    expect(onRename).toHaveBeenCalledWith('s-r', 'Brand new')
  })

  it('rename Escape cancels without calling onRename', () => {
    const onRename = vi.fn()
    render(
      <HistorySidebar
        sessions={[session({ session_id: 's-r', title: 'Old' })]}
        currentSessionId={null}
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
        onRename={onRename}
      />,
    )
    fireEvent.click(screen.getByText('···'))
    fireEvent.click(screen.getByText('Rename'))
    const input = screen.getByDisplayValue('Old')
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onRename).not.toHaveBeenCalled()
  })

  it('delete: confirms via window.confirm before calling onDelete', () => {
    const onDelete = vi.fn()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(
      <HistorySidebar
        sessions={[session({ session_id: 's-d', title: 'Bye' })]}
        currentSessionId={null}
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
        onDelete={onDelete}
      />,
    )
    fireEvent.click(screen.getByText('···'))
    fireEvent.click(screen.getByText('Delete'))
    expect(confirmSpy).toHaveBeenCalled()
    expect(onDelete).toHaveBeenCalledWith('s-d')
  })

  it('delete: aborts when window.confirm returns false', () => {
    const onDelete = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(
      <HistorySidebar
        sessions={[session({ session_id: 's-d' })]}
        currentSessionId={null}
        onNewChat={vi.fn()}
        onSelect={vi.fn()}
        onDelete={onDelete}
      />,
    )
    fireEvent.click(screen.getByText('···'))
    fireEvent.click(screen.getByText('Delete'))
    expect(onDelete).not.toHaveBeenCalled()
  })
})
