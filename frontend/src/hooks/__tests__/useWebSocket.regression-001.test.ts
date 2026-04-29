// Regression: ISSUE-002/003/007 — StrictMode WS double-mount cascade
// Found by /qa on 2026-04-12
// Report: .gstack/qa-reports/qa-report-engram-2026-04-12.md

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useWebSocket } from '../useWebSocket'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  readyState = 0
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  close() {
    if (this.readyState === 3) return
    this.readyState = 3
    if (this.onclose) {
      const handler = this.onclose
      setTimeout(() => handler(), 0)
    }
  }

  send() {}
  simulateOpen() { this.readyState = 1; this.onopen?.() }

  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
}

describe('useWebSocket — StrictMode resilience', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('no orphaned reconnects after unmount', () => {
    const { unmount } = renderHook(() => useWebSocket('ws://test'))

    // Record how many WS instances exist after initial mount
    // (may be 1 or 2 depending on StrictMode behavior)
    const countAfterMount = MockWebSocket.instances.length

    unmount()

    // Advance timers well past any reconnect delay (3s default)
    act(() => { vi.advanceTimersByTime(10000) })

    // The key assertion: no NEW connections were opened after unmount.
    // The old bug would create an extra WS here from the orphaned
    // reconnect timer that fired from WS1's onclose.
    expect(MockWebSocket.instances.length).toBe(countAfterMount)
  })

  it('reconnects after real server disconnect', async () => {
    renderHook(() => useWebSocket('ws://test'))
    // useWebSocket defers connect via queueMicrotask; flush it before accessing instances
    await act(async () => {})

    const activeWs = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    activeWs.simulateOpen()

    const countBefore = MockWebSocket.instances.length

    // Simulate server disconnect
    act(() => {
      activeWs.readyState = 3
      activeWs.onclose?.()
    })

    // After reconnect delay, a new WS should appear
    act(() => { vi.advanceTimersByTime(3500) })
    expect(MockWebSocket.instances.length).toBeGreaterThan(countBefore)
  })
})
