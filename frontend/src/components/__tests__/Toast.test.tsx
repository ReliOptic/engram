// Tests for the Toast context provider.
// Covers: addToast displays the message, multiple toasts stack,
// auto-dismiss after 3 seconds, manual close removes the toast,
// and useToast outside the provider is a no-op (won't crash).

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { ToastProvider, useToast } from '../Toast'

function Trigger({ message, type = 'info' as const }: { message: string; type?: 'success' | 'error' | 'info' }) {
  const { addToast } = useToast()
  return <button onClick={() => addToast(message, type)}>fire-{message}</button>
}

describe('ToastProvider + useToast', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('displays a toast when addToast is called', () => {
    render(
      <ToastProvider>
        <Trigger message="hello" />
      </ToastProvider>
    )

    fireEvent.click(screen.getByText('fire-hello'))
    expect(screen.getByText('hello')).toBeInTheDocument()
  })

  it('stacks multiple toasts', () => {
    render(
      <ToastProvider>
        <Trigger message="first" />
        <Trigger message="second" />
      </ToastProvider>
    )

    fireEvent.click(screen.getByText('fire-first'))
    fireEvent.click(screen.getByText('fire-second'))

    expect(screen.getByText('first')).toBeInTheDocument()
    expect(screen.getByText('second')).toBeInTheDocument()
  })

  it('auto-dismisses after 3 seconds', () => {
    render(
      <ToastProvider>
        <Trigger message="bye" />
      </ToastProvider>
    )

    fireEvent.click(screen.getByText('fire-bye'))
    expect(screen.getByText('bye')).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(3100) })

    expect(screen.queryByText('bye')).not.toBeInTheDocument()
  })

  it('manual close button removes a single toast', () => {
    render(
      <ToastProvider>
        <Trigger message="A" />
        <Trigger message="B" />
      </ToastProvider>
    )

    fireEvent.click(screen.getByText('fire-A'))
    fireEvent.click(screen.getByText('fire-B'))

    // Each toast has a close button rendering "×"
    const closeBtns = screen.getAllByRole('button', { name: /×/ })
    expect(closeBtns).toHaveLength(2)

    fireEvent.click(closeBtns[0]) // close 'A'

    expect(screen.queryByText('A')).not.toBeInTheDocument()
    expect(screen.getByText('B')).toBeInTheDocument()
  })

  it('useToast outside a provider is a safe no-op', () => {
    function Standalone() {
      const { addToast } = useToast()
      return <button onClick={() => addToast('orphan')}>standalone</button>
    }

    expect(() => {
      render(<Standalone />)
      fireEvent.click(screen.getByText('standalone'))
    }).not.toThrow()
  })
})
