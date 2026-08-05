import { useEffect, useId, useMemo, useState } from 'react'
import type { Project, ShotState, Scene, Shot, TakeRecord } from '../../types/project'
import TakeStrip, { LipsyncStatusBadge } from '../console/TakeStrip'
import AutoApproveBadge from '../console/AutoApproveBadge'
import RejectAutoApproveModal from '../console/RejectAutoApproveModal'
import IterationPanel from './IterationPanel'
import { shotRequiresLipsync } from '../../lib/lipsyncEvidence'
import { canResumeDeferredProviderJob } from '../../lib/providerRecovery'

const API = '/api'

const COLOR_PRESETS = [
  { id: 'warm_cinema', label: 'Warm Cinema' },
  { id: 'cool_noir', label: 'Cool Noir' },
  { id: 'vibrant', label: 'Vibrant' },
  { id: 'desaturated', label: 'Desaturated' },
  { id: 'golden_hour', label: 'Golden Hour' },
  { id: 'moonlight', label: 'Moonlight' },
  { id: 'high_contrast', label: 'High Contrast' },
  { id: 'pastel', label: 'Pastel' },
]

const SPEED_OPTIONS = [
  { factor: 0.25, label: '0.25x' },
  { factor: 0.5, label: '0.5x' },
  { factor: 0.75, label: '0.75x' },
  { factor: 1.5, label: '1.5x' },
  { factor: 2.0, label: '2x' },
]

interface Diagnosis {
  scores: Record<string, number>
  recommendations: { tool: string; reason: string }[]
}

interface Props {
  project: Project
  activeStage: string | null
  shotStates: Map<string, Partial<ShotState>>
  onApprovePlan: (shotId: string) => Promise<any>
  onRejectPlan: (shotId: string, reason?: string) => Promise<any>
  onGenerateKeyframe: (shotId: string, positive?: string, negative?: string) => Promise<any>
  onApproveKeyframe: (shotId: string, takeId: string) => Promise<any>
  onApprovePerformance: (shotId: string, takeId: string) => Promise<any>
  onGenerateMotion: (shotId: string) => Promise<any>
  onApproveFinal: (shotId: string, takeId: string) => Promise<any>
  onCorrect: (shotId: string, action: string, params?: Record<string, any>, takeId?: string) => Promise<any>
  onDiagnose: (shotId: string, takeId?: string, deep?: boolean) => Promise<any>
  onRegenerate: (shotId: string, positive?: string, negative?: string) => Promise<any>
  onProceedToAssembly: () => Promise<any>
  /** Refresh project state from the server. Called after a successful
   *  auto-approve rejection so the badge clears without waiting for the
   *  next poll cycle (per S13 code-review fix). */
  onRefreshProject: () => Promise<void> | void
  /** S17 + S18: directorial iteration. Optional — callers without the
   *  CINEMA_DIRECTORIAL_ITERATION flag simply omit this prop; the
   *  Iterate button is hidden when it's absent.
   *
   *  S18 extends the signature with `targetStage` (one of keyframe /
   *  performance / motion — matched to which review gate the panel was
   *  opened from) plus optional structured `verb`+`params` for the verb
   *  DSL. When `targetStage` is omitted, the endpoint defaults to keyframe
   *  for S17 back-compat. */
  onIterate?: (
    shotId: string,
    takeId: string,
    prose: string,
    targetStage?: 'keyframe' | 'performance' | 'motion',
    verb?: string,
    params?: Record<string, unknown>,
  ) => Promise<any>
}

function findTake(takes: TakeRecord[], takeId: string) {
  return takes.find((take) => take.id === takeId)
}

function lastTake(takes: TakeRecord[]) {
  return takes.length > 0 ? takes[takes.length - 1] : undefined
}

function formatScore(value?: number) {
  if (value == null) return null
  const pct = Math.round(value * 100)
  const color = pct >= 75 ? 'text-ok' : pct >= 55 ? 'text-warn' : 'text-fail'
  return <span className={`text-xs font-mono ${color}`}>{pct}%</span>
}

function CascadeBadge({
  meta,
  label,
}: {
  meta: TakeRecord['cascade_metadata']
  /** Prefix for the engine chip — e.g. "lipsync" renders "lipsync via X".
   *  NF-4 (P1-3): dialogue takes carry a SECOND cascade record at
   *  metadata.lipsync_cascade (the overlay lip-sync pass); cascade_metadata
   *  on those takes holds the VIDEO cascade. */
  label?: string
}) {
  if (!meta) return null
  const scoreColor = meta.score != null && meta.threshold != null
    ? label === 'lipsync'
      ? meta.validation_state === 'PASS'
        ? 'text-ok'
        : meta.validation_state === 'FAIL'
          ? 'text-fail'
          : 'text-mut'
      : meta.score >= meta.threshold
        ? 'text-ok'
        : 'text-warn'
    : null
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      <span className="rounded bg-panel px-1.5 py-0.5 text-eyebrow text-mut">
        {label ? `${label} via ${meta.engine}` : `via ${meta.engine}`}
      </span>
      {scoreColor && meta.score != null && (
        <span className={`font-mono text-eyebrow ${scoreColor}`}>
          {meta.score.toFixed(3)}
        </span>
      )}
      {meta.fallback && (
        <span className="rounded bg-fail/20 px-1.5 py-0.5 text-eyebrow text-fail">
          ⚠ FALLBACK
        </span>
      )}
    </div>
  )
}

/** Render only persisted synchronization evidence. Provider-native audio is
 *  called out, but it becomes UNKNOWN when no measured validation state is
 *  present — audio presence must never be promoted to a fabricated PASS. */
function TakeLipsyncEvidence({
  take,
  shotRequiresEvidence = false,
}: {
  take: TakeRecord
  shotRequiresEvidence?: boolean
}) {
  const state = take.metadata?.lipsync_validation_state
    ?? take.metadata?.lipsync_cascade?.validation_state
    ?? take.cascade_metadata?.validation_state
  const nativeAudioGenerated = take.cascade_metadata?.native_audio_generated === true
  const hasDialogue = take.metadata?.has_dialogue
  const showWhenUnmeasured = shotRequiresEvidence
    || hasDialogue === true
    || Boolean(take.metadata?.lipsync_cascade)
    || (nativeAudioGenerated && hasDialogue !== false)

  return (
    <LipsyncStatusBadge
      state={state}
      nativeAudioGenerated={nativeAudioGenerated}
      showWhenUnmeasured={showWhenUnmeasured}
    />
  )
}

