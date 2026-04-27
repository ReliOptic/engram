// Feature tests for useWebSocket beyond the existing StrictMode regression.
// Covers: status transitions, message parsing (JSON + plain text fallback),
// send() respects readyState, disconnect() schedules a reconnect, error → close.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useWebSocket } from '../useWebSocket'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  readyState = 0
  sent: string[] = []
  closed = false
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    if (this.closed) return
    this.closed = true
    this.readyState = 3
    this.onclose?.()
  }

  simulateOpen() {
    this.readyState = 1
    this.onopen?.()
  }

  simulateMessage(data: string) {
    this.onmessage?.({ data } as MessageEvent)
  }

  simulateError() {
    this.onerror?.()
  }

  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSING = 2
  static readonly CLOSED = 3
}

describe('useWebSocket — feature behaviour', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('starts in connecting state, then transitions to connected on open', () => {
    const { result } = renderHook(() => useWebSocket('ws://test'))

    expect(result.current.status).toBe('connecting')

    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    act(() => ws.simulateOpen())

    expect(result.current.status).toBe('connected')
  })

  it('parses JSON messages into lastMessage', () => {
    const { result } = renderHook(() => useWebSocket('ws://test'))
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    act(() => ws.simulateOpen())

    act(() => {
      ws.simulateMessage(JSON.stringify({
        type: 'agent_message',
        payload: { agent: 'analyzer', content: 'hello' },
      }))
    })

    expect(result.current.lastMessage).toEqual({
      type: 'agent_message',
      payload: { agent: 'analyzer', content: 'hello' },
    })
  })

  it('falls back to wrapping plain text into agent_message', () => {
    const { result } = renderHook(() => useWebSocket('ws://test'))
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    act(() => ws.simulateOpen())

    act(() => ws.simulateMessage('not json'))

    expect(result.current.lastMessage).toEqual({
      type: 'agent_message',
      payload: { content: 'not json' },
    })
  })

  it('send() forwards JSON when socket is OPEN', () => {
    const { result } = renderHook(() => useWebSocket('ws://test'))
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    act(() => ws.simulateOpen())

    act(() => {
      result.current.send({
        type: 'user_message',
        payload: { content: 'hi' },
      })
    })

    expect(ws.sent).toEqual([
      JSON.stringify({ type: 'user_message', payload: { content: 'hi' } }),
    ])
  })

  it('send() is a no-op while still connecting', () => {
    const { result } = renderHook(() => useWebSocket('ws://test'))
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    // Note: NOT simulating open — readyState remains 0

    act(() => {
      result.current.send({ type: 'user_message', payload: { content: 'hi' } })
    })

    expect(ws.sent).toEqual([])
  })

  it('disconnect() closes current socket and schedules a reconnect', () => {
    const { result } = renderHook(() => useWebSocket('ws://test'))
    const initialWs = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    act(() => initialWs.simulateOpen())

    const countBefore = MockWebSocket.instances.length

    act(() => result.current.disconnect())
    expect(initialWs.closed).toBe(true)
    expect(result.current.status).toBe('disconnected')

    // Reconnect timer is scheduled at 1000ms in disconnect()
    act(() => { vi.advanceTimersByTime(1100) })
    expect(MockWebSocket.instances.length).toBeGreaterThan(countBefore)
  })

  it('on error, the socket is closed (which then triggers reconnect)', () => {
    renderHook(() => useWebSocket('ws://test'))
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
    act(() => ws.simulateOpen())

    act(() => ws.simulateError())

    expect(ws.closed).toBe(true)
  })
})
