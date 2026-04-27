// Tests for useSessions hook — covers fetch on mount, create / rename /
// delete, and graceful failure handling. fetch is stubbed via vi.stubGlobal.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useSessions, type Session } from '../useSessions'

function makeSession(overrides: Partial<Session> = {}): Session {
  return {
    session_id: 's-1',
    title: 'Initial',
    silo_account: 'ClientA',
    silo_tool: 'ProductA',
    silo_component: 'Module1',
    status: 'active',
    created_at: '2026-04-01T00:00:00Z',
    updated_at: '2026-04-01T00:00:00Z',
    message_count: 0,
    ...overrides,
  }
}

function jsonResponse(body: unknown, ok = true): Response {
  return {
    ok,
    json: async () => body,
  } as Response
}

describe('useSessions', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches active sessions on mount', async () => {
    const initial = [makeSession(), makeSession({ session_id: 's-2', title: 'Second' })]
    fetchMock.mockResolvedValueOnce(jsonResponse(initial))

    const { result } = renderHook(() => useSessions())

    await waitFor(() => expect(result.current.sessions).toHaveLength(2))
    expect(fetchMock).toHaveBeenCalledWith('/api/sessions?status=active')
    expect(result.current.loading).toBe(false)
  })

  it('createSession POSTs and prepends the result to state', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([])) // initial fetch
    const created = makeSession({ session_id: 's-new', title: 'Hello' })
    fetchMock.mockResolvedValueOnce(jsonResponse(created))

    const { result } = renderHook(() => useSessions())
    await waitFor(() => expect(result.current.loading).toBe(false))

    let returned: Session | null = null
    await act(async () => {
      returned = await result.current.createSession('Hello', {
        account: 'ClientA', tool: 'ProductA', component: 'Module1',
      })
    })

    expect(returned).toEqual(created)
    expect(result.current.sessions[0]).toEqual(created)

    const [url, init] = fetchMock.mock.calls[1]
    expect(url).toBe('/api/sessions')
    expect(init).toMatchObject({ method: 'POST' })
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      title: 'Hello',
      silo_account: 'ClientA',
      silo_tool: 'ProductA',
      silo_component: 'Module1',
    })
  })

  it('createSession returns null when backend rejects', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]))
    fetchMock.mockResolvedValueOnce(jsonResponse({}, false))

    const { result } = renderHook(() => useSessions())
    await waitFor(() => expect(result.current.loading).toBe(false))

    let returned: Session | null = null
    await act(async () => {
      returned = await result.current.createSession('X')
    })

    expect(returned).toBeNull()
    expect(result.current.sessions).toHaveLength(0)
  })

  it('deleteSession removes from state when backend confirms', async () => {
    const initial = [makeSession({ session_id: 's-1' }), makeSession({ session_id: 's-2' })]
    fetchMock.mockResolvedValueOnce(jsonResponse(initial))
    fetchMock.mockResolvedValueOnce(jsonResponse({}, true))

    const { result } = renderHook(() => useSessions())
    await waitFor(() => expect(result.current.sessions).toHaveLength(2))

    await act(async () => {
      await result.current.deleteSession('s-1')
    })

    expect(result.current.sessions.map((s) => s.session_id)).toEqual(['s-2'])
    expect(fetchMock).toHaveBeenCalledWith('/api/sessions/s-1', { method: 'DELETE' })
  })

  it('renameSession updates title in place', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([
      makeSession({ session_id: 's-1', title: 'Old' }),
    ]))
    fetchMock.mockResolvedValueOnce(jsonResponse({}, true))

    const { result } = renderHook(() => useSessions())
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))

    await act(async () => {
      await result.current.renameSession('s-1', 'New title')
    })

    expect(result.current.sessions[0].title).toBe('New title')

    const [url, init] = fetchMock.mock.calls[1]
    expect(url).toBe('/api/sessions/s-1')
    expect(init).toMatchObject({ method: 'PATCH' })
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ title: 'New title' })
  })

  it('rename does not mutate state if the API rejects', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([
      makeSession({ session_id: 's-1', title: 'Old' }),
    ]))
    fetchMock.mockResolvedValueOnce(jsonResponse({}, false))

    const { result } = renderHook(() => useSessions())
    await waitFor(() => expect(result.current.sessions).toHaveLength(1))

    await act(async () => {
      await result.current.renameSession('s-1', 'Should not stick')
    })

    expect(result.current.sessions[0].title).toBe('Old')
  })

  it('fetchSessions failure leaves sessions empty without throwing', async () => {
    fetchMock.mockRejectedValueOnce(new Error('network'))

    const { result } = renderHook(() => useSessions())

    // The hook swallows the error; loading should still settle to false
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.sessions).toEqual([])
  })
})