function TakeCard({
  take,
  active,
  approved,
  showIterateButton,
  shotRequiresEvidence = false,
  onSelect,
  onApprove,
  onIterate,
}: {
  take: TakeRecord
  active: boolean
  approved: boolean
  /** S17: show the Iterate button only at KEYFRAME_REVIEW / REVIEW when onIterate is wired.
   *  S18 extends usage to the REVIEW gate; PERFORMANCE_REVIEW uses an inline iterate
   *  button next to the Approve button (renders IterationPanel below) rather than per-card. */
  showIterateButton: boolean
  shotRequiresEvidence?: boolean
  onSelect: () => void
  onApprove: () => void
  /** S18: onIterate signature carries the optional verb DSL params through. */
  onIterate?: (
    takeId: string,
    prose: string,
    verb?: string,
    params?: Record<string, unknown>,
  ) => Promise<any>
}) {
  const [iterating, setIterating] = useState(false)

  return (
    <div className={`rounded border px-2 py-2 ${active ? 'border-acc bg-acc/10' : 'border-line bg-app'}`}>
      <button onClick={onSelect} className="w-full text-left">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-tx font-medium">{take.kind}</span>
          {approved && <span className="text-eyebrow text-ok">Approved</span>}
        </div>
        <div className="mt-1 text-eyebrow text-mut font-mono break-all">{take.id}</div>
        <CascadeBadge meta={take.cascade_metadata} />
        <CascadeBadge meta={take.metadata?.lipsync_cascade} label="lipsync" />
      </button>
      <TakeLipsyncEvidence take={take} shotRequiresEvidence={shotRequiresEvidence} />
      {!approved && (
        <div className="mt-2 flex gap-2">
          <button
            onClick={onApprove}
            className="flex-1 rounded border border-ok/50 px-2 py-1 text-eyebrow text-ok hover:bg-ok/10"
          >
            Approve
          </button>
          {showIterateButton && onIterate && !iterating && (
            <button
              onClick={() => { setIterating(true) }}
              className="rounded border border-acc/50 px-2 py-1 text-eyebrow text-acc hover:bg-acc/10"
              title="Open directorial iteration panel to generate a new take with your direction"
            >
              Iterate
            </button>
          )}
        </div>
      )}
      {/* S17 + S18: inline iteration drawer — KEYFRAME_REVIEW + REVIEW + CINEMA_DIRECTORIAL_ITERATION only */}
      {iterating && onIterate && (
        <IterationPanel
          onSubmit={async (prose, verb, params) => {
            const result = await onIterate(take.id, prose, verb, params)
            // Close panel on non-error result
            if (!result?.error) {
              setIterating(false)
            }
            return result
          }}
          onCancel={() => setIterating(false)}
        />
      )}
    </div>
  )
}

