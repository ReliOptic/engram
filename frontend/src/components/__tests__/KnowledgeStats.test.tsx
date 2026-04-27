// Tests for KnowledgeStats — fetches /api/knowledge/stats and renders
// loading / empty / populated views.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { KnowledgeStats } from '../KnowledgeStats'

function jsonResponse(body: unknown): Response {
  return { ok: true, json: async () => body } as Response
}

describe('KnowledgeStats', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => vi.restoreAllMocks())

  it('renders the loading shimmer until fetch resolves', async () => {
    let resolve!: (v: Response) => void
    fetchMock.mockReturnValueOnce(new Promise((r) => (resolve = r)))

    const { container } = render(<KnowledgeStats />)
    // Shimmer div is the first non-heading element
    expect(screen.getByText('Knowledge Base')).toBeInTheDocument()
    expect(container.querySelector('div[style*="shimmer"]')).toBeTruthy()

    resolve(jsonResponse({
      collections: {}, total_chunks: 0,
      cases: { total: 0, recent_7d: 0 }, sessions_total: 0,
    }))
    await waitFor(() =>
      expect(screen.queryByText('Knowledge Base')).toBeInTheDocument(),
    )
  })

  it('renders empty CTA when there are no chunks', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      collections: {}, total_chunks: 0,
      cases: { total: 0, recent_7d: 0 }, sessions_total: 0,
    }))
    render(<KnowledgeStats />)
    await waitFor(() =>
      expect(
        screen.getByText(/No knowledge data yet/i),
      ).toBeInTheDocument(),
    )
  })

  it('renders the totals + per-collection counts when populated', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      collections: {
        manuals: 1234,
        case_records: 56,
        weekly: 78,
        traces: 9,
      },
      total_chunks: 1377,
      cases: { total: 12, recent_7d: 3 },
      sessions_total: 8,
    }))
    render(<KnowledgeStats />)

    await waitFor(() => screen.getByText('1,377'))
    expect(screen.getByText('total chunks')).toBeInTheDocument()
    expect(screen.getByText('1,234')).toBeInTheDocument()  // manuals
    expect(screen.getByText('56')).toBeInTheDocument()     // case_records
    expect(screen.getByText('78')).toBeInTheDocument()     // weekly
    expect(screen.getByText('9')).toBeInTheDocument()      // traces
  })

  it('shows activity rows when cases or sessions exist', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      collections: { manuals: 5 },
      total_chunks: 5,
      cases: { total: 12, recent_7d: 3 },
      sessions_total: 8,
    }))
    render(<KnowledgeStats />)

    await waitFor(() => screen.getByText('Activity'))
    expect(screen.getByText('Total cases resolved')).toBeInTheDocument()
    expect(screen.getByText('+3')).toBeInTheDocument()
    expect(screen.getByText('Support sessions')).toBeInTheDocument()
  })

  it('renders nothing when the fetch errors out', async () => {
    fetchMock.mockRejectedValueOnce(new Error('boom'))
    const { container } = render(<KnowledgeStats />)
    // After the fetch settles, loading=false and data=null → returns null
    await waitFor(() => {
      // shimmer div should be gone
      expect(container.querySelector('div[style*="shimmer"]')).toBeFalsy()
    })
    // The component returns null after a failure, so the heading is not present
    expect(screen.queryByText('Knowledge Base')).not.toBeInTheDocument()
  })

  it('cases.recent_7d=0 renders "0" not "+0"', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({
      collections: { manuals: 1 },
      total_chunks: 1,
      cases: { total: 4, recent_7d: 0 },
      sessions_total: 1,
    }))
    render(<KnowledgeStats />)
    await waitFor(() => screen.getByText('Activity'))
    expect(screen.queryByText('+0')).not.toBeInTheDocument()
  })
})
