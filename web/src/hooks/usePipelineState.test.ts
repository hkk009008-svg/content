import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePipelineState, STAGE_RAIL_MAP, resolveStageBucket } from './usePipelineState'
import type { PipelineAction, ProgressEvent, CheckpointInfo } from '../types/project'

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
  checkpoint?: CheckpointInfo
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

describe('usePipelineState -- canonical stage vocabulary is exhaustive (Slice 11b)', () => {
  it('every stage declared in STAGE_RAIL_MAP resolves without throwing', () => {
    for (const stage of Object.keys(STAGE_RAIL_MAP)) {
      expect(() => resolveStageBucket(stage)).not.toThrow()
    }
  })

  it('a stage the table has never heard of fails loudly instead of silently rendering a blank rail', () => {
    expect(() => resolveStageBucket('TOTALLY_UNDECLARED_STAGE_XYZ')).toThrow(/STAGE_RAIL_MAP/)
  })

  it('every one of the 14 rail stages maps back to itself', () => {
    const railIds = Object.entries(STAGE_RAIL_MAP)
      .filter(([, bucket]) => bucket.kind === 'rail')
      .map(([stage]) => stage)
    expect(railIds).toHaveLength(14)
    for (const id of railIds) {
      expect(resolveStageBucket(id)).toEqual({ kind: 'rail', id })
    }
  })

  it('COMPLETE and DONE are the only terminal stages', () => {
    const terminal = Object.entries(STAGE_RAIL_MAP)
      .filter(([, bucket]) => bucket.kind === 'terminal')
      .map(([stage]) => stage)
      .sort()
    expect(terminal).toEqual(['COMPLETE', 'DONE'])
  })
})

describe('usePipelineState -- reconnect replay lands on the same state as an unbroken stream (Slice 11b)', () => {
  it('a reconnect-replayed suffix produces the same activeStage as processing every event live', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(pipelineStateBody())))

    const unbroken = renderHook(() => usePipelineState('proj-unbroken'))
    const reconnected = renderHook(() => usePipelineState('proj-reconnected'))
    await waitFor(() => expect(unbroken.result.current.allowedActions).toEqual(['start']))
    await waitFor(() => expect(reconnected.result.current.allowedActions).toEqual(['start']))

    const timeline: ProgressEvent[] = [
      { stage: 'STYLE', detail: 'style', percent: 2 },
      { stage: 'AUDIO', detail: 'audio', percent: 5 },
      { stage: 'DECOMPOSE', detail: 'decompose', percent: 12 },
      { stage: 'DIRECTOR', detail: 'director', percent: 13 },
      { stage: 'PLAN_REVIEW', detail: 'plan review', percent: 25 },
      { stage: 'KEYFRAME', detail: 'keyframe', percent: 40 },
    ]

    // Unbroken: every event delivered live, in order, no disconnect.
    act(() => { timeline.forEach((e) => unbroken.result.current.processEvent(e)) })

    // Reconnected: only the first 3 arrived before a transport drop; the
    // rest arrive as a REPLAYED backlog after reconnect (tagged
    // `replayed: true`, exactly as 11a's server sends them) -- the reducer
    // must treat a replayed event identically to a live one.
    act(() => { timeline.slice(0, 3).forEach((e) => reconnected.result.current.processEvent(e)) })
    act(() => {
      timeline.slice(3).forEach((e) => {
        const replayedEvent = { ...e, replayed: true }
        reconnected.result.current.processEvent(replayedEvent)
      })
    })

    expect(reconnected.result.current.activeStage).toBe(unbroken.result.current.activeStage)
    expect(reconnected.result.current.activeStage).toBe('KEYFRAME')
  })

  it('a same-named side-channel event during a later gate cannot drag the rail backward (regen-during-review)', async () => {
    const fetchMock = vi.fn(async () => response(pipelineStateBody()))
    vi.stubGlobal('fetch', fetchMock)
    const { result } = renderHook(() => usePipelineState('proj-review-regen'))
    await waitFor(() => expect(result.current.allowedActions).toEqual(['start']))

    act(() => {
      result.current.processEvent({ stage: 'KEYFRAME', detail: '', percent: 40 })
      result.current.processEvent({ stage: 'KEYFRAME_REVIEW', detail: '', percent: 55 })
    })
    expect(result.current.activeStage).toBe('KEYFRAME_REVIEW')

    // "Generate another keyframe" while parked at the gate re-publishes
    // KEYFRAME/KEYFRAME_READY into the SAME stream (see the STAGE_RAIL_MAP
    // module comment) -- it must not yank the rail back.
    act(() => {
      result.current.processEvent({ stage: 'KEYFRAME', detail: '', percent: 40, shot_id: 'shot-1', scene_id: 'scene-1' })
      result.current.processEvent({ stage: 'KEYFRAME_READY', detail: '', percent: 40, shot_id: 'shot-1', scene_id: 'scene-1' })
    })
    expect(result.current.activeStage).toBe('KEYFRAME_REVIEW')
  })

  it('a GAP event triggers a fresh pipeline-state reconcile instead of guessing at the missed range', async () => {
    const fetchMock = vi.fn(async () => response(pipelineStateBody({ running: true, allowed_actions: ['cancel', 'pause'] })))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => usePipelineState('proj-gap'))
    await waitFor(() => expect(result.current.running).toBe(true))

    act(() => {
      result.current.processEvent({
        stage: 'GAP', detail: 'Missed events 4-9 (replay buffer cap exceeded)', percent: -1,
      })
    })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
  })
})

