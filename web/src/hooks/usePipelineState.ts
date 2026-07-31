import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import type { ProgressEvent, ShotState, PipelineStage, DirectorReview, PipelineState, PipelineAction } from '../types/project'
import { useSSE } from './useSSE'
import { apiGet, apiPost } from '../lib/api'

const PIPELINE_STAGES: PipelineStage[] = [
  { id: 'STYLE', label: 'Style Rules', status: 'pending' },
  { id: 'AUDIO', label: 'Background Music', status: 'pending' },
  { id: 'DECOMPOSE', label: 'Shot Decomposition', status: 'pending' },
  { id: 'DIRECTOR', label: 'Director Review', status: 'pending' },
  { id: 'PLAN_REVIEW', label: 'Shot Plans', status: 'pending' },
  { id: 'KEYFRAME', label: 'Keyframes', status: 'pending' },
  { id: 'KEYFRAME_REVIEW', label: 'Keyframe Review', status: 'pending' },
  { id: 'PERFORMANCE', label: 'Performance Capture', status: 'pending' },
  { id: 'PERFORMANCE_REVIEW', label: 'Performance Review', status: 'pending' },
  { id: 'MOTION', label: 'Motion', status: 'pending' },
  { id: 'REVIEW', label: 'Final Review', status: 'pending' },
  { id: 'SCENE_PREVIEW', label: 'Scene Preview', status: 'pending' },
  { id: 'ASSEMBLY', label: 'Final Assembly', status: 'pending' },
  // S19 Surface B (cycle-9): SCREENING is a 14th stage inserted AFTER ASSEMBLY.
  // Visible unconditionally in the stage list; the BACKEND `CINEMA_SCREENING_STAGE`
  // env flag controls whether the pipeline actually emits SCREENING stage events.
  // Default ON as of v5.1+ flag-flip (2026-05-26); §7.7.3 Class B opt-out UX flag.
  // When explicitly opted out (CINEMA_SCREENING_STAGE=0) the pipeline goes
  // ASSEMBLY → COMPLETE as before and this stage simply remains in 'pending'
  // status (legacy-compatible pre-flip behavior).
  { id: 'SCREENING', label: 'Screening', status: 'pending' },
]

