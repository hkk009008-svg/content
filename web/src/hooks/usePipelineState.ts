import { useState, useCallback, useMemo } from 'react'
import type { ProgressEvent, ShotState, PipelineStage, DirectorReview, PipelineState } from '../types/project'
import { useSSE } from './useSSE'

const PIPELINE_STAGES: PipelineStage[] = [
  { id: 'STYLE', label: 'Style Rules', status: 'pending' },
  { id: 'AUDIO', label: 'Background Music', status: 'pending' },
  { id: 'DECOMPOSE', label: 'Shot Decomposition', status: 'pending' },
  { id: 'DIRECTOR', label: 'Director Review', status: 'pending' },
  { id: 'DIALOGUE', label: 'Dialogue Audio', status: 'pending' },
  { id: 'GENERATE', label: 'Image Generation', status: 'pending' },
  { id: 'VIDEO', label: 'Video Generation', status: 'pending' },
  { id: 'INTERP', label: 'Frame Interpolation', status: 'pending' },
  { id: 'REVIEW', label: "Director's Cut", status: 'pending' },
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

  // Route incoming events to the right state buckets
  const processEvent = useCallback((event: ProgressEvent) => {
    const { stage, scene_id, shot_id, image_url, identity_score, director_review,
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
        if (identity_score !== undefined && identity_score >= 0) updated.identity_score = identity_score
        if (coherence_score !== undefined && coherence_score >= 0) updated.coherence_score = coherence_score
        if (motion_score !== undefined && motion_score >= 0) updated.motion_score = motion_score
        if (shot_type) updated.shot_type = shot_type
        if (failure_reason) updated.failure_reason = failure_reason
        if (quality_metrics) updated.quality_metrics = quality_metrics

        // Map stage to shot status
        if (stage === 'GENERATE' || stage === 'REGENERATE') updated.status = 'generating_image'
        if (stage === 'VALIDATED' || stage === 'IDENTITY_OK') updated.status = 'image_review'
        if (stage === 'REGENERATED') updated.status = 'image_review'
        if (stage === 'IDENTITY_FAIL') updated.status = 'generating_image'
        if (stage === 'SHOT_FAILED') updated.status = 'failed'
        if (stage === 'VIDEO') updated.status = 'generating_video'
        if (stage === 'INTERP' || stage === 'LIPSYNC' || stage === 'QUALITY') updated.status = 'post_processing'
        if (stage === 'UPSCALE') updated.status = 'post_processing'

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

  const regenerateShot = useCallback(async (shotId: string, positivePrompt?: string, negativePrompt?: string) => {
    if (!projectId) return null
    const body: any = {}
    if (positivePrompt) body.positive_prompt = positivePrompt
    if (negativePrompt) body.negative_prompt = negativePrompt
    const res = await fetch(`/api/projects/${projectId}/shots/${shotId}/regenerate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    return res.json()
  }, [projectId])

  const correctShot = useCallback(async (shotId: string, action: string, params: Record<string, any> = {}) => {
    if (!projectId) return null
    const res = await fetch(`/api/projects/${projectId}/shots/${shotId}/correct`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, params }),
    })
    return res.json()
  }, [projectId])

  const diagnoseShot = useCallback(async (shotId: string) => {
    if (!projectId) return null
    const res = await fetch(`/api/projects/${projectId}/shots/${shotId}/diagnose`, { method: 'POST' })
    return res.json()
  }, [projectId])

  const proceedToAssembly = useCallback(async () => {
    if (!projectId) return
    await fetch(`/api/projects/${projectId}/proceed-assembly`, { method: 'POST' })
  }, [projectId])

  // Enhanced start that also processes events
  const start = useCallback(() => {
    setShotStates(new Map())
    setDirectorReview(null)
    setCompletedStages(new Set())
    setActiveStage(null)
    setIsPaused(false)
    setFailedShots([])
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
    // Pipeline controls
    pause,
    resume,
    regenerateShot,
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