describe('usePipelineState -- legacy shot_results/gate_status reconciliation (Slice 11b)', () => {
  it('hydrate reconciles legacy shot_results into shotStates in the same shape the SSE reducer produces', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(pipelineStateBody({
      shot_results: {
        'shot-1': { image: 'kf.jpg', video: null, identity_score: 0.82, status: 'keyframe_review' },
        'shot-2': { image: 'kf2.jpg', video: 'motion.mp4', identity_score: -1, status: 'final_review' },
      },
    }))))

    const { result } = renderHook(() => usePipelineState('proj-legacy'))
    await waitFor(() => expect(result.current.shotStates.size).toBe(2))

    expect(result.current.shotStates.get('shot-1')).toEqual({
      id: 'shot-1', generated_image: 'kf.jpg', identity_score: 0.82, status: 'image_review',
    })
    // identity_score -1 is the "absent" sentinel (mirrors processEvent's own
    // `>= 0` guard) -- it must not land in the hydrated entry.
    expect(result.current.shotStates.get('shot-2')).toEqual({
      id: 'shot-2', generated_image: 'kf2.jpg', generated_video: 'motion.mp4', status: 'final_review',
    })
  })

  it('an unrecognized legacy status is left unset rather than crashing the hydrate fetch', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(pipelineStateBody({
      shot_results: { 'shot-1': { image: 'kf.jpg', video: null, identity_score: 0.5, status: 'some_pre_migration_status' } },
    }))))

    const { result } = renderHook(() => usePipelineState('proj-legacy-unknown'))
    await waitFor(() => expect(result.current.shotStates.size).toBe(1))
    expect(result.current.shotStates.get('shot-1')?.status).toBeUndefined()
    expect(result.current.shotStates.get('shot-1')?.generated_image).toBe('kf.jpg')
    expect(result.current.shotStates.get('shot-1')?.identity_score).toBe(0.5)
  })

  it('a legacy hydrate never clobbers a richer field a live SSE event already populated, but still fills real gaps', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response(pipelineStateBody({ running: true, allowed_actions: ['cancel', 'pause'] })))
      .mockImplementationOnce(async () => response(pipelineStateBody({
        running: true, allowed_actions: ['cancel', 'pause'],
        shot_results: { 'shot-1': { image: 'stale.jpg', video: null, identity_score: 0.1, status: 'keyframe_review' } },
      })))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => usePipelineState('proj-no-clobber'))
    await waitFor(() => expect(result.current.running).toBe(true))

    // A live SSE event already gave this shot richer data than any legacy
    // snapshot can express -- but never touched identity_score.
    act(() => {
      result.current.processEvent({
        stage: 'KEYFRAME_REVIEW', detail: '', percent: 50, scene_id: 'scene-1', shot_id: 'shot-1',
        image_url: 'live.jpg', coherence_score: 0.95,
      })
    })
    expect(result.current.shotStates.get('shot-1')?.generated_image).toBe('live.jpg')
    expect(result.current.shotStates.get('shot-1')?.coherence_score).toBe(0.95)

    // A refresh (e.g. after a pause/resume click) re-hydrates from a STALE
    // legacy snapshot for the SAME shot -- it must not overwrite what the
    // live event already established...
    await act(async () => { await result.current.refreshPipelineState() })

    expect(result.current.shotStates.get('shot-1')?.generated_image).toBe('live.jpg')
    expect(result.current.shotStates.get('shot-1')?.coherence_score).toBe(0.95)
    // ...but SHOULD fill identity_score, which no live event ever touched.
    expect(result.current.shotStates.get('shot-1')?.identity_score).toBe(0.1)
  })

  it('gate_status marks earlier rail stages complete without ever asserting a live "running" stage', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(pipelineStateBody({
      current_stage: '', // idle snapshot branch -- no live pointer at all
      gate_status: { total_shots: 3, plans_approved: 3, keyframes_approved: 3, motions_generated: 0, finals_approved: 0 },
    }))))

    const { result } = renderHook(() => usePipelineState('proj-gate-floor'))
    await waitFor(() => expect(result.current.stages.find((s) => s.id === 'KEYFRAME_REVIEW')?.status).toBe('complete'))

    const byId = new Map(result.current.stages.map((s) => [s.id, s.status]))
    expect(byId.get('STYLE')).toBe('complete')
    expect(byId.get('PLAN_REVIEW')).toBe('complete')
    expect(byId.get('KEYFRAME_REVIEW')).toBe('complete')
    // PERFORMANCE is next in line, but there is no LIVE confirmation it is
    // actually running right now -- gate_status must never synthesize that.
    expect(byId.get('PERFORMANCE')).toBe('pending')
    expect(result.current.stages.some((s) => s.status === 'running')).toBe(false)
  })
})

