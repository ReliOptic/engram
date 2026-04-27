// Tests for APIKeySettings — covers Test/Save flows for OpenRouter/OpenAI
// API keys, status indicator transitions, validation guards, and the
// "untested" reset on input change.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { APIKeySettings } from '../APIKeySettings'
import { ToastProvider } from '../../Toast'

function renderWith() {
  return render(
    <ToastProvider>
      <APIKeySettings />
    </ToastProvider>,
  )
}

function jsonResponse(body: unknown, ok = true): Response {
  return { ok, json: async () => body } as Response
}

describe('APIKeySettings', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => vi.restoreAllMocks())

  it('renders cards for both OpenRouter and OpenAI keys', () => {
    renderWith()
    expect(screen.getByText('OpenRouter API Key')).toBeInTheDocument()
    expect(screen.getByText('OpenAI API Key')).toBeInTheDocument()
    // Both rows start "Not tested"
    expect(screen.getAllByText('Not tested')).toHaveLength(2)
  })

  it('Test button is a no-op (toast only) when the key field is empty', async () => {
    renderWith()
    const [openrouterTest] = screen.getAllByText('Test')
    fireEvent.click(openrouterTest)
    expect(fetchMock).not.toHaveBeenCalled()
    // The toast surfaces the validation error
    await waitFor(() =>
      expect(screen.getByText('Please enter an API key first')).toBeInTheDocument(),
    )
  })

  it('Test posts to /api/settings/test-connection and marks Valid on ok', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }))
    renderWith()

    const [openrouterInput] = screen.getAllByPlaceholderText(/Enter openrouter API key/i)
    fireEvent.change(openrouterInput, { target: { value: 'sk-or-test' } })

    fireEvent.click(screen.getAllByText('Test')[0])

    await waitFor(() => screen.getByText('Valid'))

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/settings/test-connection')
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      provider: 'openrouter', api_key: 'sk-or-test',
    })
  })

  it('Test marks Invalid when the API rejects the key', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: false, error: 'bad key' }))
    renderWith()

    const inputs = screen.getAllByPlaceholderText(/API key/)
    fireEvent.change(inputs[1], { target: { value: 'sk-bad' } })  // OpenAI row
    fireEvent.click(screen.getAllByText('Test')[1])

    await waitFor(() => screen.getByText('Invalid'))
    // Invalid + 1 still-untested = expected
    expect(screen.getAllByText('Not tested')).toHaveLength(1)
  })

  it('Test marks Invalid on a network error', async () => {
    fetchMock.mockRejectedValueOnce(new Error('offline'))
    renderWith()

    const inputs = screen.getAllByPlaceholderText(/API key/)
    fireEvent.change(inputs[0], { target: { value: 'sk-x' } })
    fireEvent.click(screen.getAllByText('Test')[0])

    await waitFor(() => screen.getByText('Invalid'))
  })

  it('typing in the field resets status back to Not tested', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }))
    renderWith()

    const inputs = screen.getAllByPlaceholderText(/API key/)
    fireEvent.change(inputs[0], { target: { value: 'sk-1' } })
    fireEvent.click(screen.getAllByText('Test')[0])
    await waitFor(() => screen.getByText('Valid'))

    // Edit the field — status should reset
    fireEvent.change(inputs[0], { target: { value: 'sk-2' } })
    expect(screen.queryByText('Valid')).not.toBeInTheDocument()
    expect(screen.getAllByText('Not tested')).toHaveLength(2)
  })

  it('Save POSTs to /api/settings/save-api-key and toasts on success', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }))
    renderWith()

    const inputs = screen.getAllByPlaceholderText(/API key/)
    fireEvent.change(inputs[0], { target: { value: 'sk-save-me' } })

    fireEvent.click(screen.getAllByText('Save')[0])

    await waitFor(() =>
      expect(screen.getByText('OpenRouter API Key saved to .env')).toBeInTheDocument(),
    )

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/settings/save-api-key')
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      provider: 'openrouter', api_key: 'sk-save-me',
    })
  })

  it('Save is disabled while the key field is empty', () => {
    renderWith()
    const saveButtons = screen.getAllByText('Save') as unknown as HTMLButtonElement[]
    expect(saveButtons[0].disabled).toBe(true)
    expect(saveButtons[1].disabled).toBe(true)
  })
})
