// Tests for the ChatInput component:
// - Initial cascading dropdowns are populated from /api/config/dropdowns
// - Typing + Enter calls onSend with the trimmed message and silo
// - Empty / whitespace messages don't trigger onSend
// - Shift+Enter does NOT submit
// - Send button is disabled until text is present
// - isProcessing replaces Send with Stop
// - Falls back to mock dropdowns when the fetch fails

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ChatInput } from '../ChatInput'

const sampleDropdowns = {
  accounts: {
    'ClientA': {
      tools: {
        'ProductA': { components: ['Module1', 'Module2'] },
      },
    },
  },
}

function jsonResponse(body: unknown, ok = true): Response {
  return { ok, json: async () => body } as Response
}

function setupFetch(impl: ReturnType<typeof vi.fn>) {
  vi.stubGlobal('fetch', impl)
}

describe('ChatInput', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('populates dropdowns from /api/config/dropdowns and submits via Send', async () => {
    setupFetch(vi.fn().mockResolvedValueOnce(jsonResponse(sampleDropdowns)))

    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)

    // Wait until cascading dropdowns initialise
    await waitFor(() => {
      expect(screen.getByDisplayValue('ClientA')).toBeInTheDocument()
    })
    expect(screen.getByDisplayValue('ProductA')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Module1')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Describe your issue...'), {
      target: { value: '  hello there  ' },
    })
    fireEvent.click(screen.getByText('Send'))

    expect(onSend).toHaveBeenCalledWith(
      'hello there',  // trimmed
      { account: 'ClientA', tool: 'ProductA', component: 'Module1' },
      undefined,
    )
  })

  it('Enter submits, Shift+Enter does not', async () => {
    setupFetch(vi.fn().mockResolvedValueOnce(jsonResponse(sampleDropdowns)))

    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    await waitFor(() => screen.getByDisplayValue('ClientA'))

    const textarea = screen.getByPlaceholderText('Describe your issue...')
    fireEvent.change(textarea, { target: { value: 'msg' } })

    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true })
    expect(onSend).not.toHaveBeenCalled()

    fireEvent.keyDown(textarea, { key: 'Enter' })
    expect(onSend).toHaveBeenCalledOnce()
  })

  it('does not submit when message is empty / whitespace', async () => {
    setupFetch(vi.fn().mockResolvedValueOnce(jsonResponse(sampleDropdowns)))

    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    await waitFor(() => screen.getByDisplayValue('ClientA'))

    const sendBtn = screen.getByText('Send') as HTMLButtonElement
    expect(sendBtn.disabled).toBe(true)

    fireEvent.change(screen.getByPlaceholderText('Describe your issue...'), {
      target: { value: '   ' },
    })
    fireEvent.click(sendBtn)
    expect(onSend).not.toHaveBeenCalled()
  })

  it('shows Stop instead of Send while isProcessing, wired to onStop', async () => {
    setupFetch(vi.fn().mockResolvedValueOnce(jsonResponse(sampleDropdowns)))

    const onStop = vi.fn()
    render(
      <ChatInput onSend={vi.fn()} isProcessing onStop={onStop} />
    )
    await waitFor(() => screen.getByDisplayValue('ClientA'))

    expect(screen.queryByText('Send')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('Stop'))
    expect(onStop).toHaveBeenCalledOnce()
  })

  it('falls back to mock dropdowns when /api/config/dropdowns fails', async () => {
    setupFetch(vi.fn().mockRejectedValueOnce(new Error('network')))

    render(<ChatInput onSend={vi.fn()} />)

    await waitFor(() => {
      expect(screen.getByDisplayValue('Demo Client')).toBeInTheDocument()
    })
    expect(screen.getByDisplayValue('Product A')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Module 1')).toBeInTheDocument()
  })

  it('changing the Account resets Tool/Component to defaults', async () => {
    const big = {
      accounts: {
        'A1': { tools: { 'T1': { components: ['C1'] } } },
        'A2': { tools: { 'T2': { components: ['C2', 'C3'] } } },
      },
    }
    setupFetch(vi.fn().mockResolvedValueOnce(jsonResponse(big)))

    const onSend = vi.fn()
    render(<ChatInput onSend={onSend} />)
    await waitFor(() => screen.getByDisplayValue('A1'))

    fireEvent.change(screen.getByDisplayValue('A1'), { target: { value: 'A2' } })

    await waitFor(() => screen.getByDisplayValue('A2'))
    expect(screen.getByDisplayValue('T2')).toBeInTheDocument()
    expect(screen.getByDisplayValue('C2')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Describe your issue...'), {
      target: { value: 'hi' },
    })
    fireEvent.click(screen.getByText('Send'))

    expect(onSend).toHaveBeenCalledWith(
      'hi', { account: 'A2', tool: 'T2', component: 'C2' }, undefined,
    )
  })
})
