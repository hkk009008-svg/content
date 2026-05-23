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

  const diagnoseShot = useCallback(async (shotId: string, takeId?: string) => {
    if (!projectId) return null
    return postJson(`/api/projects/${projectId}/shots/${shotId}/diagnose`, takeId ? { take_id: takeId } : {})
  }, [projectId, postJson])

  const proceedToAssembly = useCallback(async () => {
    if (!projectId) return
    return postJson(`/api/projects/${projectId}/assemble`)
  }, [projectId, postJson])

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
    // Pass-through from useSSE
    events: sse.events,
    latest: sse.latest,
    isStreaming: sse.isStreaming,
    start,
    stop: sse.stop,
  }
}
