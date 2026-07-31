import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { usePipelineState } from './usePipelineState'
import type { PipelineAction } from '../types/project'

/**
 * Slice 8b (2026-07-30 comprehensive-unification plan, plan slice 8) --
 * project-scoped pipeline state, action authority, and truthful mutations.
 *
 * Shape-based fixtures only: no live backend/roster coupling. Every
 * `pipeline-state` response mirrors the exact additive shape slice 8a
 * shipped (tests/unit/test_pipeline_state_authority.py).
 */

interface PipelineStateBody {
  paused: boolean
  cancelled: boolean
  current_stage: string
  current_scene_id: string
  current_shot_id: string
  shot_results: Record<string, unknown>
  failed_shots: string[]
  scenes_completed: number
  gate_status: {
    total_shots: number
    plans_approved: number
    keyframes_approved: number
    motions_generated: number
    finals_approved: number
  }
  running: boolean
  allowed_actions: PipelineAction[]
}

function pipelineStateBody(overrides: Partial<PipelineStateBody> = {}): PipelineStateBody {
  return {
    paused: false,
    cancelled: false,
    current_stage: '',
    current_scene_id: '',
    current_shot_id: '',
    shot_results: {},
    failed_shots: [],
    scenes_completed: 0,
    gate_status: {
      total_shots: 0, plans_approved: 0, keyframes_approved: 0, motions_generated: 0, finals_approved: 0,
    },
    running: false,
    allowed_actions: ['start'],
    ...overrides,
  }
}

/** `lib/api.ts`'s `apiRequest` reads the body via `res.text()` (never
 *  `res.json()`), so the mock Response only needs to satisfy that. */
function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    text: vi.fn(async () => JSON.stringify(payload)),
  } as unknown as Response
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => { resolve = res })
  return { promise, resolve }
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('usePipelineState -- PID boundary (project switch)', () => {
  it('an A -> B switch resets shot/failure/stage/action state synchronously -- B never inherits A data', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response(pipelineStateBody({
        current_stage: 'MOTION',
        failed_shots: ['shotA1'],
        running: true,
        allowed_actions: ['cancel', 'pause'],
      })))
      .mockImplementationOnce(async () => response(pipelineStateBody())) // B: idle
    vi.stubGlobal('fetch', fetchMock)

    const { result, rerender } = renderHook(
      ({ projectId }) => usePipelineState(projectId),
      { initialProps: { projectId: 'proj-A' as string | null } },
    )

    await waitFor(() => expect(result.current.activeStage).toBe('MOTION'))
    expect(result.current.failedShots).toEqual(['shotA1'])
    expect(result.current.running).toBe(true)
    expect(result.current.allowedActions).toEqual(['cancel', 'pause'])

    // Also populate SSE-routed state (shotStates/directorReview) for A --
    // hydration deliberately does not touch these (see hydrateFrom's
    // docstring), so the leak test must cover both sources.
    act(() => {
      result.current.processEvent({
        stage: 'KEYFRAME_REVIEW',
        detail: 'A shot up for review',
        percent: 50,
        scene_id: 'sceneA',
        shot_id: 'shotA1',
        director_review: { decision: 'APPROVED', violations: [], quality_score: 0.9, reasoning: 'ok' },
      })
    })
    expect(result.current.shotStates.size).toBe(1)
    expect(result.current.directorReview).not.toBeNull()

    rerender({ projectId: 'proj-B' })

    // Reset is synchronous -- visible immediately, before B's own hydrate
    // fetch (already in flight) resolves.
    expect(result.current.shotStates.size).toBe(0)
    expect(result.current.directorReview).toBeNull()
    expect(result.current.failedShots).toEqual([])
    expect(result.current.activeStage).toBeNull()
    expect(result.current.running).toBe(false)
    expect(result.current.allowedActions).toEqual([])

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(result.current.allowedActions).toEqual(['start']))
    // B hydrated to ITS OWN idle truth -- not a trace of A's data anywhere.
    expect(result.current.failedShots).toEqual([])
    expect(result.current.activeStage).toBeNull()
    expect(result.current.shotStates.size).toBe(0)
    expect(result.current.directorReview).toBeNull()
  })

  it('switching to null and back resets state the same way (the real "back to projects" path)', async () => {
    const fetchMock = vi.fn(async () => response(pipelineStateBody({ current_stage: 'REVIEW', running: true, allowed_actions: ['cancel', 'pause'] })))
    vi.stubGlobal('fetch', fetchMock)

    const { result, rerender } = renderHook(
      ({ projectId }) => usePipelineState(projectId),
      { initialProps: { projectId: 'proj-A' as string | null } },
    )
    await waitFor(() => expect(result.current.activeStage).toBe('REVIEW'))

    rerender({ projectId: null })
    expect(result.current.activeStage).toBeNull()
    expect(result.current.running).toBe(false)
    expect(result.current.allowedActions).toEqual([])
    // No fetch is issued while there is no project.
    expect(fetchMock).toHaveBeenCalledTimes(1)

    rerender({ projectId: 'proj-B' })
    expect(result.current.activeStage).toBeNull() // reset again, before B hydrates
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })
})