describe('usePipelineState -- checkpoint summary (Slice 11c)', () => {
  const resumableCheckpoint: CheckpointInfo = {
    resumable: true,
    completed_scenes: 2,
    total_scenes: 5,
    stage: 'MOTION',
    shots_done: 3,
    shots_failed: 1,
  }

  it('hydrates checkpoint from the idle branch response', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(pipelineStateBody({
      allowed_actions: ['start', 'resume_checkpoint'],
      checkpoint: resumableCheckpoint,
    }))))

    const { result } = renderHook(() => usePipelineState('proj-checkpoint'))

    await waitFor(() => expect(result.current.allowedActions).toEqual(['start', 'resume_checkpoint']))
    expect(result.current.checkpoint).toEqual(resumableCheckpoint)
  })

  it('defaults checkpoint to null when the response omits it (running/paused branch)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(pipelineStateBody({
      running: true, allowed_actions: ['cancel', 'pause'],
      // no `checkpoint` key -- mirrors the live-pipeline branch shape.
    }))))

    const { result } = renderHook(() => usePipelineState('proj-checkpoint-running'))

    await waitFor(() => expect(result.current.running).toBe(true))
    expect(result.current.checkpoint).toBeNull()
  })

  it('an A -> B project switch does not leak A checkpoint state into B', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response(pipelineStateBody({
        allowed_actions: ['start', 'resume_checkpoint'],
        checkpoint: resumableCheckpoint,
      })))
      .mockImplementationOnce(async () => response(pipelineStateBody())) // B: idle, no checkpoint
    vi.stubGlobal('fetch', fetchMock)

    const { result, rerender } = renderHook(
      ({ projectId }) => usePipelineState(projectId),
      { initialProps: { projectId: 'proj-A' as string | null } },
    )
    await waitFor(() => expect(result.current.checkpoint).toEqual(resumableCheckpoint))

    rerender({ projectId: 'proj-B' })

    // Reset is synchronous -- gone immediately, before B's own fetch resolves.
    expect(result.current.checkpoint).toBeNull()

    await waitFor(() => expect(result.current.allowedActions).toEqual(['start']))
    expect(result.current.checkpoint).toBeNull()
  })
})

describe('usePipelineState -- a transport drop alone never flips `running` (Slice 11b)', () => {
  // Exercises the REAL useSSE wiring (not just a mocked prop) end to end,
  // mirroring App.tsx's real handleGenerate sequence: start the SSE watch,
  // then separately confirm `running` from a fresh fetch -- never from the
  // stream. `_pipeline_action_authority`'s own docstring: "a client can
  // disconnect from the SSE stream while generation keeps running, and vice
  // versa, so transport state is never job truth."
  class MockEventSource {
    static instances: MockEventSource[] = []
    readonly url: string
    onmessage: ((event: MessageEvent<string>) => void) | null = null
    onerror: ((event: Event) => void) | null = null
    close = vi.fn()
    constructor(url: string | URL) {
      this.url = String(url)
      MockEventSource.instances.push(this)
    }
    fail() { this.onerror?.(new Event('error')) }
  }

  beforeEach(() => {
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
  })

  afterEach(() => {
    cleanup()
    if (vi.isFakeTimers()) vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('running (backend truth) survives a transport drop all the way through SSE giving up', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response(pipelineStateBody())) // initial idle hydrate
      .mockImplementationOnce(async () => response(pipelineStateBody({ running: true, allowed_actions: ['cancel', 'pause'] }))) // post-generate refresh
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => usePipelineState('proj-transport-drop'))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    act(() => result.current.start())
    await act(async () => { await result.current.refreshPipelineState() })
    await waitFor(() => expect(result.current.running).toBe(true))
    expect(result.current.isStreaming).toBe(true)
    expect(result.current.allowedActions).toEqual(['cancel', 'pause'])

    // Switch to fake timers only NOW -- the async setup above (fetch +
    // hydrate) is fully settled with real timers/microtasks; only the
    // retry-backoff scheduling below needs to be fast-forwarded.
    vi.useFakeTimers()

    // Fail the connection repeatedly until useSSE exhausts its own retry
    // budget and gives up (isStreaming genuinely flips false here) --
    // running must not react at any point along the way.
    for (let attempt = 0; attempt < 11; attempt++) {
      const current = MockEventSource.instances[MockEventSource.instances.length - 1]
      act(() => current.fail())
      expect(result.current.running).toBe(true)
      expect(result.current.allowedActions).toEqual(['cancel', 'pause'])
      act(() => { vi.advanceTimersByTime(30_000) })
    }

    expect(result.current.isStreaming).toBe(false) // the transport genuinely gave up...
    expect(result.current.running).toBe(true) // ...yet backend truth never moved.
    expect(result.current.allowedActions).toEqual(['cancel', 'pause'])
  })
})
