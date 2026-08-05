import { useState } from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectNoAxeViolations } from '../../../test/a11y-setup'
import type { GpuWorkerStatus, GpuWorkersResponse } from '../../../types/project'
import { ImageSection } from './ImageSection'
import { GpuWorkersSection } from './GpuWorkersSection'

function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    text: vi.fn(async () => JSON.stringify(payload)),
  } as unknown as Response
}

const SNAPSHOT: GpuWorkersResponse = {
  checked_at: '2026-08-05T04:05:06Z',
  workers: [
    {
      role: 'image',
      label: 'Image worker',
      configured: true,
      dedicated: false,
      state: 'reachable',
      message: 'Service answered, but its image node contract is incomplete.',
      gpu_name: 'NVIDIA GeForce RTX 5070 Ti',
      vram_total_gib: 16,
      vram_free_gib: 12.25,
      running: 1,
      pending: 2,
      missing_node_classes: ['ExampleRequiredImageNode'],
    },
    {
      role: 'performance',
      label: 'Performance worker',
      configured: true,
      dedicated: true,
      state: 'ready',
      message: 'LivePortrait node and model contract passed.',
    },
  ],
}

const READY_SNAPSHOT: GpuWorkersResponse = {
  checked_at: '2026-08-06T01:02:03Z',
  workers: [{
    role: 'image',
    label: 'Image worker',
    configured: true,
    dedicated: false,
    state: 'ready',
    message: 'Local FLUX.2 execution and benchmark contracts passed.',
    startup_ready: true,
    execution_proven: true,
    benchmark_state: 'passed',
  }],
}

