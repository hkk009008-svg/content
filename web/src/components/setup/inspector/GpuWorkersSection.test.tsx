import { useState } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { expectNoAxeViolations } from '../../../test/a11y-setup'
import type {
  GpuWorkerControlResponse,
  GpuWorkerStatus,
  GpuWorkersResponse,
} from '../../../types/project'
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

const WORKERS_ENDPOINT = '/api/runtime/gpu-workers'
const CONTROL_ENDPOINT = '/api/runtime/gpu-worker-control'

const CONTROL: GpuWorkerControlResponse = {
  schema_version: 1,
  state: 'stopped',
  can_start: true,
  gpu_busy: false,
  gpu_used_mib: 1082,
  gpu_utilization_percent: 0,
  last_task_result: 1,
  message: 'The Windows worker is stopped and the GPU is available to launch.',
  checked_at: '2026-08-06T01:02:03Z',
  control_token: 'c'.repeat(43),
}

function workerFetch(payload: unknown = SNAPSHOT) {
  return vi.fn(async (input: RequestInfo | URL) => (
    String(input) === CONTROL_ENDPOINT ? response(CONTROL) : response(payload)
  ))
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
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('GpuWorkersSection', () => {
  it('fetches on mount and distinguishes reachable from contract-ready', async () => {
    let resolveFetch: ((value: Response) => void) | undefined
    const fetchMock = vi.fn((input: RequestInfo | URL) => (
      String(input) === CONTROL_ENDPOINT
        ? Promise.resolve(response(CONTROL))
        : new Promise<Response>((resolve) => { resolveFetch = resolve })
    ))
    vi.stubGlobal('fetch', fetchMock)

    render(<GpuWorkersSection />)

    expect(screen.getByText('Checking GPU workers').closest('[role="status"]')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'Refresh GPU worker status' })).toBeDisabled()
    expect(fetchMock).toHaveBeenCalledWith(WORKERS_ENDPOINT, undefined)
    expect(fetchMock).toHaveBeenCalledWith(CONTROL_ENDPOINT, undefined)

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
    let workerRequests = 0
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input) === CONTROL_ENDPOINT) return Promise.resolve(response(CONTROL))
      workerRequests += 1
      if (workerRequests === 1) return Promise.resolve(response(SNAPSHOT))
      return new Promise<Response>((resolve) => { resolveRefresh = resolve })
    })
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
    await waitFor(() => expect(workerRequests).toBe(2))
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
    vi.stubGlobal('fetch', workerFetch(shared))

    const { container } = render(<GpuWorkersSection />)

    expect(await screen.findByText('Blocked')).toBeInTheDocument()
    expect(screen.getByText('Local image execution proof is incomplete.')).toBeInTheDocument()
    expect(screen.getAllByText(/Shared/)).toHaveLength(2)
    expect(screen.getByText(/Image worker: Blocked; Performance worker: Ready/).closest('[role="status"]')).not.toBeNull()
    expect(screen.queryByText('Reachable, not ready')).toBeNull()
    await expectNoAxeViolations(container)
  })

  it('surfaces a failed request as an alert, then allows an explicit retry', async () => {
    let workerRequests = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === CONTROL_ENDPOINT) return response(CONTROL)
      workerRequests += 1
      return workerRequests === 1
        ? response({ error: 'Health probe timed out' }, false, 503)
        : response(SNAPSHOT)
    })
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
    vi.stubGlobal('fetch', workerFetch({ workers: [{ state: 'ready' }] }))

    render(<GpuWorkersSection />)

    expect(await screen.findByRole('alert')).toHaveTextContent('returned an invalid response')
    expect(screen.queryByText('Ready')).toBeNull()
  })

  it.each([
    ['failed', response({ error: 'Health probe timed out' }, false, 503)],
    ['malformed', response({ workers: [{ state: 'ready' }] })],
  ])('revokes local image authority when a refresh is %s', async (_case, refreshResponse) => {
    let resolveRefresh: ((value: Response) => void) | undefined
    let workerRequests = 0
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input) === CONTROL_ENDPOINT) return Promise.resolve(response(CONTROL))
      workerRequests += 1
      if (workerRequests === 1) return Promise.resolve(response(READY_SNAPSHOT))
      return new Promise<Response>((resolve) => { resolveRefresh = resolve })
    })
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
    vi.stubGlobal('fetch', workerFetch())

    const { container } = render(<GpuWorkersSection />)
    expect(await screen.findByText('Reachable, not ready')).toBeInTheDocument()

    await expectNoAxeViolations(container)
  })

  it('starts the fixed Windows worker with the server-issued control token', async () => {
    const starting: GpuWorkerControlResponse = {
      ...CONTROL,
      state: 'starting',
      can_start: false,
      message: 'Windows worker launch requested; readiness is checked separately.',
      control_token: undefined,
    }
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === `${CONTROL_ENDPOINT}/start`) return response(starting, true, 202)
      if (url === CONTROL_ENDPOINT) return response(CONTROL)
      return response(SNAPSHOT)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<GpuWorkersSection />)
    const start = await screen.findByRole('button', { name: 'Start Windows worker' })
    expect(start).toBeEnabled()
    fireEvent.click(start)

    expect(await screen.findByText('Windows worker starting')).toBeInTheDocument()
    expect(
      screen.getAllByText(starting.message).some((node) => node.closest('[role="status"]')),
    ).toBe(true)
    expect(fetchMock).toHaveBeenCalledWith(
      `${CONTROL_ENDPOINT}/start`,
      expect.objectContaining({
        method: 'POST',
        body: '{}',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          'X-Content-Control-Token': CONTROL.control_token,
        }),
      }),
    )
    expect(screen.queryByRole('button', { name: /stop windows worker/i })).toBeNull()
  })

  it('moves keyboard focus to Refresh when a successful start removes its button', async () => {
    const user = userEvent.setup()
    const starting: GpuWorkerControlResponse = {
      ...CONTROL,
      state: 'starting',
      can_start: false,
      message: 'Windows worker launch requested; readiness is checked separately.',
      control_token: undefined,
    }
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === `${CONTROL_ENDPOINT}/start`) return response(starting, true, 202)
      return response(url === CONTROL_ENDPOINT ? CONTROL : SNAPSHOT)
    }))

    render(<GpuWorkersSection />)
    const start = await screen.findByRole('button', { name: 'Start Windows worker' })
    start.focus()
    expect(start).toHaveFocus()

    await user.keyboard('{Enter}')

    expect(await screen.findByText('Windows worker starting')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Start Windows worker' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Refresh GPU worker status' })).toHaveFocus()
  })

  it.each([
    [
      'failed',
      { ...CONTROL, state: 'failed', can_start: false, message: 'The previous launch failed.' },
      'Launch failed',
    ],
    [
      'unknown',
      { ...CONTROL, state: 'unknown', can_start: false, message: 'Task state could not be verified.' },
      'Task state unknown',
    ],
    [
      'busy',
      { ...CONTROL, can_start: false, gpu_busy: true, message: 'The Windows GPU is busy.' },
      'Windows worker stopped',
    ],
    [
      'unavailable',
      { ...CONTROL, state: 'unavailable', can_start: false, message: 'Control is unavailable.' },
      'Launch unavailable',
    ],
  ] as const)(
    'announces the %s launch-control transition after a manual refresh',
    async (_case, refreshedControl, expectedLabel) => {
      let controlRequests = 0
      const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
        if (String(input) !== CONTROL_ENDPOINT) return response(SNAPSHOT)
        controlRequests += 1
        return response(controlRequests === 1 ? CONTROL : refreshedControl)
      })
      vi.stubGlobal('fetch', fetchMock)

      render(<GpuWorkersSection />)
      const refresh = await screen.findByRole('button', { name: 'Refresh GPU worker status' })
      fireEvent.click(refresh)

      await waitFor(() => {
        expect(
          screen.getAllByRole('status').some((status) => (
            status.textContent?.includes(
              `Windows launch control: ${expectedLabel}. ${refreshedControl.message}`,
            )
          )),
        ).toBe(true)
      })
      expect(controlRequests).toBe(2)
    },
  )

  it('surfaces a failed launch accessibly and keeps explicit retry available', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === `${CONTROL_ENDPOINT}/start`) {
        return response({ error: 'Windows worker launch failed closed.' }, false, 503)
      }
      return response(url === CONTROL_ENDPOINT ? CONTROL : SNAPSHOT)
    })
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(<GpuWorkersSection />)
    const start = await screen.findByRole('button', { name: 'Start Windows worker' })
    fireEvent.click(start)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Windows worker launch unavailable: Windows worker launch failed closed.',
    )
    expect(
      screen.getByText(
        'Windows worker was not launched. Windows worker launch failed closed.',
      ).closest('[role="status"]'),
    ).not.toBeNull()
    expect(start).toBeEnabled()
    await expectNoAxeViolations(container)
  })

  it('does not schedule polling when a deferred launch resolves after unmount', async () => {
    const starting: GpuWorkerControlResponse = {
      ...CONTROL,
      state: 'starting',
      can_start: false,
      message: 'Windows worker launch requested; readiness is checked separately.',
      control_token: undefined,
    }
    let resolveStart: ((value: Response) => void) | undefined
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === `${CONTROL_ENDPOINT}/start`) {
        return new Promise<Response>((resolve) => { resolveStart = resolve })
      }
      return Promise.resolve(url === CONTROL_ENDPOINT ? response(CONTROL) : response(SNAPSHOT))
    })
    vi.stubGlobal('fetch', fetchMock)

    const { unmount } = render(<GpuWorkersSection />)
    fireEvent.click(await screen.findByRole('button', { name: 'Start Windows worker' }))
    await waitFor(() => expect(resolveStart).toBeTypeOf('function'))
    const timerSpy = vi.spyOn(window, 'setTimeout')
    const requestsAtUnmount = fetchMock.mock.calls.length

    unmount()
    await act(async () => {
      resolveStart?.(response(starting, true, 202))
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(timerSpy).not.toHaveBeenCalled()
    expect(fetchMock).toHaveBeenCalledTimes(requestsAtUnmount)
  })

  it('polls repeatedly after launch until the performance worker is ready, then stops', async () => {
    vi.useFakeTimers()
    const starting: GpuWorkerControlResponse = {
      ...CONTROL,
      state: 'starting',
      can_start: false,
      message: 'Windows worker launch requested; readiness is checked separately.',
      control_token: undefined,
    }
    const running: GpuWorkerControlResponse = {
      ...CONTROL,
      state: 'running',
      can_start: false,
      message: 'The Windows worker task is running; readiness is checked separately.',
    }
    const notReady: GpuWorkersResponse = {
      ...SNAPSHOT,
      workers: SNAPSHOT.workers.map((worker) => (
        worker.role === 'performance'
          ? {
              ...worker,
              state: 'offline',
              message: 'The performance worker is still starting.',
            }
          : worker
      )),
    }
    let workerRequests = 0
    let controlRequests = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === `${CONTROL_ENDPOINT}/start`) return response(starting, true, 202)
      if (url === CONTROL_ENDPOINT) {
        controlRequests += 1
        return response(controlRequests === 1 ? CONTROL : running)
      }
      workerRequests += 1
      return response(workerRequests < 3 ? notReady : SNAPSHOT)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<GpuWorkersSection />)
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Start Windows worker' }))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(workerRequests).toBe(1)
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(workerRequests).toBe(2)
    expect(screen.getByText('The performance worker is still starting.')).toBeInTheDocument()

    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(workerRequests).toBe(3)
    expect(screen.getByText('Windows performance worker is ready.').closest('[role="status"]')).not.toBeNull()

    await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
    expect(workerRequests).toBe(3)
    expect(controlRequests).toBe(3)
  })

  it('stops polling and announces when launch readiness times out', async () => {
    vi.useFakeTimers()
    const starting: GpuWorkerControlResponse = {
      ...CONTROL,
      state: 'starting',
      can_start: false,
      message: 'Windows worker launch requested; readiness is checked separately.',
      control_token: undefined,
    }
    const running: GpuWorkerControlResponse = {
      ...CONTROL,
      state: 'running',
      can_start: false,
      message: 'The Windows worker task is running; readiness is checked separately.',
    }
    const notReady: GpuWorkersResponse = {
      ...SNAPSHOT,
      workers: SNAPSHOT.workers.map((worker) => (
        worker.role === 'performance'
          ? { ...worker, state: 'offline', message: 'The worker is still starting.' }
          : worker
      )),
    }
    let workerRequests = 0
    let controlRequests = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === `${CONTROL_ENDPOINT}/start`) return response(starting, true, 202)
      if (url === CONTROL_ENDPOINT) {
        controlRequests += 1
        return response(controlRequests === 1 ? CONTROL : running)
      }
      workerRequests += 1
      return response(notReady)
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<GpuWorkersSection />)
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Start Windows worker' }))
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    vi.setSystemTime(Date.now() + (5 * 60 * 1000))
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })

    expect(
      screen.getByText(
        'Windows worker is still not ready. Refresh to check its latest status.',
      ).closest('[role="status"]'),
    ).not.toBeNull()
    const requestsAtTimeout = fetchMock.mock.calls.length
    await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
    expect(fetchMock).toHaveBeenCalledTimes(requestsAtTimeout)
    expect(workerRequests).toBe(2)
    expect(controlRequests).toBe(2)
  })
})
