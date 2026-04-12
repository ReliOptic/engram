// Regression: Keyboard shortcuts Ctrl+K and Ctrl+B were not wired up
// Found by /qa on 2026-04-12
// Report: .gstack/qa-reports/qa-report-zemas-2026-04-12.md
//
// The useKeyboardShortcuts hook was defined with all handlers but
// ChatPage only passed onNewChat and onStop. The remaining handlers
// (onFocusInput, onToggleLeftSidebar) were undefined, causing Ctrl+K
// and Ctrl+B to silently no-op via optional chaining.

import { describe, it, expect, vi, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useKeyboardShortcuts } from '../useKeyboardShortcuts'

function fireKey(key: string, ctrlKey = true) {
  window.dispatchEvent(new KeyboardEvent('keydown', { key, ctrlKey, bubbles: true }))
}

describe('useKeyboardShortcuts', () => {
  afterEach(() => vi.restoreAllMocks())

  it('Ctrl+K calls onFocusInput', () => {
    const onFocusInput = vi.fn()
    renderHook(() => useKeyboardShortcuts({ onFocusInput }))

    fireKey('k')
    expect(onFocusInput).toHaveBeenCalledOnce()
  })

  it('Ctrl+B calls onToggleLeftSidebar', () => {
    const onToggleLeftSidebar = vi.fn()
    renderHook(() => useKeyboardShortcuts({ onToggleLeftSidebar }))

    fireKey('b')
    expect(onToggleLeftSidebar).toHaveBeenCalledOnce()
  })

  it('Ctrl+N calls onNewChat', () => {
    const onNewChat = vi.fn()
    renderHook(() => useKeyboardShortcuts({ onNewChat }))

    fireKey('n')
    expect(onNewChat).toHaveBeenCalledOnce()
  })

  it('Escape calls onStop', () => {
    const onStop = vi.fn()
    renderHook(() => useKeyboardShortcuts({ onStop }))

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(onStop).toHaveBeenCalledOnce()
  })

  it('does not call undefined handlers', () => {
    // No handlers provided — should not throw
    expect(() => {
      renderHook(() => useKeyboardShortcuts({}))
      fireKey('k')
      fireKey('b')
      fireKey('n')
    }).not.toThrow()
  })
})