describe('usePipelineState -- server-derived action authority', () => {
  it('an idle backend reports running=false and allows only "start" -- no cancel/pause/resume', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(pipelineStateBody({ running: false, allowed_actions: ['start'] }))))

    const { result } = renderHook(() => usePipelineState('proj-idle'))

    await waitFor(() => expect(result.current.allowedActions).toEqual(['start']))
    expect(result.current.running).toBe(false)
    expect(result.current.allowedActions).not.toContain('cancel')
    expect(result.current.allowedActions).not.toContain('pause')
    expect(result.current.allowedActions).not.toContain('resume')
  })

  it('a running-paused backend reports cancel+resume, distinct from running-unpaused', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(pipelineStateBody({
      paused: true, running: true, allowed_actions: ['cancel', 'resume'],
    }))))

    const { result } = renderHook(() => usePipelineState('proj-paused'))

    await waitFor(() => expect(result.current.running).toBe(true))
    expect(result.current.isPaused).toBe(true)
    expect(result.current.allowedActions).toEqual(['cancel', 'resume'])
    expect(result.current.allowedActions).not.toContain('start')
    expect(result.current.allowedActions).not.toContain('pause')
  })
})

describe('usePipelineState -- stale out-of-order responses', () => {
  it('drops a pipeline-state response that resolves after a newer one already superseded it', async () => {
    const first = deferred<Response>()
    const second = deferred<Response>()
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)
    vi.stubGlobal('fetch', fetchMock)

    const { result, rerender } = renderHook(
      ({ projectId }) => usePipelineState(projectId),
      { initialProps: { projectId: 'proj-A' as string | null } },
    )
    rerender({ projectId: 'proj-B' })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    // B's (second, newer) request resolves FIRST.
    await act(async () => {
      second.resolve(response(pipelineStateBody({
        current_stage: 'MOTION', running: true, allowed_actions: ['cancel', 'pause'],
      })))
    })
    await waitFor(() => expect(result.current.activeStage).toBe('MOTION'))

    // A's (first, now-superseded) request resolves LATE and must be dropped.
    await act(async () => {
      first.resolve(response(pipelineStateBody({
        current_stage: 'REVIEW', running: true, allowed_actions: ['cancel', 'resume'],
      })))
    })
    expect(result.current.activeStage).toBe('MOTION')
    expect(result.current.allowedActions).toEqual(['cancel', 'pause'])
  })

  it('drops a stale response to a manual refreshPipelineState() call superseded by a newer refresh', async () => {
    const first = deferred<Response>()
    const second = deferred<Response>()
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response(pipelineStateBody({ running: true, allowed_actions: ['cancel', 'pause'] }))) // initial hydrate
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => usePipelineState('proj-refresh'))
    await waitFor(() => expect(result.current.running).toBe(true))

    // Two refreshes fired back-to-back (e.g. two rapid pause/resume clicks);
    // the second is issued before the first resolves.
    let refreshOne: Promise<void>
    let refreshTwo: Promise<void>
    act(() => {
      refreshOne = result.current.refreshPipelineState()
      refreshTwo = result.current.refreshPipelineState()
    })
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))

    await act(async () => {
      second.resolve(response(pipelineStateBody({ current_stage: 'NEWEST', running: true, allowed_actions: ['cancel', 'resume'] })))
      await refreshTwo
    })
    expect(result.current.activeStage).toBe('NEWEST')

    await act(async () => {
      first.resolve(response(pipelineStateBody({ current_stage: 'STALE', running: true, allowed_actions: ['cancel', 'pause'] })))
      await refreshOne
    })
    // The stale (first-issued, later-resolving) refresh must not win.
    expect(result.current.activeStage).toBe('NEWEST')
    expect(result.current.allowedActions).toEqual(['cancel', 'resume'])
  })
})

describe('usePipelineState -- truthful mutations (never paint optimistic success)', () => {
  it('pause() does not flip isPaused when the server rejects the request', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response(pipelineStateBody({ running: true, allowed_actions: ['cancel', 'pause'] }))) // initial hydrate
      .mockImplementationOnce(async () => response({ error: 'pipeline already stopped' }, false, 409)) // the /pause POST itself
      .mockImplementationOnce(async () => response(pipelineStateBody({ paused: false, running: true, allowed_actions: ['cancel', 'pause'] }))) // post-mutation refresh: still not paused
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => usePipelineState('proj-pause'))
    await waitFor(() => expect(result.current.running).toBe(true))
    expect(result.current.isPaused).toBe(false)

    await act(async () => {
      await result.current.pause()
    })

    expect(result.current.isPaused).toBe(false)
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('a non-2xx shot-plan mutation resolves to a truthful error, never a bare success-shaped body', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response(pipelineStateBody())) // initial hydrate
      .mockImplementationOnce(async () => response({ error: 'Shot not found' }, false, 404))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => usePipelineState('proj-mutate'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    let outcome: any
    await act(async () => {
      outcome = await result.current.approveShotPlan('shot-1')
    })

    expect(outcome.success).toBe(false)
    expect(outcome.error).toBe('Shot not found')
  })

  it('a network failure on a mutation resolves to a truthful error instead of throwing', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response(pipelineStateBody())) // initial hydrate
      .mockImplementationOnce(async () => { throw new Error('offline') })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => usePipelineState('proj-network'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    let outcome: any
    await act(async () => {
      outcome = await result.current.approveShotPlan('shot-1')
    })

    expect(outcome.success).toBe(false)
    expect(outcome.error).toBe('offline')
  })

  it('a successful mutation body passes through unchanged', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response(pipelineStateBody())) // initial hydrate
      .mockImplementationOnce(async () => response({ approved: true, take: { id: 'take-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => usePipelineState('proj-success'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    let outcome: any
    await act(async () => {
      outcome = await result.current.approveShotPlan('shot-1')
    })

    expect(outcome).toEqual({ approved: true, take: { id: 'take-1' } })
    expect(outcome.error).toBeUndefined()
  })
})