function ReadinessHarness() {
  const [imageWorker, setImageWorker] = useState<GpuWorkerStatus | null>(
    READY_SNAPSHOT.workers[0] ?? null,
  )
  return (
    <>
      <ImageSection
        s={{ identity_backend: 'gemini_multiref' }}
        config={null}
        imageWorker={imageWorker}
        update={vi.fn()}
      />
      <GpuWorkersSection onImageWorker={setImageWorker} />
    </>
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('GpuWorkersSection', () => {
  it('fetches on mount and distinguishes reachable from contract-ready', async () => {
    let resolveFetch: ((value: Response) => void) | undefined
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { resolveFetch = resolve }))
    vi.stubGlobal('fetch', fetchMock)

    render(<GpuWorkersSection />)

    expect(screen.getByText('Checking GPU workers').closest('[role="status"]')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Refresh GPU worker status' })).toBeDisabled()
    expect(fetchMock).toHaveBeenCalledWith('/api/runtime/gpu-workers', undefined)

    resolveFetch?.(response({
      ...SNAPSHOT,
      // Even if a future backend accidentally adds sensitive implementation
      // fields, the component renders only the explicit safe projection.
      endpoint_url: 'http://private-worker:8189',
      api_token: 'do-not-render',
    }))

    expect(await screen.findByText('Reachable, not ready')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('NVIDIA GeForce RTX 5070 Ti')).toBeInTheDocument()
    expect(screen.getByText('16.0 GiB')).toBeInTheDocument()
    expect(screen.getByText('12.3 GiB')).toBeInTheDocument()
    expect(screen.getByText('LivePortrait node and model contract passed.')).toBeInTheDocument()
    expect(screen.queryByText('http://private-worker:8189')).toBeNull()
    expect(screen.queryByText('do-not-render')).toBeNull()
    expect(screen.getByText(/Image worker: Reachable, not ready; Performance worker: Ready/).closest('[role="status"]')).not.toBeNull()
  })

  it('keeps the last confirmed snapshot visible during a manual refresh', async () => {
    let resolveRefresh: ((value: Response) => void) | undefined
    const refreshed: GpuWorkersResponse = {
      checked_at: '2026-08-05T04:06:07Z',
      workers: [{
        ...SNAPSHOT.workers[1],
        state: 'offline',
        message: 'The worker did not answer before the readiness timeout.',
      }],
    }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(SNAPSHOT))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveRefresh = resolve }))
    vi.stubGlobal('fetch', fetchMock)

    render(<GpuWorkersSection />)
    expect(await screen.findByText('Ready')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Refresh GPU worker status' }))

    expect(screen.getByRole('button', { name: 'Refresh GPU worker status' })).toBeDisabled()
    expect(screen.getByText('Refreshing GPU workers')).toBeInTheDocument()
    expect(screen.getByText('LivePortrait node and model contract passed.')).toBeInTheDocument()

    resolveRefresh?.(response(refreshed))
    expect(await screen.findByText('Offline')).toBeInTheDocument()
    expect(screen.getByText('The worker did not answer before the readiness timeout.')).toBeInTheDocument()
    expect(screen.getByText(/Performance worker: Offline/).closest('[role="status"]')).not.toBeNull()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })

  it('renders a blocked shared image capability without implying readiness', async () => {
    const shared: GpuWorkersResponse = {
      checked_at: '2026-08-06T01:02:03Z',
      workers: [
        {
          ...SNAPSHOT.workers[0],
          dedicated: false,
          state: 'blocked',
          message: 'Local image execution proof is incomplete.',
          running: 0,
          pending: 0,
          missing_node_classes: undefined,
        },
        {
          ...SNAPSHOT.workers[1],
          dedicated: false,
        },
      ],
    }
    vi.stubGlobal('fetch', vi.fn(async () => response(shared)))

    const { container } = render(<GpuWorkersSection />)

    expect(await screen.findByText('Blocked')).toBeInTheDocument()
    expect(screen.getByText('Local image execution proof is incomplete.')).toBeInTheDocument()
    expect(screen.getAllByText(/Shared/)).toHaveLength(2)
    expect(screen.getByText(/Image worker: Blocked; Performance worker: Ready/).closest('[role="status"]')).not.toBeNull()
    expect(screen.queryByText('Reachable, not ready')).toBeNull()
    await expectNoAxeViolations(container)
  })

  it('surfaces a failed request as an alert, then allows an explicit retry', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ error: 'Health probe timed out' }, false, 503))
      .mockResolvedValueOnce(response(SNAPSHOT))
    vi.stubGlobal('fetch', fetchMock)

    render(<GpuWorkersSection />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'GPU worker status unavailable: Health probe timed out',
    )
    const refresh = screen.getByRole('button', { name: 'Refresh GPU worker status' })
    expect(refresh).toBeEnabled()

    fireEvent.click(refresh)
    expect(await screen.findByText('Reachable, not ready')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('fails closed on a malformed success body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ workers: [{ state: 'ready' }] })))

    render(<GpuWorkersSection />)

    expect(await screen.findByRole('alert')).toHaveTextContent('returned an invalid response')
    expect(screen.queryByText('Ready')).toBeNull()
  })

  it.each([
    ['failed', response({ error: 'Health probe timed out' }, false, 503)],
    ['malformed', response({ workers: [{ state: 'ready' }] })],
  ])('revokes local image authority when a refresh is %s', async (_case, refreshResponse) => {
    let resolveRefresh: ((value: Response) => void) | undefined
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(READY_SNAPSHOT))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveRefresh = resolve }))
    vi.stubGlobal('fetch', fetchMock)

    render(<ReadinessHarness />)
    const localBackend = screen.getByDisplayValue('local_flux2_klein')
    await waitFor(() => expect(localBackend).toBeEnabled())

    fireEvent.click(screen.getByRole('button', { name: 'Refresh GPU worker status' }))
    await waitFor(() => expect(localBackend).toBeDisabled())

    resolveRefresh?.(refreshResponse)
    expect(await screen.findByRole('alert')).toHaveTextContent('GPU worker status unavailable')
    expect(localBackend).toBeDisabled()
  })

  it('has no automated accessibility violations in the populated state', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(SNAPSHOT)))

    const { container } = render(<GpuWorkersSection />)
    expect(await screen.findByText('Reachable, not ready')).toBeInTheDocument()

    await expectNoAxeViolations(container)
  })
})
