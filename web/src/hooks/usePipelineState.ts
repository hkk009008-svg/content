import { useState, useCallback, useMemo } from 'react'
import type { ProgressEvent, ShotState, PipelineStage, DirectorReview, PipelineState } from '../types/project'
import { useSSE } from './useSSE'

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

  // Pipeline control actions
  const pause = useCallback(async () => {
    if (!projectId) return
    await fetch(`/api/projects/${projectId}/pause`, { method: 'POST' })
    setIsPaused(true)
  }, [projectId])

  const resume = useCallback(async () => {
    if (!projectId) return
    await fetch(`/api/projects/${projectId}/resume`, { method: 'POST' })
    setIsPaused(false)
  }, [projectId])

  const postJson = useCallback(async (path: string, body?: Record<string, any>) => {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    })
    return res.json()
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
    const res = await fetch(`/api/projects/${projectId}/shots/${shotId}/takes/${takeId}/iterate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return res.json()
  }, [projectId])

  /** S20 (cycle-9 Surface B): operator approves the screened cut.
   *  POSTs to /api/projects/<pid>/screening/approve. The endpoint is
   *  feature-flagged behind CINEMA_SCREENING_STAGE; a 404 surfaces here
   *  as a JSON error rather than throwing, so the caller can render the
   *  inline error. Returns null when projectId is unset (same no-op
   *  contract as iterateTake). */
  const approveScreening = useCallback(async () => {
    if (!projectId) return null
    const res = await fetch(`/api/projects/${projectId}/screening/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
    return res.json()
  }, [projectId])

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
    const res = await fetch(`/api/projects/${projectId}/assemble/re-assemble`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ only_if_changed: onlyIfChanged }),
    })
    // (S21 reviewer Minor #5 fold) Guard against a non-JSON 500/timeout
    // surface (proxy 504, HTML error page from a misconfigured route).
    // Returning a JSON-shaped object lets the UI render the error inline
    // instead of crashing on res.json() parse failure.
    if (!res.ok) {
      return { success: false, error: res.statusText || `HTTP ${res.status}` }
    }
    return res.json()
  }, [projectId])

  // Enhanced start that also processes events
  const start = useCallback(() => {
    setShotStates(new Map())
    setDirectorReview(null)
    setCompletedStages(new Set())
    setActiveStage(null)
    setIsPaused(false)
    setFailedShots([])
    setActiveShotId(null)
    setNotesBuffer([])
    sse.start()
  }, [sse])

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
