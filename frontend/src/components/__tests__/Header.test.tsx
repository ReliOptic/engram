// Tests for the Header — WS status indicator, sync badge logic,
// and the settings link.

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Header } from '../Header'

function renderHeader(props: Parameters<typeof Header>[0]) {
  return render(
    <MemoryRouter>
      <Header {...props} />
    </MemoryRouter>,
  )
}

describe('Header', () => {
  it('shows the wsStatus text and a tooltip on the dot', () => {
    renderHeader({ wsStatus: 'connected' })
    expect(screen.getByText('connected')).toBeInTheDocument()
    expect(
      screen.getByTitle('WebSocket: connected'),
    ).toBeInTheDocument()
  })

  it('renders the brand and a link to /settings', () => {
    renderHeader({ wsStatus: 'connecting' })
    expect(screen.getByText('Engram')).toBeInTheDocument()
    const link = screen.getByTitle('Settings (Ctrl+,)')
    expect(link.getAttribute('href')).toBe('/settings')
  })

  it('hides the sync badge when sync is disabled or undefined', () => {
    renderHeader({ wsStatus: 'connected' })
    // None of the sync titles render
    expect(screen.queryByTitle(/Sync:/)).toBeNull()

    renderHeader({ wsStatus: 'connected', syncStatus: 'disabled' })
    expect(screen.queryByTitle(/Sync:/)).toBeNull()
  })

  it('renders the synced badge with correct title', () => {
    renderHeader({ wsStatus: 'connected', syncStatus: 'synced' })
    expect(screen.getByTitle('Sync: up to date')).toBeInTheDocument()
  })

  it('shows a pending badge with the count', () => {
    renderHeader({ wsStatus: 'connected', syncStatus: 'pending', syncPending: 3 })
    const badge = screen.getByTitle('Sync: 3 pending')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveTextContent('↑3')
  })

  it('shows the offline badge with the right symbol', () => {
    renderHeader({ wsStatus: 'disconnected', syncStatus: 'offline' })
    const badge = screen.getByTitle('Sync: server offline')
    expect(badge).toHaveTextContent('⊘')
  })
})