function ClipCard({
  shot,
  scene,
  projectId,
  activeStage,
  shotState,
  onApprovePlan,
  onRejectPlan,
  onGenerateKeyframe,
  onApproveKeyframe,
  onApprovePerformance,
  onGenerateMotion,
  onApproveFinal,
  onCorrect,
  onDiagnose,
  onRegenerate,
  onRefreshProject,
  onIterate,
}: {
  shot: Shot
  scene: Scene
  projectId: string
  activeStage: string | null
  shotState: Partial<ShotState> | undefined
  onApprovePlan: Props['onApprovePlan']
  onRejectPlan: Props['onRejectPlan']
  onGenerateKeyframe: Props['onGenerateKeyframe']
  onApproveKeyframe: Props['onApproveKeyframe']
  onApprovePerformance: Props['onApprovePerformance']
  onGenerateMotion: Props['onGenerateMotion']
  onApproveFinal: Props['onApproveFinal']
  onCorrect: Props['onCorrect']
  onDiagnose: Props['onDiagnose']
  onRegenerate: Props['onRegenerate']
  onRefreshProject: Props['onRefreshProject']
  onIterate?: Props['onIterate']
}) {
  const [diagnosis, setDiagnosis] = useState<any | null>(null)
  const [diagnosing, setDiagnosing] = useState(false)
  const [deepDiagnosing, setDeepDiagnosing] = useState(false)
  const [loadingAction, setLoadingAction] = useState<string | null>(null)
  const [positivePrompt, setPositivePrompt] = useState(shot.prompt || '')
  const [negativePrompt, setNegativePrompt] = useState(shot.negative_constraints || '')
  const [showRegenForm, setShowRegenForm] = useState(false)
  const [keyframeRecoveryError, setKeyframeRecoveryError] = useState<string | null>(null)
  const requiresLipsync = shotRequiresLipsync(shot)
  const [rejectReason, setRejectReason] = useState(shot.plan_rejection_reason || '')
  const [rejectAutoApproveGate, setRejectAutoApproveGate] = useState<'plan' | 'image' | 'motion' | 'final' | null>(null)
  /** S18: Performance-card iteration toggle. Inline drawer below the
   *  side-by-side preview, mirroring TakeCard's iteration UX shape. */
  const [iteratingPerformance, setIteratingPerformance] = useState(false)
  const deferredKeyframeJobTitleId = useId()
  const deferredJobTitleId = useId()

  const audit = shot.auto_approve_audit || []
  const [selectedKeyframeTakeId, setSelectedKeyframeTakeId] = useState(shot.approved_keyframe_take_id || lastTake(shot.keyframe_takes || [])?.id || '')
  const [selectedFinalTakeId, setSelectedFinalTakeId] = useState(shot.approved_final_take_id || lastTake(shot.postprocess_variants || [])?.id || lastTake(shot.motion_takes || [])?.id || '')

  const keyframeTakes = shot.keyframe_takes || []
  const finalTakes = useMemo(() => [...(shot.motion_takes || []), ...(shot.postprocess_variants || [])], [shot.motion_takes, shot.postprocess_variants])
  const selectedKeyframe = findTake(keyframeTakes, selectedKeyframeTakeId) || lastTake(keyframeTakes)
  const selectedFinal = findTake(finalTakes, selectedFinalTakeId) || lastTake(finalTakes)
  const latestDiagnostic = shot.diagnostics && shot.diagnostics.length > 0 ? shot.diagnostics[shot.diagnostics.length - 1] : null
  const statusBadge = activeStage === 'PLAN_REVIEW'
    ? 'Shot Plan'
    : activeStage === 'KEYFRAME_REVIEW'
      ? 'Keyframe Review'
      : activeStage === 'PERFORMANCE_REVIEW'
        ? 'Performance Review'
        : 'Final Review'

  // --- Performance takes: surface when stage is PERFORMANCE_REVIEW ---
  // Mirrors the keyframe/final patterns above. When the performance phase
  // produced a take, its video clip is what the operator approves.
  const performanceTakes = shot.performance_takes || []
  const latestPerformanceTake = performanceTakes.length > 0
    ? performanceTakes[performanceTakes.length - 1]
    : null
  const approvedPerformanceTakeId = shot.approved_performance_take_id || latestPerformanceTake?.id || ''
  const performanceEngine = shot.performance_engine || ''
  const drivingVideoPath = shot.driving_video_path || ''
  const performanceVideoPath = latestPerformanceTake?.path || ''
  const performanceMetadata = latestPerformanceTake?.metadata || {}
  const motionFidelity: number | null | undefined = performanceMetadata.motion_fidelity
  const performanceIdentity: number | null | undefined = performanceMetadata.identity_score
  const resolvedShotType = shot.shot_type
  const deferredKeyframeJob = shot.deferred_keyframe_job
  const deferredMotionJob = shot.deferred_motion_job
  const deferredJobIsRecovery = deferredMotionJob?.status === 'recovery_required'
  const deferredJobStatusLabel = deferredJobIsRecovery ? 'Recovery Required' : 'Pending'
  const deferredJobEngine = deferredMotionJob?.engine?.trim() || 'Provider'
  const deferredJobCanResume = canResumeDeferredProviderJob(
    deferredJobEngine,
    deferredMotionJob?.job_id,
  )

  useEffect(() => {
    if (shot.approved_keyframe_take_id) {
      setSelectedKeyframeTakeId(shot.approved_keyframe_take_id)
    } else if (!selectedKeyframeTakeId && keyframeTakes.length > 0) {
      setSelectedKeyframeTakeId(keyframeTakes[keyframeTakes.length - 1].id)
    }
  }, [keyframeTakes, selectedKeyframeTakeId, shot.approved_keyframe_take_id])

  useEffect(() => {
    if (shot.approved_final_take_id) {
      setSelectedFinalTakeId(shot.approved_final_take_id)
    } else if (!selectedFinalTakeId && finalTakes.length > 0) {
      setSelectedFinalTakeId(finalTakes[finalTakes.length - 1].id)
    }
  }, [finalTakes, selectedFinalTakeId, shot.approved_final_take_id])

  useEffect(() => {
    if (deferredKeyframeJob) setShowRegenForm(false)
  }, [deferredKeyframeJob])

  const imageUrl = selectedKeyframe?.path || shotState?.generated_image || shot.generated_image
  const videoUrl = selectedFinal?.path || shotState?.generated_video || shot.generated_video
  const activeTakeId = selectedFinal?.id || selectedKeyframe?.id

  const runAction = async (label: string, action: () => Promise<any>) => {
    setLoadingAction(label)
    try {
      return await action()
    } finally {
      setLoadingAction(null)
    }
  }

  const handleDiagnose = async () => {
    if (!activeTakeId) return
    setDiagnosing(true)
    const result = await onDiagnose(shot.id, activeTakeId)
    setDiagnosis(result)
    setDiagnosing(false)
  }

  const handleDeepDiagnose = async () => {
    if (!activeTakeId) return
    setDeepDiagnosing(true)
    const result = await onDiagnose(shot.id, activeTakeId, true)
    setDiagnosis(result)
    setDeepDiagnosing(false)
  }

  const handleCorrect = async (action: string, params: Record<string, any> = {}) => {
    if (!selectedFinal?.id) return
    await runAction(action, () => onCorrect(shot.id, action, params, selectedFinal.id))
  }

  const handleGenerateKeyframeClick = async () => {
    if (deferredKeyframeJob) return
    await runAction('keyframe', () => onGenerateKeyframe(shot.id, positivePrompt, negativePrompt))
    setShowRegenForm(false)
  }

  const handleRegenerate = async () => {
    if (deferredKeyframeJob) return
    // Full restart: clear every downstream approval and regenerate the keyframe
    // with the (possibly edited) prompt. See ShotController.restart_shot.
    await runAction('regenerate', () => onRegenerate(shot.id, positivePrompt, negativePrompt))
    setShowRegenForm(false)
  }

  const handleResolveDeferredKeyframeJob = async () => {
    if (!deferredKeyframeJob) return

    const jobId = deferredKeyframeJob.job_id?.trim() || 'not reported'
    const confirmed = window.confirm(
      `Confirm that keyframe job ${jobId} was reconciled manually? This clears the recovery block and does not create a new keyframe.`,
    )
    if (!confirmed) return

    setKeyframeRecoveryError(null)
    await runAction('keyframe-recovery', async () => {
      let response: Response
      try {
        response = await fetch(
          `${API}/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shot.id)}/keyframes/recovery/resolve`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirmed: true }),
          },
        )
      } catch {
        setKeyframeRecoveryError('Could not reach the server. The keyframe recovery block remains in place.')
        return
      }

      let payload: { error?: unknown; detail?: unknown } = {}
      try {
        payload = await response.json() as { error?: unknown; detail?: unknown }
      } catch {
        // An empty or non-JSON response is valid on success; HTTP status remains authoritative.
      }

      if (!response.ok) {
        const detail = typeof payload.error === 'string'
          ? payload.error
          : typeof payload.detail === 'string'
            ? payload.detail
            : `Server error ${response.status}`
        setKeyframeRecoveryError(`${detail} The keyframe recovery block remains in place.`)
        return
      }

      try {
        await onRefreshProject()
      } catch {
        setKeyframeRecoveryError('The recovery record was resolved, but the project could not be refreshed. Reload the project before continuing.')
      }
    })
  }

  return (
    <div className="rounded-lg border border-line bg-panel">
      <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-tx">{scene.title}</span>
            <span className="rounded bg-app px-2 py-0.5 text-eyebrow text-mut">{statusBadge}</span>
            {shot.plan_status === 'approved' && <span className="text-eyebrow text-ok">Plan approved</span>}
            {shot.approved_keyframe_take_id && <span className="text-eyebrow text-ok">Keyframe locked</span>}
            {shot.approved_final_take_id && <span className="text-eyebrow text-ok">Final locked</span>}
          </div>
          <div className="mt-1 text-xs text-mut">{shot.id}</div>
        </div>
        {loadingAction && <div className="text-xs text-acc">{loadingAction}...</div>}
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-[280px_1fr]">
        <div className="space-y-3">
          {videoUrl ? (
            <video
              src={`${API}/projects/${projectId}/file?path=${encodeURIComponent(videoUrl)}`}
              controls
              className="w-full rounded border border-line bg-black"
            />
          ) : imageUrl ? (
            <img
              src={`${API}/projects/${projectId}/file?path=${encodeURIComponent(imageUrl)}`}
              className="w-full rounded border border-line object-cover"
            />
          ) : (
            <div className="flex aspect-video items-center justify-center rounded border border-line bg-app text-sm text-mut">
              No take yet
            </div>
          )}

          <div className="rounded border border-line bg-app px-3 py-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-mut">Identity</span>
              {formatScore(shotState?.identity_score ?? latestDiagnostic?.scores?.identity)}
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-mut">Coherence</span>
              {formatScore(diagnosis?.scores?.coherence ?? latestDiagnostic?.scores?.coherence)}
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-mut">Motion</span>
              {formatScore(diagnosis?.scores?.motion ?? latestDiagnostic?.scores?.motion)}
            </div>
            {selectedFinal && (
              selectedFinal.cascade_metadata
              || selectedFinal.metadata?.lipsync_cascade
              || selectedFinal.metadata?.lipsync_validation_state
              || selectedFinal.metadata?.has_dialogue === true
              || requiresLipsync
            ) && (
              <div className="mt-2 border-t border-line pt-2">
                <CascadeBadge meta={selectedFinal.cascade_metadata} />
                <CascadeBadge meta={selectedFinal.metadata?.lipsync_cascade} label="lipsync" />
                <TakeLipsyncEvidence
                  take={selectedFinal}
                  shotRequiresEvidence={requiresLipsync}
                />
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded border border-line bg-app px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-mut">Plan</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => runAction('approve-plan', () => onApprovePlan(shot.id))}
                  className="rounded border border-ok/50 px-2 py-1 text-eyebrow-lg text-ok hover:bg-ok/10"
                >
                  Approve Plan
                </button>
                <button
                  onClick={() => runAction('reject-plan', () => onRejectPlan(shot.id, rejectReason))}
                  className="rounded border border-fail/50 px-2 py-1 text-eyebrow-lg text-fail hover:bg-fail/10"
                >
                  Reject Plan
                </button>
              </div>
            </div>
            <p className="mt-2 text-sm text-tx">{shot.prompt}</p>
            <div className="mt-2 flex flex-wrap gap-2 text-eyebrow-lg text-mut">
              <span className="rounded bg-panel px-2 py-1">{shot.camera}</span>
              <span className="rounded bg-panel px-2 py-1">{shot.target_api}</span>
              {shot.continuity_constraints && <span className="rounded bg-panel px-2 py-1">{shot.continuity_constraints}</span>}
            </div>
            {shot.plan_auto_approved && (
              <AutoApproveBadge
                gate="plan"
                audit={audit}
                onReject={() => setRejectAutoApproveGate('plan')}
              />
            )}
            <input
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
              placeholder="Reason if rejecting this shot plan"
              className="mt-3 w-full rounded border border-line bg-panel px-2 py-1.5 text-xs text-tx"
            />
          </section>

          <section className="rounded border border-line bg-app px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-mut">Keyframes</h3>
              <button
                onClick={handleGenerateKeyframeClick}
                disabled={shot.plan_status !== 'approved' || Boolean(deferredKeyframeJob) || loadingAction === 'keyframe'}
                aria-describedby={deferredKeyframeJob ? deferredKeyframeJobTitleId : undefined}
                className="rounded border border-acc/50 px-2 py-1 text-eyebrow-lg text-acc hover:bg-acc/10 disabled:opacity-40"
              >
                Generate Keyframe
              </button>
            </div>
            {deferredKeyframeJob && (
              <div
                role="alert"
                aria-labelledby={deferredKeyframeJobTitleId}
                className="mt-3 rounded border border-fail/50 bg-fail/5 px-3 py-3 text-xs"
              >
                <h4 id={deferredKeyframeJobTitleId} className="font-semibold text-fail">
                  Keyframe Job Recovery Required
                </h4>
                <p className="mt-2 leading-relaxed text-tx">
                  A previous provider attempt is unresolved. New keyframe generation stays disabled until an operator reconciles this saved job.
                </p>
                <dl className="mt-2 grid gap-x-4 gap-y-1 text-mut sm:grid-cols-2">
                  <div>
                    <dt className="inline">Status: </dt>
                    <dd className="inline font-mono text-tx">{deferredKeyframeJob.status}</dd>
                  </div>
                  <div className="min-w-0">
                    <dt className="inline">Job ID: </dt>
                    <dd className="inline break-all font-mono text-tx">
                      {deferredKeyframeJob.job_id?.trim() || 'not reported'}
                    </dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="inline">Reason: </dt>
                    <dd className="inline text-tx">
                      {deferredKeyframeJob.reason?.trim() || 'No reason was reported.'}
                    </dd>
                  </div>
                  {deferredKeyframeJob.resolve_after && (
                    <div className="sm:col-span-2">
                      <dt className="inline">Manual reconciliation available after: </dt>
                      <dd className="inline font-mono text-tx">
                        {deferredKeyframeJob.resolve_after}
                      </dd>
                    </div>
                  )}
                </dl>
                <p className="mt-2 leading-relaxed text-mut">
                  Confirm only after checking the provider record. Reconciliation clears this block; it does not retry or create a take.
                </p>
                <button
                  onClick={handleResolveDeferredKeyframeJob}
                  disabled={loadingAction === 'keyframe-recovery'}
                  aria-busy={loadingAction === 'keyframe-recovery'}
                  className="mt-3 rounded border border-fail/50 px-2 py-1 text-eyebrow-lg text-fail hover:bg-fail/10 disabled:opacity-40"
                >
                  {loadingAction === 'keyframe-recovery' ? 'Reconciling…' : 'Confirm Manual Reconciliation'}
                </button>
                {keyframeRecoveryError && (
                  <p role="status" className="mt-2 leading-relaxed text-fail">
                    {keyframeRecoveryError}
                  </p>
                )}
              </div>
            )}
            {keyframeTakes.length > 0 ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {keyframeTakes.map((take) => (
                  <TakeCard
                    key={take.id}
                    take={take}
                    active={selectedKeyframe?.id === take.id}
                    approved={shot.approved_keyframe_take_id === take.id}
                    showIterateButton={activeStage === 'KEYFRAME_REVIEW' && Boolean(onIterate) && !deferredKeyframeJob}
                    onSelect={() => setSelectedKeyframeTakeId(take.id)}
                    onApprove={() => runAction(`approve-${take.id}`, () => onApproveKeyframe(shot.id, take.id))}
                    onIterate={onIterate ? (takeId, prose, verb, params) =>
                      onIterate(shot.id, takeId, prose, 'keyframe', verb, params)
                    : undefined}
                  />
                ))}
              </div>
            ) : (
              <div className="mt-3 text-xs text-mut">No keyframe takes yet.</div>
            )}
            {shot.image_auto_approved && (
              <AutoApproveBadge
                gate="image"
                audit={audit}
                onReject={() => setRejectAutoApproveGate('image')}
              />
            )}

            {showRegenForm ? (
              <div className="mt-3 space-y-2 rounded border border-acc/30 bg-panel px-3 py-3">
                <textarea
                  value={positivePrompt}
                  onChange={(event) => setPositivePrompt(event.target.value)}
                  rows={3}
                  className="w-full rounded border border-line bg-app px-2 py-1.5 text-xs text-tx"
                />
                <textarea
                  value={negativePrompt}
                  onChange={(event) => setNegativePrompt(event.target.value)}
                  rows={2}
                  className="w-full rounded border border-line bg-app px-2 py-1.5 text-xs text-tx"
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleRegenerate}
                    disabled={Boolean(deferredKeyframeJob) || loadingAction === 'regenerate'}
                    className="rounded bg-acc px-3 py-1.5 text-xs text-white"
                  >
                    Create New Take
                  </button>
                  <button
                    onClick={() => setShowRegenForm(false)}
                    className="rounded border border-line px-3 py-1.5 text-xs text-mut"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowRegenForm(true)}
                disabled={Boolean(deferredKeyframeJob)}
                aria-describedby={deferredKeyframeJob ? deferredKeyframeJobTitleId : undefined}
                className="mt-3 text-xs text-acc hover:text-acc disabled:cursor-not-allowed disabled:opacity-40"
              >
                Adjust prompts and create another keyframe take
              </button>
            )}
          </section>

          {/* Performance Capture section — visible across all review stages so
              operator can monitor + replace the driving reference at any point.
              Highlighted with a brass accent when PERFORMANCE_REVIEW is active. */}
          <section className={`rounded border px-3 py-3 ${
            activeStage === 'PERFORMANCE_REVIEW'
              ? 'border-acc/60 bg-acc/5'
              : 'border-line bg-app'
          }`}>
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-mut">
                Performance Capture
                {performanceEngine && performanceEngine !== 'SKIP' && (
                  <span className="ml-2 rounded bg-acc/20 px-1.5 py-0.5 text-eyebrow-lg text-acc">
                    {performanceEngine}
                  </span>
                )}
                {performanceEngine === 'SKIP' && (
                  <span className="ml-2 rounded bg-panel px-1.5 py-0.5 text-eyebrow-lg text-mut">
                    SKIP (wide / no characters)
                  </span>
                )}
              </h3>
              <div className="flex gap-2">
                <label className="rounded border border-acc/50 px-2 py-1 text-eyebrow-lg text-acc hover:bg-acc/10 cursor-pointer">
                  {drivingVideoPath ? '↻ Replace driving' : '+ Upload driving'}
                  <input
                    type="file"
                    accept="video/*"
                    className="hidden"
                    onChange={async (e) => {
                      const f = e.target.files?.[0]
                      if (!f) return
                      const fd = new FormData()
                      fd.append('driving_video', f)
                      await fetch(`${API}/projects/${projectId}/shots/${shot.id}/upload-driving-video`, {
                        method: 'POST', body: fd,
                      })
                    }}
                  />
                </label>
                {latestPerformanceTake && shot.approved_performance_take_id !== latestPerformanceTake.id && (
                  <button
                    onClick={() => runAction('approve-performance', () => onApprovePerformance(shot.id, latestPerformanceTake.id))}
                    disabled={loadingAction === 'approve-performance'}
                    className="rounded border border-ok/50 px-2 py-1 text-eyebrow-lg text-ok hover:bg-ok/10 disabled:opacity-40"
                  >
                    {loadingAction === 'approve-performance' ? 'Approving…' : 'Approve'}
                  </button>
                )}
                {approvedPerformanceTakeId && (
                  <button
                    onClick={async () => {
                      if (!confirm('Clear performance take? Next run will regenerate.')) return
                      await fetch(`${API}/projects/${projectId}/shots/${shot.id}/performance`, { method: 'DELETE' })
                    }}
                    className="rounded border border-fail/50 px-2 py-1 text-eyebrow-lg text-fail hover:bg-fail/10"
                  >
                    Re-record (clear)
                  </button>
                )}
                {/* S18: PERFORMANCE_REVIEW gate exposes Iterate when there's a take to iterate from.
                    Inline-rendered inside the Performance Capture section because performance takes
                    don't use TakeCard (Lane V #5 noted the PerformanceCard absence — this is the
                    matching wiring without adding a new card abstraction). */}
                {activeStage === 'PERFORMANCE_REVIEW'
                  && onIterate
                  && latestPerformanceTake
                  && !iteratingPerformance && (
                  <button
                    onClick={() => setIteratingPerformance(true)}
                    className="rounded border border-acc/50 px-2 py-1 text-eyebrow-lg text-acc hover:bg-acc/10"
                    title="Open directorial iteration panel to generate a new performance take"
                  >
                    Iterate
                  </button>
                )}
              </div>
            </div>

            {/* Side-by-side preview: driving reference on the left, captured performance on the right.
                Delegated to TakeStrip — also consumed by Monitor (A3). */}
            <TakeStrip
              drivingUrl={drivingVideoPath || null}
              performanceUrl={performanceVideoPath || null}
              projectId={projectId}
            />

            {/* S18: inline iteration drawer for PERFORMANCE_REVIEW. target_stage='performance' routes
                regenerate_with_intent → generate_performance_take per cinema/shots/controller.py:1202. */}
            {iteratingPerformance && onIterate && latestPerformanceTake && (
              <IterationPanel
                onSubmit={async (prose, verb, params) => {
                  const result = await onIterate(
                    shot.id, latestPerformanceTake.id, prose, 'performance', verb, params,
                  )
                  if (!result?.error) setIteratingPerformance(false)
                  return result
                }}
                onCancel={() => setIteratingPerformance(false)}
              />
            )}

            {/* Scores from the identity + motion gates */}
            {(performanceIdentity != null || motionFidelity != null) && (
              <>
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded bg-panel px-2 py-1.5">
                    <div className="text-mut uppercase text-eyebrow-lg">Identity (GhostFaceNet)</div>
                    <div className="mt-0.5 font-mono">
                      {typeof performanceIdentity === 'number'
                        ? performanceIdentity.toFixed(3)
                        : '—'}
                    </div>
                  </div>
                  <div className="rounded bg-panel px-2 py-1.5">
                    <div className="text-mut uppercase text-eyebrow-lg">Motion fidelity</div>
                    <div className="mt-0.5 font-mono">
                      {typeof motionFidelity === 'number'
                        ? motionFidelity.toFixed(3)
                        : motionFidelity === null
                          ? 'inconclusive'
                          : '—'}
                    </div>
                  </div>
                </div>
                {performanceMetadata.motion_floor_failed === true && resolvedShotType && (
                  <span
                    role="status"
                    className="ml-2 rounded bg-fail/20 px-1.5 py-0.5 text-eyebrow-lg text-fail"
                  >
                    below {resolvedShotType} floor
                  </span>
                )}
              </>
            )}

            {performanceEngine === 'SKIP' && !performanceVideoPath && (
              <p className="mt-3 text-xs text-mut italic">
                Skipped: this shot doesn't benefit from performance capture (no characters or framing too wide).
                Motion will use plain text-to-video.
              </p>
            )}
          </section>

          <section className="rounded border border-line bg-app px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-mut">Motion and Final Takes</h3>
              {deferredMotionJob && !deferredJobCanResume ? (
                <span className="rounded border border-fail/40 px-2 py-1 text-eyebrow-lg text-fail">
                  Manual Recovery Required
                </span>
              ) : (
                <button
                  onClick={() => runAction('motion', () => onGenerateMotion(shot.id))}
                  disabled={(!shot.approved_keyframe_take_id && !deferredMotionJob) || loadingAction === 'motion'}
                  aria-busy={loadingAction === 'motion'}
                  title={deferredMotionJob
                    ? `Checks or resumes the saved ${deferredJobEngine} provider job; no new fallback provider is started.`
                    : undefined}
                  className="rounded border border-acc/50 px-2 py-1 text-eyebrow-lg text-acc hover:bg-acc/10 disabled:opacity-40"
                >
                  {loadingAction === 'motion'
                    ? deferredMotionJob ? 'Checking / resuming…' : 'Generating…'
                    : deferredMotionJob ? `Check / Resume ${deferredJobEngine} Job` : 'Generate Motion'}
                </button>
              )}
            </div>
            {deferredMotionJob && (
              <div
                role={deferredJobIsRecovery ? 'alert' : 'status'}
                aria-labelledby={deferredJobTitleId}
                className={`mt-3 rounded border px-3 py-3 text-xs ${
                  deferredJobIsRecovery
                    ? 'border-fail/50 bg-fail/5'
                    : 'border-warn/50 bg-warn/5'
                }`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h4
                    id={deferredJobTitleId}
                    className={`font-semibold ${deferredJobIsRecovery ? 'text-fail' : 'text-warn'}`}
                  >
                    {deferredJobEngine} Job {deferredJobStatusLabel}
                  </h4>
                  <span className="rounded bg-app px-2 py-0.5 font-mono text-eyebrow-lg text-mut">
                    {deferredMotionJob.engine}
                  </span>
                </div>
                {deferredMotionJob.reason && (
                  <p className="mt-2 leading-relaxed text-tx">{deferredMotionJob.reason}</p>
                )}
                <dl className="mt-2 grid gap-x-4 gap-y-1 text-mut sm:grid-cols-2">
                  {deferredMotionJob.job_id && (
                    <div className="min-w-0">
                      <dt className="inline">Job ID: </dt>
                      <dd className="inline break-all font-mono text-tx">{deferredMotionJob.job_id}</dd>
                    </div>
                  )}
                  {deferredMotionJob.provider_status && (
                    <div>
                      <dt className="inline">Provider status: </dt>
                      <dd className="inline font-mono text-tx">{deferredMotionJob.provider_status}</dd>
                    </div>
                  )}
                  {Array.isArray(deferredMotionJob.attempts) && deferredMotionJob.attempts.length > 0 && (
                    <div>
                      <dt className="inline">Attempts: </dt>
                      <dd className="inline font-mono text-tx">
                        {deferredMotionJob.attempts.filter((attempt) => typeof attempt === 'string').join(' → ')}
                      </dd>
                    </div>
                  )}
                  {typeof deferredMotionJob.duration_s === 'number' && Number.isFinite(deferredMotionJob.duration_s) && (
                    <div>
                      <dt className="inline">Requested duration: </dt>
                      <dd className="inline font-mono text-tx">{deferredMotionJob.duration_s}s</dd>
                    </div>
                  )}
                  {typeof deferredMotionJob.billed === 'boolean' && (
                    <div>
                      <dt className="inline">Provider billing: </dt>
                      <dd className="inline text-tx">{deferredMotionJob.billed ? 'reported' : 'not reported'}</dd>
                    </div>
                  )}
                  {deferredMotionJob.updated_at && (
                    <div>
                      <dt className="inline">Updated: </dt>
                      <dd className="inline font-mono text-tx">
                        <time dateTime={deferredMotionJob.updated_at}>{deferredMotionJob.updated_at}</time>
                      </dd>
                    </div>
                  )}
                </dl>
                <p className="mt-2 leading-relaxed text-mut">
                  {deferredJobCanResume
                    ? `Check / Resume uses this saved ${deferredJobEngine} job. It does not start a fallback provider.`
                    : 'Automatic recovery is unavailable. Use the saved job ID in the provider console; this record blocks fallback generation.'}
                </p>
              </div>
            )}
            {finalTakes.length > 0 ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {finalTakes.map((take) => (
                  <TakeCard
                    key={take.id}
                    take={take}
                    active={selectedFinal?.id === take.id}
                    approved={shot.approved_final_take_id === take.id}
                    shotRequiresEvidence={requiresLipsync}
                    /* S18: REVIEW gate now exposes Iterate for motion takes too.
                       Postprocess-variant takes (kind != 'motion') stay non-iterable
                       — they're derivative of an approved motion take, not a
                       regeneration target. */
                    showIterateButton={
                      activeStage === 'REVIEW'
                      && Boolean(onIterate)
                      && take.kind === 'motion'
                    }
                    onSelect={() => setSelectedFinalTakeId(take.id)}
                    onApprove={() => runAction(`approve-${take.id}`, () => onApproveFinal(shot.id, take.id))}
                    onIterate={onIterate ? (takeId, prose, verb, params) =>
                      onIterate(shot.id, takeId, prose, 'motion', verb, params)
                    : undefined}
                  />
                ))}
              </div>
            ) : (
              <div className="mt-3 text-xs text-mut">No motion or postprocess takes yet.</div>
            )}
            {shot.motion_auto_approved && (
              <AutoApproveBadge
                gate="motion"
                audit={audit}
                onReject={() => setRejectAutoApproveGate('motion')}
              />
            )}
            {shot.final_auto_approved && (
              <AutoApproveBadge
                gate="final"
                audit={audit}
                onReject={() => setRejectAutoApproveGate('final')}
              />
            )}

            <div className="mt-3 flex flex-wrap gap-2">
              {[
                { action: 'face_swap', label: 'Face Swap' },
                { action: 'lip_sync', label: 'Lip Sync' },
                { action: 'rife', label: 'RIFE Smooth' },
                { action: 'upscale', label: 'Upscale' },
              ].map((tool) => (
                <button
                  key={tool.action}
                  onClick={() => handleCorrect(tool.action)}
                  disabled={!selectedFinal?.id}
                  className="rounded border border-line px-2 py-1 text-eyebrow-lg text-tx hover:bg-head disabled:opacity-40"
                >
                  {tool.label}
                </button>
              ))}
              <select
                aria-label="Color grade preset"
                onChange={(event) => {
                  if (event.target.value) handleCorrect('color_grade', { preset: event.target.value })
                  event.target.value = ''
                }}
                disabled={!selectedFinal?.id}
                className="rounded border border-line bg-panel px-2 py-1 text-eyebrow-lg text-tx disabled:opacity-40"
              >
                <option value="">Color Grade</option>
                {COLOR_PRESETS.map((preset) => (
                  <option key={preset.id} value={preset.id}>{preset.label}</option>
                ))}
              </select>
              <select
                aria-label="Playback speed correction"
                onChange={(event) => {
                  if (event.target.value) handleCorrect('speed', { factor: parseFloat(event.target.value) })
                  event.target.value = ''
                }}
                disabled={!selectedFinal?.id}
                className="rounded border border-line bg-panel px-2 py-1 text-eyebrow-lg text-tx disabled:opacity-40"
              >
                <option value="">Speed</option>
                {SPEED_OPTIONS.map((option) => (
                  <option key={option.factor} value={option.factor}>{option.label}</option>
                ))}
              </select>
              <button
                onClick={handleDiagnose}
                disabled={!activeTakeId || diagnosing}
                className="rounded border border-line px-2 py-1 text-eyebrow-lg text-acc hover:bg-acc/10 disabled:opacity-40"
              >
                {diagnosing ? 'Diagnosing...' : 'Diagnose'}
              </button>
              <button
                onClick={handleDeepDiagnose}
                disabled={!activeTakeId || deepDiagnosing || diagnosis?.deep_available === false}
                className="rounded border border-warn/50 px-2 py-1 text-eyebrow-lg text-warn hover:bg-warn/10 disabled:opacity-40"
                title={diagnosis?.deep_available === false ? 'Deep diagnosis not available for this take' : 'Run LLM-powered deep diagnosis'}
              >
                {deepDiagnosing ? 'Deep diagnosing...' : 'Deep diagnose'}
              </button>
            </div>

            {(diagnosis?.recommendations?.length || latestDiagnostic?.recommendations?.length) ? (
              <div className="mt-3 rounded border border-warn/20 bg-warn/5 px-3 py-2 text-xs">
                {(diagnosis?.recommendations || latestDiagnostic?.recommendations || []).map((recommendation: { tool: string; reason: string }, index: number) => (
                  <div key={`${recommendation.tool}-${index}`} className="mt-1 flex items-center gap-2">
                    <span className="text-warn">{recommendation.tool}</span>
                    <span className="text-mut">{recommendation.reason}</span>
                  </div>
                ))}
              </div>
            ) : null}

            {/* Remediation advisory — shown on identity failure, from diagnose result or inline take metadata */}
            {(() => {
              const activeTake = activeTakeId
                ? findTake([...keyframeTakes, ...finalTakes], activeTakeId)
                : null
              const advisory = diagnosis?.remediation_advisory ?? activeTake?.metadata?.remediation_advisory
              if (!advisory) return null
              return (
                <div className="mt-3 rounded border border-warn/30 bg-warn/5 px-3 py-3 text-xs space-y-2">
                  <div className="font-semibold uppercase tracking-wide text-warn text-eyebrow-lg">
                    Identity Remediation Advisory
                  </div>
                  {advisory.failure_reason && (
                    <div className="text-mut">{advisory.failure_reason}</div>
                  )}
                  {advisory.suggested_negative_prompt && (
                    <div className="space-y-1">
                      <div className="text-mut uppercase text-eyebrow tracking-wide">Suggested negative prompt</div>
                      <code className="block font-mono bg-app px-2 py-1.5 rounded text-tx break-all whitespace-pre-wrap">
                        {advisory.suggested_negative_prompt}
                      </code>
                      <button
                        onClick={() => setNegativePrompt(advisory.suggested_negative_prompt)}
                        className="text-acc hover:text-acc underline underline-offset-2"
                      >
                        Apply negative prompt
                      </button>
                    </div>
                  )}
                  {advisory.suggested_pulid_adjustment && (
                    <div className="text-mut">
                      <span className="text-warn">PuLID adjustment:</span>{' '}
                      {typeof advisory.suggested_pulid_adjustment === 'number'
                        ? `PuLID weight ${advisory.suggested_pulid_adjustment > 0 ? '+' : ''}${advisory.suggested_pulid_adjustment}`
                        : String(advisory.suggested_pulid_adjustment)}
                    </div>
                  )}
                </div>
              )
            })()}

            {/* Deep advisory — LLM diagnosis result */}
            {diagnosis?.advisory_deep && (
              <div className="mt-3 rounded border border-warn/30 bg-warn/5 px-3 py-3 text-xs space-y-2">
                <div className="font-semibold uppercase tracking-wide text-warn text-eyebrow-lg">
                  Deep Diagnosis
                  <span className="ml-2 rounded bg-app px-1.5 py-0.5 text-mut font-normal normal-case tracking-normal">
                    {diagnosis.advisory_deep.source ?? 'llm'}
                  </span>
                </div>
                {diagnosis.advisory_deep.visual_findings && (
                  <div className="space-y-1">
                    <div className="text-mut uppercase text-eyebrow tracking-wide">Visual findings</div>
                    <div className="text-mut">{diagnosis.advisory_deep.visual_findings}</div>
                  </div>
                )}
                {diagnosis.advisory_deep.diagnosis && (
                  <div className="text-mut">{diagnosis.advisory_deep.diagnosis}</div>
                )}
                {diagnosis.advisory_deep.prompt_mutation && (
                  <div className="space-y-1">
                    <div className="text-mut uppercase text-eyebrow tracking-wide">Prompt mutation</div>
                    <code className="block font-mono bg-app px-2 py-1.5 rounded text-tx break-all whitespace-pre-wrap">
                      {diagnosis.advisory_deep.prompt_mutation}
                    </code>
                  </div>
                )}
                {diagnosis.advisory_deep.mutation_focus && (
                  <div className="text-mut">
                    <span className="text-warn">Focus:</span>{' '}
                    {diagnosis.advisory_deep.mutation_focus}
                  </div>
                )}
                {diagnosis.advisory_deep.decision && (
                  <div className="text-mut">
                    <span className="text-warn">Decision:</span>{' '}
                    {diagnosis.advisory_deep.decision}
                  </div>
                )}
              </div>
            )}

            {/* Deep error note */}
            {diagnosis?.deep_error && (
              <div className="mt-2 text-eyebrow-lg text-dim italic">
                Deep diagnosis unavailable: {diagnosis.deep_error}
              </div>
            )}
          </section>
        </div>
      </div>

      {/* Auto-approve rejection modal — opened by badge Reject affordance.
          onSubmit refreshes the project so the badge clears immediately —
          per S13 code-review fix (without this, the badge keeps showing
          auto-approved until the next poll cycle, lying about shot state). */}
      {rejectAutoApproveGate && (
        <RejectAutoApproveModal
          projectId={projectId}
          shotId={shot.id}
          gate={rejectAutoApproveGate}
          isOpen={true}
          onClose={() => setRejectAutoApproveGate(null)}
          onSubmit={() => {
            setRejectAutoApproveGate(null)
            void onRefreshProject()
          }}
        />
      )}
    </div>
  )
}

