import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ProjectSelector from './ProjectSelector'

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  }))
}

const PROJECTS = [
  { id: 'alpha12345678', name: 'Alpha' },
  { id: 'beta123456789', name: 'Beta' },
]

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => { resolve = res })
  return { promise, resolve }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('ProjectSelector project deletion', () => {
  it('names the project in confirmation and leaves it intact when cancelled', async () => {
    vi.stubGlobal('fetch', vi.fn(() => response(PROJECTS)))
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<ProjectSelector onSelect={vi.fn()} />)

    await screen.findByText('Alpha')
    await userEvent.click(screen.getByRole('button', { name: 'Delete Alpha' }))

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('Alpha'))
    expect(screen.getByText('Alpha')).toBeTruthy()
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('deletes through the scoped endpoint and removes only that project', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (!init?.method) return response(PROJECTS)
      expect(String(input)).toBe('/api/projects/alpha12345678')
      expect(init.method).toBe('DELETE')
      return response({ deleted: true })
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<ProjectSelector onSelect={vi.fn()} />)

    await screen.findByText('Alpha')
    await userEvent.click(screen.getByRole('button', { name: 'Delete Alpha' }))

    await waitFor(() => expect(screen.queryByText('Alpha')).toBeNull())
    expect(screen.getByText('Beta')).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('surfaces a busy or server rejection and keeps the project', async () => {
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => (
      init?.method === 'DELETE'
        ? response({ error: 'Project is currently running' }, 409)
        : response(PROJECTS)
    )))
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<ProjectSelector onSelect={vi.fn()} />)

    await screen.findByText('Alpha')
    await userEvent.click(screen.getByRole('button', { name: 'Delete Alpha' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Project is currently running')
    expect(screen.getByText('Alpha')).toBeTruthy()
  })

  it('locks all project actions while one delete is pending', async () => {
    let resolveDelete: ((value: Response) => void) | undefined
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      if (!init?.method) return response(PROJECTS)
      return new Promise<Response>((resolve) => { resolveDelete = resolve })
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<ProjectSelector onSelect={vi.fn()} />)

    await screen.findByText('Alpha')
    await userEvent.click(screen.getByRole('button', { name: 'Delete Alpha' }))

    expect(screen.getByRole('button', { name: 'Delete Beta' })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Beta beta1234/i })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Delete Beta' }))
    expect(fetchMock).toHaveBeenCalledTimes(2)

    resolveDelete?.(new Response(JSON.stringify({ deleted: true }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }))
    await waitFor(() => expect(screen.queryByText('Alpha')).toBeNull())
  })

  it('creates through the truthful API helper and selects only after success', async () => {
    const onSelect = vi.fn()
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => (
      init?.method === 'POST'
        ? response({ id: 'new123456789', name: 'New Film' })
        : response([])
    )))
    render(<ProjectSelector onSelect={onSelect} />)

    fireEvent.change(screen.getByPlaceholderText('Enter film title...'), {
      target: { value: 'New Film' },
    })
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith('new123456789'))
  })

  it('awaits project loading and locks create/select/delete actions until it settles', async () => {
    const selection = deferred<void>()
    const onSelect = vi.fn(() => selection.promise)
    vi.stubGlobal('fetch', vi.fn(() => response(PROJECTS)))
    render(<ProjectSelector onSelect={onSelect} />)

    await screen.findByText('Alpha')
    fireEvent.change(screen.getByRole('textbox', { name: 'Film title' }), {
      target: { value: 'Another Film' },
    })
    expect(screen.getByRole('button', { name: 'Create' })).not.toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: /Alpha alpha123/i }))

    expect(screen.getByText('Opening…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete Beta' })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Beta beta1234/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Create' })).toBeDisabled()

    selection.resolve()
    await waitFor(() => expect(screen.queryByText('Opening…')).toBeNull())
  })

  it('surfaces an existing-project load failure and re-enables a retry', async () => {
    const onSelect = vi.fn(async () => { throw new Error('Project details unavailable') })
    vi.stubGlobal('fetch', vi.fn(() => response(PROJECTS)))
    render(<ProjectSelector onSelect={onSelect} />)

    await screen.findByText('Alpha')
    const alphaButton = screen.getByRole('button', { name: /Alpha alpha123/i })
    await userEvent.click(alphaButton)

    expect(await screen.findByRole('alert')).toHaveTextContent('Project details unavailable')
    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(alphaButton).not.toBeDisabled()
  })

  it('keeps a created project available for retry when create succeeds but opening fails', async () => {
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => (
      init?.method === 'POST'
        ? response({ id: 'new123456789', name: 'New Film' })
        : response([])
    )))
    const onSelect = vi.fn(async () => { throw new Error('Created project could not be loaded') })
    render(<ProjectSelector onSelect={onSelect} />)

    fireEvent.change(screen.getByPlaceholderText('Enter film title...'), {
      target: { value: 'New Film' },
    })
    await userEvent.click(screen.getByRole('button', { name: 'Create' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Created project could not be loaded')
    expect(screen.getByText('New Film')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /New Film new12345/i })).not.toBeDisabled()
  })
})
