import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CostLiveSnapshot, Project } from '../../types/project'
import Telemetry from './Telemetry'

const SNAPSHOT: CostLiveSnapshot = {
  total_usd: 1.25,
  charged_usd: 1.25,
  active_reservation_usd: 0.75,
  committed_usd: 2,
  budget_status: 'active',
  budget_limit_usd: 5,
  remaining_usd: 3,
  accepted_unknown_count: 1,
  billed_failure_count: 1,
  blocked_attempt_count: 2,
  attempts: [{
    attempt_id: 'attempt-1',
    provider: 'runway',
    engine: 'RUNWAY_GEN4',
    operation: 'video_generation',
    shot_id: 'shot-1',
    video_id: 'project-1',
    state: 'accepted_unknown',
    reserved_cost_usd: 0.75,
    reconciled_cost_usd: 0,
    billed: null,
    provider_job_id: 'task-123',
    provider_status: '',
    failure_code: '',
    detail: 'Submission may have been accepted',
    created_at: '2026-08-05T00:00:00+00:00',
    updated_at: '2026-08-05T00:00:01+00:00',
    active: true,
  }],
}

const PROJECT = {
  id: 'project-1',
  name: 'Cost authority',
  global_settings: { aspect_ratio: '16:9', music_mood: '', color_palette: '', style_rules: {} },
  scenes: [],
} as unknown as Project

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response
}

describe('Telemetry paid-job authority', () => {
  beforeEach(() => {
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  afterEach(() => {
    cleanup()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('loads authoritative cost state while idle and distinguishes charged, reserved, and exposure', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(SNAPSHOT))
    vi.stubGlobal('fetch', fetchMock)

    render(
      <Telemetry
        project={PROJECT}
        shotStates={new Map()}
        failedShots={[]}
        isStreaming={false}
        projectId="project-1"
      />,
    )

    expect(await screen.findByText('$1.2500')).toBeInTheDocument()
    expect(screen.getByText('$0.7500')).toBeInTheDocument()
    expect(screen.getByText('$2.0000')).toBeInTheDocument()
    expect(screen.getByText('$3.0000')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('accepted job')
    expect(screen.getByRole('list', { name: 'Active paid provider jobs' })).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/projects/project-1/cost-live',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    )
  })

  it('requests cancellation through the project-scoped endpoint and explains reservation semantics', async () => {
    const cancelledSnapshot: CostLiveSnapshot = {
      ...SNAPSHOT,
      attempts: [{ ...SNAPSHOT.attempts[0], state: 'cancel_requested' }],
      accepted_unknown_count: 0,
    }
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) =>
      init?.method === 'POST' ? jsonResponse(cancelledSnapshot) : jsonResponse(SNAPSHOT),
    )
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()

    render(
      <Telemetry
        project={PROJECT}
        shotStates={new Map()}
        failedShots={[]}
        isStreaming
        projectId="project-1"
      />,
    )

    await user.click(await screen.findByRole('button', { name: 'Request cancellation' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/projects/project-1/paid-attempts/attempt-1/cancel',
      expect.objectContaining({ method: 'POST' }),
    ))
    expect(screen.getByRole('status')).toHaveTextContent('Budget remains reserved')
    expect(screen.queryByRole('button', { name: 'Request cancellation' })).toBeNull()
  })
})
