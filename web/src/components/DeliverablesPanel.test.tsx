import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectNoAxeViolations } from '../test/a11y-setup'
import DeliverablesPanel from './DeliverablesPanel'

function response(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('DeliverablesPanel', () => {
  it('shows immutable version evidence and packages plus downloads in one click', async () => {
    const artifact = {
      artifact_id: 'av-000000000001-aaaaaaaaaaaa',
      sequence: 2,
      version: 2,
      logical_name: 'final/master',
      sha256: 'a'.repeat(64),
      byte_size: 1024,
      media_type: 'video/mp4',
      provider: 'runway',
      model: 'gen4_turbo',
      distribution_class: 'client_deliverable',
      reproducibility: {
        status: 'provider_replay_only',
        bit_exact: false,
        note: 'Provider replay can differ.',
      },
    }
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return response({
          sha256: 'b'.repeat(64),
          byte_size: 2_000_000,
          artifact_ids: [artifact.artifact_id],
          entry_count: 3,
          filename: 'project-1-deliverables.zip',
          download_url: `/api/projects/project-1/deliverables/package/download?sha256=${'b'.repeat(64)}`,
        }, 201)
      }
      return response({
        current: [artifact],
        records: [artifact],
        has_more: false,
        next_before_sequence: null,
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const user = userEvent.setup()

    const { container } = render(<DeliverablesPanel projectId="project-1" />)

    expect(await screen.findByText('final/master')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'v2 · current' })).toBeInTheDocument()
    expect(screen.getByText('Provider replay · not bit-exact')).toBeInTheDocument()
    expect(screen.getAllByText('sha256:aaaaaaaa').length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: 'Package selected versions' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/projects/project-1/deliverables/package',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ artifact_ids: [artifact.artifact_id] }),
      }),
    ))
    expect(await screen.findByRole('status')).toHaveTextContent('Verified package ready')
    expect(screen.getByText(/project-1-deliverables.zip/)).toBeInTheDocument()
    expect(click).toHaveBeenCalledTimes(1)
    await expectNoAxeViolations(container)
  })

  it('keeps packaging failure truthful and does not start a download', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) =>
      init?.method === 'POST'
        ? response({ error: 'no client deliverables are available' }, 400)
        : response({
          current: [],
          records: [],
          has_more: false,
          next_before_sequence: null,
        }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const user = userEvent.setup()

    render(<DeliverablesPanel projectId="project-1" />)
    await user.click(await screen.findByRole('button', { name: 'Package client deliverables' }))

    expect(await screen.findByRole('status')).toHaveTextContent('no client deliverables')
    expect(click).not.toHaveBeenCalled()
  })

  it('lets the operator select and package an archived immutable version', async () => {
    const current = {
      artifact_id: 'av-current',
      sequence: 3,
      version: 2,
      logical_name: 'final/master',
      sha256: 'c'.repeat(64),
      byte_size: 2048,
      media_type: 'video/mp4',
      provider: null,
      model: 'ffmpeg-final-assembly',
      distribution_class: 'client_deliverable',
      reproducibility: {
        status: 'recipe_captured',
        bit_exact: false,
        note: 'Recipe only.',
      },
    }
    const archived = {
      ...current,
      artifact_id: 'av-archived',
      sequence: 1,
      version: 1,
      sha256: 'a'.repeat(64),
    }
    const internal = {
      ...current,
      artifact_id: 'av-internal',
      sequence: 2,
      version: 1,
      logical_name: 'shots/shot-1/motion/take-1',
      distribution_class: 'internal',
      sha256: 'b'.repeat(64),
    }
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return response({
          sha256: 'd'.repeat(64),
          byte_size: 1000,
          artifact_ids: [archived.artifact_id],
          entry_count: 3,
          filename: 'project-1-deliverables.zip',
          download_url: '/download',
        }, 201)
      }
      return response({
        current: [current, internal],
        records: [current, internal, archived],
        has_more: false,
        next_before_sequence: null,
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const user = userEvent.setup()

    render(<DeliverablesPanel projectId="project-1" />)

    const version = await screen.findByRole('combobox', { name: 'Version for final/master' })
    expect(version).toHaveValue(current.artifact_id)
    await user.selectOptions(version, archived.artifact_id)
    expect(screen.getAllByText('sha256:aaaaaaaa').length).toBeGreaterThan(0)
    expect(screen.getByText(/shots\/shot-1\/motion\/take-1/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Package selected versions' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/projects/project-1/deliverables/package',
      expect.objectContaining({
        body: JSON.stringify({ artifact_ids: [archived.artifact_id] }),
      }),
    ))
  })
})