export default function ReviewStage({
  project,
  activeStage,
  shotStates,
  onApprovePlan,
  onRejectPlan,
  onGenerateKeyframe,
  onApproveKeyframe,
  onApprovePerformance,
  onGenerateMotion,
  onApproveFinal,
  onCorrect,
  onDiagnose,
  onRegenerate,
  onProceedToAssembly,
  onRefreshProject,
  onIterate,
}: Props) {
  const allShots: { shot: Shot; scene: Scene }[] = []
  for (const scene of project.scenes) {
    for (const shot of scene.shots || []) {
      allShots.push({ shot, scene })
    }
  }

  const stageCopy = activeStage === 'PLAN_REVIEW'
    ? 'Approve or reject shot plans before any keyframe generation starts.'
    : activeStage === 'KEYFRAME_REVIEW'
      ? 'Approve one keyframe per shot before motion generation starts.'
      : activeStage === 'PERFORMANCE_REVIEW'
        ? 'Review performance takes. Approve, re-record, or skip per shot. Approved drivers condition motion generation downstream.'
        : 'Review motion and postprocess variants. Assembly only uses the approved final take for each shot.'

  const assemblyReady = allShots.length > 0 && allShots.every(({ shot }) => Boolean(shot.approved_final_take_id))

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-acc">Guided Production Review</h2>
          <p className="mt-1 text-xs text-mut">{stageCopy}</p>
        </div>
        <button
          onClick={() => void onProceedToAssembly()}
          disabled={!assemblyReady}
          className="rounded-lg bg-ok px-6 py-2.5 text-sm font-semibold text-white shadow-glow-success disabled:opacity-40"
        >
          Assemble Approved Film
        </button>
      </div>

      {allShots.length > 0 ? (
        <div className="space-y-3">
          {allShots.map(({ shot, scene }) => (
            <ClipCard
              key={shot.id}
              shot={shot}
              scene={scene}
              projectId={project.id}
              activeStage={activeStage}
              shotState={shotStates.get(shot.id)}
              onApprovePlan={onApprovePlan}
              onRejectPlan={onRejectPlan}
              onGenerateKeyframe={onGenerateKeyframe}
              onApproveKeyframe={onApproveKeyframe}
              onApprovePerformance={onApprovePerformance}
              onGenerateMotion={onGenerateMotion}
              onApproveFinal={onApproveFinal}
              onCorrect={onCorrect}
              onDiagnose={onDiagnose}
              onRegenerate={onRegenerate}
              onRefreshProject={onRefreshProject}
              onIterate={onIterate}
            />
          ))}
        </div>
      ) : (
        <div className="py-20 text-center text-mut">
          <p className="text-lg">No shots available</p>
        </div>
      )}
    </div>
  )
}