export function usePipelineState(projectId: string | null) {
  const sse = useSSE(projectId)
  const [shotStates, setShotStates] = useState<Map<string, Partial<ShotState>>>(new Map())
  const [directorReview, setDirectorReview] = useState<DirectorReview | null>(null)
  const [completedStages, setCompletedStages] = useState<Set<string>>(new Set())
  const [activeStage, setActiveStage] = useState<string | null>(null)
  const [isPaused, setIsPaused] = useState(false)
  const [failedShots, setFailedShots] = useState<string[]>([])
  const [activeShotId, setActiveShotId] = useState<string | null>(null)
  const [notesBuffer, setNotesBuffer] = useState<ProgressEvent[]>([])
  // Slice 8b: server-derived lifecycle authority
  // (`web_server.py:_pipeline_action_authority`, via
  // `GET /api/projects/<pid>/pipeline-state`). NEVER inferred from
  // `sse.isStreaming` (transport connectivity is not job truth) -- see
  // `fetchAndHydrate` / `refreshPipelineState` below.
  const [running, setRunning] = useState(false)
  const [allowedActions, setAllowedActions] = useState<PipelineAction[]>([])

  // Guards every pipeline-state fetch (project-switch hydration AND
  // on-demand post-mutation refreshes) against an out-of-order arrival:
  // bumped before every fetch is issued and on effect cleanup, compared
  // when a fetch resolves. A response whose epoch no longer matches the
  // current one was superseded by a newer fetch (a fresh project switch,
  // or a fresh refresh) and is dropped rather than applied.
  const epochRef = useRef(0)

  // Shared by the PID-switch effect below and `start()` -- both need the
  // same "forget everything about the previous run" reset.
  const resetLocalState = useCallback(() => {
    setShotStates(new Map())
    setDirectorReview(null)
    setCompletedStages(new Set())
    setActiveStage(null)
    setIsPaused(false)
    setFailedShots([])
    setActiveShotId(null)
    setNotesBuffer([])
    setRunning(false)
    setAllowedActions([])
  }, [])

  const hydrateFrom = useCallback((state: PipelineState) => {
    setIsPaused(!!state.paused)
    setFailedShots(state.failed_shots ?? [])
    setActiveStage(state.current_stage || null)
    setRunning(!!state.running)
    setAllowedActions(state.allowed_actions ?? [])
    // NOTE: shot_results / gate_status are intentionally NOT reconciled
    // into shotStates/completedStages here. The legacy snapshot's status
    // vocabulary (e.g. "in_progress") does not match the SSE-driven
    // ShotStatus union this hook otherwise populates from `processEvent`,
    // and unifying the two is the documented job of the Slice 11
    // stage-vocabulary work, not this slice's action-authority contract.
    // Leaving them alone means a page reload mid-run repaints shot cards
    // as fresh SSE events arrive, rather than risking a wrong badge from
    // a mismatched status enum.
  }, [])

  const fetchAndHydrate = useCallback(async (pid: string) => {
    epochRef.current += 1
    const myEpoch = epochRef.current
    const result = await apiGet<PipelineState>(`/api/projects/${pid}/pipeline-state`)
    if (epochRef.current !== myEpoch) return // superseded by a newer switch/refresh
    if (result.ok) hydrateFrom(result.data)
  }, [hydrateFrom])

  // PID boundary (Slice 8b): reset synchronously so no part of the OLD
  // project's shot/failure/stage/action state is visible even for a
  // paint, then hydrate from the NEW project's real backend state instead
  // of assuming a fresh idle run -- a project can already be mid-run,
  // paused, or pending-start when it's selected (e.g. a page reload, or
  // switching back to a project with a run left going).
  useEffect(() => {
    resetLocalState()
    if (!projectId) {
      epochRef.current += 1 // invalidate anything still in flight for the old id
      return
    }
    void fetchAndHydrate(projectId)
    return () => {
      // Also invalidate on cleanup (real unmount, or React 18 StrictMode's
      // dev-only double-invoke) even though no new fetch follows here.
      epochRef.current += 1
    }
  }, [projectId, resetLocalState, fetchAndHydrate])

  /** Public, no-arg refresh: re-fetch and re-derive running/allowed_actions
   *  (plus the other hydrated fields) from the server right now. Used
   *  after pause/resume/generate/cancel so the UI reflects CONFIRMED
   *  backend truth instead of assuming the POST means the transition
   *  already happened. No-ops when there is no active project. */
  const refreshPipelineState = useCallback(() => {
    if (!projectId) return Promise.resolve()
    return fetchAndHydrate(projectId)
  }, [projectId, fetchAndHydrate])

  // Route incoming events to the right state buckets
  const processEvent = useCallback((event: ProgressEvent) => {
    const { stage, scene_id, shot_id, image_url, video_url, take_id, take_kind, identity_score, director_review,
            coherence_score, motion_score, shot_type, failure_reason, quality_metrics } = event

    // Track pause/resume
    if (stage === 'PAUSED') { setIsPaused(true); return }
    if (stage === 'RESUMED') { setIsPaused(false); return }

    // Track active stage
    setActiveStage(stage)

    // Track completed stages
    if (event.percent >= 100 || stage === 'COMPLETE' || stage === 'DONE') {
      setCompletedStages(prev => new Set([...prev, stage]))
    }

    // Track failed shots
    if (stage === 'SHOT_FAILED' && shot_id) {
      setFailedShots(prev => [...prev, shot_id])
    }

    // Track most-recent active shot (non-failure events only)
    if (shot_id && stage !== 'SHOT_FAILED') {
      setActiveShotId(shot_id)
    }

    // Rolling notes buffer (last 20 events)
    setNotesBuffer(prev => [event, ...prev].slice(0, 20))

    // Route director review events
    if (director_review) {
      setDirectorReview(director_review)
    }

    // Route shot-level events
    if (shot_id && scene_id) {
      setShotStates(prev => {
        const next = new Map(prev)
        const existing = next.get(shot_id) || { id: shot_id, scene_id }
        const updated = { ...existing }

        if (image_url) updated.generated_image = image_url
        if (video_url) updated.generated_video = video_url
        if (take_id) updated.take_id = take_id
        if (take_kind) updated.take_kind = take_kind
        if (identity_score !== undefined && identity_score >= 0) updated.identity_score = identity_score
        if (coherence_score !== undefined && coherence_score >= 0) updated.coherence_score = coherence_score
        if (motion_score !== undefined && motion_score >= 0) updated.motion_score = motion_score
        if (shot_type) updated.shot_type = shot_type
        if (failure_reason) updated.failure_reason = failure_reason
        if (quality_metrics) updated.quality_metrics = quality_metrics

        // Map stage to shot status
        if (stage === 'PLAN_REVIEW') updated.status = 'plan_review'
        if (stage === 'KEYFRAME') updated.status = 'generating_image'
        if (stage === 'KEYFRAME_READY' || stage === 'KEYFRAME_REVIEW') updated.status = 'image_review'
        if (stage === 'PERFORMANCE') updated.status = 'generating_performance' as any
        if (stage === 'PERFORMANCE_READY' || stage === 'PERFORMANCE_REVIEW') updated.status = 'performance_review' as any
        if (stage === 'SHOT_FAILED') updated.status = 'failed'
        if (stage === 'MOTION') updated.status = 'generating_video'
        if (stage === 'MOTION_READY' || stage === 'REVIEW') updated.status = 'final_review'
        if (stage === 'POSTPROCESS_READY') updated.status = 'post_processing'
        if (stage === 'COMPLETE') updated.status = 'complete'

        next.set(shot_id, updated)
        return next
      })
    }
  }, [])

  // Compute pipeline stages with live status
  const stages = useMemo((): PipelineStage[] => {
    return PIPELINE_STAGES.map(s => ({
      ...s,
      status: completedStages.has(s.id)
        ? 'complete'
        : activeStage === s.id
          ? 'running'
          : s.status,
    }))
  }, [completedStages, activeStage])

  // Pipeline control actions -- neither flips local state optimistically.
  // Each fires the POST, then re-confirms truth from the server: the
  // request succeeding does not mean the transition already happened (the
  // pending-start window is exactly this), so `isPaused`/`running`/
  // `allowedActions` only ever change via `hydrateFrom` (Slice 8
  // requirement 5 -- never paint optimistic success).
  const pause = useCallback(async () => {
    if (!projectId) return
    await apiPost(`/api/projects/${projectId}/pause`)
    await refreshPipelineState()
  }, [projectId, refreshPipelineState])

  const resume = useCallback(async () => {
    if (!projectId) return
    await apiPost(`/api/projects/${projectId}/resume`)
    await refreshPipelineState()
  }, [projectId, refreshPipelineState])

  /** Every POST mutation below funnels through here. A non-2xx response, a
   *  non-JSON body, or a network failure ALWAYS yields an object with a
   *  truthy `.error` string (synthesizing one when the endpoint's own
   *  failure body omitted it) -- so the existing `if (!result?.error)` /
   *  `if (result?.success)` checks in ReviewStage.tsx / ScreeningStage.tsx
   *  stay truthful for every failure mode, not just the ones a given
   *  endpoint happens to encode in JSON. A real 2xx body passes through
   *  unchanged (existing callers read fields like `.take`/`.approved`
   *  straight off it). */
  const postJson = useCallback(async (path: string, body?: Record<string, any>) => {
    const result = await apiPost<Record<string, any>>(path, body)
    if (result.ok) return result.data ?? {}
    const bodyRecord = (result.body && typeof result.body === 'object' && !Array.isArray(result.body))
      ? result.body as Record<string, any>
      : {}
    return { ...bodyRecord, success: false, error: bodyRecord.error || result.error }
  }, [])

  const regenerateShot = useCallback(async (shotId: string, positivePrompt?: string, negativePrompt?: string) => {
    if (!projectId) return null
    const body: any = {}
    if (positivePrompt) body.positive_prompt = positivePrompt
    if (negativePrompt) body.negative_prompt = negativePrompt
    return postJson(`/api/projects/${projectId}/shots/${shotId}/regenerate`, body)
  }, [projectId, postJson])

  const approveShotPlan = useCallback(async (shotId: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/plan/approve`)
  }, [projectId, postJson])

  const rejectShotPlan = useCallback(async (shotId: string, reason = '') => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/plan/reject`, { reason })
  }, [projectId, postJson])

  const generateKeyframe = useCallback(async (shotId: string, positivePrompt?: string, negativePrompt?: string) => {
    if (!projectId) return null
    const body: Record<string, any> = {}
    if (positivePrompt) body.positive_prompt = positivePrompt
    if (negativePrompt) body.negative_prompt = negativePrompt
    return postJson(`/api/projects/${projectId}/shots/${shotId}/keyframes/generate`, body)
  }, [projectId, postJson])

  const restartShot = useCallback(async (shotId: string, positivePrompt?: string, negativePrompt?: string) => {
    if (!projectId) return null
    const body: Record<string, any> = {}
    if (positivePrompt) body.positive_prompt = positivePrompt
    if (negativePrompt) body.negative_prompt = negativePrompt
    return postJson(`/api/projects/${projectId}/shots/${shotId}/restart`, body)
  }, [projectId, postJson])

  const approveKeyframe = useCallback(async (shotId: string, takeId: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/keyframes/${takeId}/approve`)
  }, [projectId, postJson])

  const approvePerformance = useCallback(async (shotId: string, takeId: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/performance/${takeId}/approve`)
  }, [projectId, postJson])

  const generateMotion = useCallback(async (shotId: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/motion/generate`)
  }, [projectId, postJson])

  const approveFinal = useCallback(async (shotId: string, takeId: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/final/${takeId}/approve`)
  }, [projectId, postJson])

  const correctShot = useCallback(async (shotId: string, action: string, params: Record<string, any> = {}, takeId?: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/correct`, { action, params, take_id: takeId })
  }, [projectId, postJson])

  const diagnoseShot = useCallback(async (shotId: string, takeId?: string, deep = false) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/diagnose`, { ...(takeId ? { take_id: takeId } : {}), deep })
  }, [projectId, postJson])

  const proceedToAssembly = useCallback(async () => {
    if (!projectId) return
    return postJson(`/api/projects/${projectId}/assemble`)
  }, [projectId, postJson])

  /** S17 + S18: directorial iteration — POST flat body `{ prose, target_stage, verb?, params? }`
   *  to the iterate endpoint. On success the new take is included in the response
   *  body as `{ success: true, take: {...} }`. The caller is responsible for
   *  refreshing the project so the new take appears in the relevant take list.
   *  On 404 (CINEMA_DIRECTORIAL_ITERATION flag off), surface the error JSON
   *  rather than throwing so the IterationPanel can show an inline message.
   *  Returns `null` as the no-op contract when projectId is unset (called
   *  before a project is loaded); callers treat null as "did not run."
   *
   *  S18: `targetStage` defaults to 'keyframe' for back-compat with S17 callers
   *  (the KEYFRAME_REVIEW wiring still works without changes). `verb`+`params`
   *  are optional structured-iteration extensions; when omitted, the endpoint
   *  treats the call as freeform (the original S17 path).
   *
   *  Server endpoint accepts both nested `{intent: {...}}` and flat shapes per
   *  the F1 accept-both decision (operator Lane V #4, 2026-05-25T15-49-12Z);
   *  we send the flat shape to stay aligned with the existing 16 endpoint
   *  tests. The `verb`/`params` keys travel cleanly through DirectorialIntent
   *  validation because verb is Optional[str] and params is dict — no schema
   *  migration required for new verbs. */
  const iterateTake = useCallback(async (
    shotId: string,
    takeId: string,
    prose: string,
    targetStage: 'keyframe' | 'performance' | 'motion' = 'keyframe',
    verb?: string,
    params?: Record<string, unknown>,
  ) => {
    if (!projectId) return null
    const body: Record<string, unknown> = { prose, target_stage: targetStage }
    if (verb) {
      body.verb = verb
      body.params = params ?? {}
    }
    return postJson(`/api/projects/${projectId}/shots/${shotId}/takes/${takeId}/iterate`, body)
  }, [projectId, postJson])

  /** S20 (cycle-9 Surface B): operator approves the screened cut.
   *  POSTs to /api/projects/<pid>/screening/approve. The endpoint is
   *  feature-flagged behind CINEMA_SCREENING_STAGE; a 404 surfaces here
   *  as a JSON error rather than throwing, so the caller can render the
   *  inline error. Returns null when projectId is unset (same no-op
   *  contract as iterateTake). */
  const approveScreening = useCallback(async () => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/screening/approve`)
  }, [projectId, postJson])

  /** S21 (cycle-9 Surface B): re-assemble the cut from current approved takes.
   *  POSTs to /api/projects/<pid>/assemble/re-assemble with
   *  ``{only_if_changed: bool}``. Returns the JSON response shape:
   *    { success, new_assembled_path, regenerated_shots, cost_estimate_seconds, skipped }
   *
   *  Mirrors approveScreening's no-op-when-projectId-null contract. The
   *  endpoint is feature-flagged behind CINEMA_SCREENING_STAGE; 404 surfaces
   *  in the JSON for the caller to render.
   *
   *  ``onlyIfChanged=true`` (default) is the operator-facing button's normal
   *  click — short-circuits when nothing changed. ``false`` is reserved for
   *  a "force re-assemble" power-user override (not wired into UI for v1). */
  const reassembleProject = useCallback(async (onlyIfChanged: boolean = true) => {
    if (!projectId) return null
    // (S21 reviewer Minor #5's non-JSON/500 guard is now `postJson`'s job
    // uniformly -- see its docstring above.)
    return postJson(`/api/projects/${projectId}/assemble/re-assemble`, { only_if_changed: onlyIfChanged })
  }, [projectId, postJson])

  // Enhanced start that also processes events -- reuses the same reset
  // `usePipelineState` applies at a project switch, since starting a new
  // run within the SAME project needs to forget the previous run's shot/
  // failure/stage state too.
  const start = useCallback(() => {
    resetLocalState()
    sse.start()
  }, [sse, resetLocalState])

  return {
    shotStates,
    stages,
    activeStage,
    directorReview,
    processEvent,
    isPaused,
    failedShots,
    activeShotId,
    notesBuffer,
    // Slice 8b: server-derived lifecycle authority + refresh.
    running,
    allowedActions,
    refreshPipelineState,
    // Pipeline controls
    pause,
    resume,
    approveShotPlan,
    rejectShotPlan,
    generateKeyframe,
    approveKeyframe,
    approvePerformance,
    generateMotion,
    approveFinal,
    regenerateShot,
    restartShot,
    correctShot,
    diagnoseShot,
    proceedToAssembly,
    iterateTake,
    approveScreening,
    reassembleProject,
    // Pass-through from useSSE
    events: sse.events,
    latest: sse.latest,
    isStreaming: sse.isStreaming,
    start,
    stop: sse.stop,
  }
}
