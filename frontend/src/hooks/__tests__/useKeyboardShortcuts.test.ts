// Feature tests covering shortcut paths the regression file doesn't:
// Ctrl+. toggles right sidebar, Cmd+N (Mac) is treated like Ctrl+N,
// non-shortcut keys are ignored, unmount removes the listener.

import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useKeyboardShortcuts } from '../useKeyboardShortcuts'

function fireKey(key: string, opts: { ctrlKey?: boolean; metaKey?: boolean } = {}) {
  window.dispatchEvent(
    new KeyboardEvent('keydown', { key, ctrlKey: opts.ctrlKey, metaKey: opts.metaKey, bubbles: true })
  )
}

describe('useKeyboardShortcuts — feature coverage', () => {
  afterEach(() => vi.restoreAllMocks())

  it('Ctrl+. calls onToggleRightSidebar', () => {
    const onToggleRightSidebar = vi.fn()
    renderHook(() => useKeyboardShortcuts({ onToggleRightSidebar }))

    fireKey('.', { ctrlKey: true })
    expect(onToggleRightSidebar).toHaveBeenCalledOnce()
  })

  it('treats Cmd (metaKey) the same as Ctrl on macOS', () => {
    const onNewChat = vi.fn()
    renderHook(() => useKeyboardShortcuts({ onNewChat }))

    fireKey('n', { metaKey: true })
    expect(onNewChat).toHaveBeenCalledOnce()
  })

  it('plain N (no modifier) does NOT trigger onNewChat', () => {
    const onNewChat = vi.fn()
    renderHook(() => useKeyboardShortcuts({ onNewChat }))

    fireKey('n')  // no ctrl/meta
    expect(onNewChat).not.toHaveBeenCalled()
  })

  it('unrelated keys do nothing', () => {
    const handlers = {
      onNewChat: vi.fn(), onFocusInput: vi.fn(),
      onToggleLeftSidebar: vi.fn(), onToggleRightSidebar: vi.fn(),
      onStop: vi.fn(),
    }
    renderHook(() => useKeyboardShortcuts(handlers))

    fireKey('a', { ctrlKey: true })
    fireKey('z', { ctrlKey: true })
    fireKey('Enter')

    for (const fn of Object.values(handlers)) {
      expect(fn).not.toHaveBeenCalled()
    }
  })

  it('removes the listener on unmount', () => {
    const onNewChat = vi.fn()
    const { unmount } = renderHook(() => useKeyboardShortcuts({ onNewChat }))

    unmount()
    fireKey('n', { ctrlKey: true })
    expect(onNewChat).not.toHaveBeenCalled()
  })

  it('Ctrl+, navigates to /settings', () => {
    // Stub window.location.href via a real assignment intercept.
    const originalLocation = window.location
    let assignedHref = ''
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        get href() { return assignedHref },
        set href(v: string) { assignedHref = v },
      },
    })

    renderHook(() => useKeyboardShortcuts({}))
    fireKey(',', { ctrlKey: true })

    expect(assignedHref).toBe('/settings')

    Object.defineProperty(window, 'location', {
      configurable: true,
      value: originalLocation,
    })
  })
})
