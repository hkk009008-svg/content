import { useEffect, useMemo, useState } from 'react'
import type { Project, ShotState, Scene, Shot, TakeRecord } from '../../types/project'
import TakeStrip from '../console/TakeStrip'
import AutoApproveBadge from '../console/AutoApproveBadge'
import RejectAutoApproveModal from '../console/RejectAutoApproveModal'
import IterationPanel from './IterationPanel'

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
  const color = pct >= 75 ? 'text-editorial-ready' : pct >= 55 ? 'text-editorial-warn' : 'text-editorial-curtain'
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
    ? meta.score >= meta.threshold
      ? 'text-editorial-ready'
      : 'text-editorial-warn'
    : null
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      <span className="rounded bg-editorial-ink-soft px-1.5 py-0.5 text-eyebrow text-editorial-ivory-mute">
        {label ? `${label} via ${meta.engine}` : `via ${meta.engine}`}
      </span>
      {scoreColor && meta.score != null && (
        <span className={`font-mono text-eyebrow ${scoreColor}`}>
          {meta.score.toFixed(3)}
        </span>
      )}
      {meta.fallback && (
        <span className="rounded bg-editorial-curtain/20 px-1.5 py-0.5 text-eyebrow text-editorial-curtain">
          ⚠ FALLBACK
        </span>
      )}
    </div>
  )
}

function TakeCard({
  take,
  active,
  approved,
  showIterateButton,
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
    <div className={`rounded border px-2 py-2 ${active ? 'border-editorial-brass bg-editorial-brass/10' : 'border-editorial-rule bg-editorial-ink'}`}>
      <button onClick={onSelect} className="w-full text-left">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-editorial-ivory font-medium">{take.kind}</span>
          {approved && <span className="text-eyebrow text-editorial-ready">Approved</span>}
        </div>
        <div className="mt-1 text-eyebrow text-editorial-ivory-mute font-mono break-all">{take.id}</div>
        <CascadeBadge meta={take.cascade_metadata} />
        <CascadeBadge meta={take.metadata?.lipsync_cascade} label="lipsync" />
      </button>
      {!approved && (
        <div className="mt-2 flex gap-2">
          <button
            onClick={onApprove}
            className="flex-1 rounded border border-editorial-ready/50 px-2 py-1 text-eyebrow text-editorial-ready hover:bg-editorial-ready/10"
          >
            Approve
          </button>
          {showIterateButton && onIterate && !iterating && (
            <button
              onClick={() => { setIterating(true) }}
              className="rounded border border-editorial-brass/50 px-2 py-1 text-eyebrow text-editorial-brass hover:bg-editorial-brass/10"
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
  const [rejectReason, setRejectReason] = useState(shot.plan_rejection_reason || '')
  const [rejectAutoApproveGate, setRejectAutoApproveGate] = useState<'plan' | 'image' | 'motion' | 'final' | null>(null)
  /** S18: Performance-card iteration toggle. Inline drawer below the
   *  side-by-side preview, mirroring TakeCard's iteration UX shape. */
  const [iteratingPerformance, setIteratingPerformance] = useState(false)

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
    await runAction('keyframe', () => onGenerateKeyframe(shot.id, positivePrompt, negativePrompt))
    setShowRegenForm(false)
  }

  const handleRegenerate = async () => {
    // Full restart: clear every downstream approval and regenerate the keyframe
    // with the (possibly edited) prompt. See ShotController.restart_shot.
    await runAction('regenerate', () => onRegenerate(shot.id, positivePrompt, negativePrompt))
    setShowRegenForm(false)
  }

  return (
    <div className="rounded-lg border border-editorial-rule bg-editorial-ink-soft">
      <div className="flex items-center justify-between gap-3 border-b border-editorial-rule px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-editorial-ivory">{scene.title}</span>
            <span className="rounded bg-editorial-ink px-2 py-0.5 text-eyebrow text-editorial-ivory-mute">{statusBadge}</span>
            {shot.plan_status === 'approved' && <span className="text-eyebrow text-editorial-ready">Plan approved</span>}
            {shot.approved_keyframe_take_id && <span className="text-eyebrow text-editorial-ready">Keyframe locked</span>}
            {shot.approved_final_take_id && <span className="text-eyebrow text-editorial-ready">Final locked</span>}
          </div>
          <div className="mt-1 text-xs text-editorial-ivory-mute">{shot.id}</div>
        </div>
        {loadingAction && <div className="text-xs text-editorial-brass">{loadingAction}...</div>}
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-[280px_1fr]">
        <div className="space-y-3">
          {videoUrl ? (
            <video
              src={`${API}/projects/${projectId}/file?path=${encodeURIComponent(videoUrl)}`}
              controls
              className="w-full rounded border border-editorial-rule bg-black"
            />
          ) : imageUrl ? (
            <img
              src={`${API}/projects/${projectId}/file?path=${encodeURIComponent(imageUrl)}`}
              className="w-full rounded border border-editorial-rule object-cover"
            />
          ) : (
            <div className="flex aspect-video items-center justify-center rounded border border-editorial-rule bg-editorial-ink text-sm text-editorial-ivory-mute">
              No take yet
            </div>
          )}

          <div className="rounded border border-editorial-rule bg-editorial-ink px-3 py-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-editorial-ivory-mute">Identity</span>
              {formatScore(shotState?.identity_score ?? latestDiagnostic?.scores?.identity)}
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-editorial-ivory-mute">Coherence</span>
              {formatScore(diagnosis?.scores?.coherence ?? latestDiagnostic?.scores?.coherence)}
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-editorial-ivory-mute">Motion</span>
              {formatScore(diagnosis?.scores?.motion ?? latestDiagnostic?.scores?.motion)}
            </div>
            {(selectedFinal?.cascade_metadata || selectedFinal?.metadata?.lipsync_cascade) && (
              <div className="mt-2 border-t border-editorial-rule pt-2">
                <CascadeBadge meta={selectedFinal.cascade_metadata} />
                <CascadeBadge meta={selectedFinal.metadata?.lipsync_cascade} label="lipsync" />
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded border border-editorial-rule bg-editorial-ink px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-editorial-ivory-mute">Plan</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => runAction('approve-plan', () => onApprovePlan(shot.id))}
                  className="rounded border border-editorial-ready/50 px-2 py-1 text-eyebrow-lg text-editorial-ready hover:bg-editorial-ready/10"
                >
                  Approve Plan
                </button>
                <button
                  onClick={() => runAction('reject-plan', () => onRejectPlan(shot.id, rejectReason))}
                  className="rounded border border-editorial-curtain/50 px-2 py-1 text-eyebrow-lg text-editorial-curtain hover:bg-editorial-curtain/10"
                >
                  Reject Plan
                </button>
              </div>
            </div>
            <p className="mt-2 text-sm text-editorial-ivory">{shot.prompt}</p>
            <div className="mt-2 flex flex-wrap gap-2 text-eyebrow-lg text-editorial-ivory-mute">
              <span className="rounded bg-editorial-ink-soft px-2 py-1">{shot.camera}</span>
              <span className="rounded bg-editorial-ink-soft px-2 py-1">{shot.target_api}</span>
              {shot.continuity_constraints && <span className="rounded bg-editorial-ink-soft px-2 py-1">{shot.continuity_constraints}</span>}
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
              className="mt-3 w-full rounded border border-editorial-rule bg-editorial-ink-soft px-2 py-1.5 text-xs text-editorial-ivory"
            />
          </section>

          <section className="rounded border border-editorial-rule bg-editorial-ink px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-editorial-ivory-mute">Keyframes</h3>
              <button
                onClick={handleGenerateKeyframeClick}
                disabled={shot.plan_status !== 'approved'}
                className="rounded border border-editorial-brass/50 px-2 py-1 text-eyebrow-lg text-editorial-brass hover:bg-editorial-brass/10 disabled:opacity-40"
              >
                Generate Keyframe
              </button>
            </div>
            {keyframeTakes.length > 0 ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {keyframeTakes.map((take) => (
                  <TakeCard
                    key={take.id}
                    take={take}
                    active={selectedKeyframe?.id === take.id}
                    approved={shot.approved_keyframe_take_id === take.id}
                    showIterateButton={activeStage === 'KEYFRAME_REVIEW' && Boolean(onIterate)}
                    onSelect={() => setSelectedKeyframeTakeId(take.id)}
                    onApprove={() => runAction(`approve-${take.id}`, () => onApproveKeyframe(shot.id, take.id))}
                    onIterate={onIterate ? (takeId, prose, verb, params) =>
                      onIterate(shot.id, takeId, prose, 'keyframe', verb, params)
                    : undefined}
                  />
                ))}
              </div>
            ) : (
              <div className="mt-3 text-xs text-editorial-ivory-mute">No keyframe takes yet.</div>
            )}
            {shot.image_auto_approved && (
              <AutoApproveBadge
                gate="image"
                audit={audit}
                onReject={() => setRejectAutoApproveGate('image')}
              />
            )}

            {showRegenForm ? (
              <div className="mt-3 space-y-2 rounded border border-editorial-brass/30 bg-editorial-ink-soft px-3 py-3">
                <textarea
                  value={positivePrompt}
                  onChange={(event) => setPositivePrompt(event.target.value)}
                  rows={3}
                  className="w-full rounded border border-editorial-rule bg-editorial-ink px-2 py-1.5 text-xs text-editorial-ivory"
                />
                <textarea
                  value={negativePrompt}
                  onChange={(event) => setNegativePrompt(event.target.value)}
                  rows={2}
                  className="w-full rounded border border-editorial-rule bg-editorial-ink px-2 py-1.5 text-xs text-editorial-ivory"
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleRegenerate}
                    className="rounded bg-editorial-brass px-3 py-1.5 text-xs text-white"
                  >
                    Create New Take
                  </button>
                  <button
                    onClick={() => setShowRegenForm(false)}
                    className="rounded border border-editorial-rule px-3 py-1.5 text-xs text-editorial-ivory-mute"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowRegenForm(true)}
                className="mt-3 text-xs text-editorial-brass hover:text-editorial-brass-deep"
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
              ? 'border-editorial-brass/60 bg-editorial-brass/5'
              : 'border-editorial-rule bg-editorial-ink'
          }`}>
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-editorial-ivory-mute">
                Performance Capture
                {performanceEngine && performanceEngine !== 'SKIP' && (
                  <span className="ml-2 rounded bg-editorial-brass/20 px-1.5 py-0.5 text-eyebrow-lg text-editorial-brass">
                    {performanceEngine}
                  </span>
                )}
                {performanceEngine === 'SKIP' && (
                  <span className="ml-2 rounded bg-editorial-ink-soft px-1.5 py-0.5 text-eyebrow-lg text-editorial-ivory-mute">
                    SKIP (wide / no characters)
                  </span>
                )}
              </h3>
              <div className="flex gap-2">
                <label className="rounded border border-editorial-brass/50 px-2 py-1 text-eyebrow-lg text-editorial-brass hover:bg-editorial-brass/10 cursor-pointer">
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
                    className="rounded border border-editorial-ready/50 px-2 py-1 text-eyebrow-lg text-editorial-ready hover:bg-editorial-ready/10 disabled:opacity-40"
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
                    className="rounded border border-editorial-curtain/50 px-2 py-1 text-eyebrow-lg text-editorial-curtain hover:bg-editorial-curtain/10"
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
                    className="rounded border border-editorial-brass/50 px-2 py-1 text-eyebrow-lg text-editorial-brass hover:bg-editorial-brass/10"
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
                  <div className="rounded bg-editorial-ink-soft px-2 py-1.5">
                    <div className="text-editorial-ivory-mute uppercase text-eyebrow-lg">Identity (ArcFace)</div>
                    <div className="mt-0.5 font-mono">
                      {typeof performanceIdentity === 'number'
                        ? performanceIdentity.toFixed(3)
                        : '—'}
                    </div>
                  </div>
                  <div className="rounded bg-editorial-ink-soft px-2 py-1.5">
                    <div className="text-editorial-ivory-mute uppercase text-eyebrow-lg">Motion fidelity</div>
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
                    className="ml-2 rounded bg-editorial-curtain/20 px-1.5 py-0.5 text-eyebrow-lg text-editorial-curtain"
                  >
                    below {resolvedShotType} floor
                  </span>
                )}
              </>
            )}

            {performanceEngine === 'SKIP' && !performanceVideoPath && (
              <p className="mt-3 text-xs text-editorial-ivory-mute italic">
                Skipped: this shot doesn't benefit from performance capture (no characters or framing too wide).
                Motion will use plain text-to-video.
              </p>
            )}
          </section>

          <section className="rounded border border-editorial-rule bg-editorial-ink px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-editorial-ivory-mute">Motion and Final Takes</h3>
              <button
                onClick={() => runAction('motion', () => onGenerateMotion(shot.id))}
                disabled={!shot.approved_keyframe_take_id}
                className="rounded border border-editorial-brass/50 px-2 py-1 text-eyebrow-lg text-editorial-brass hover:bg-editorial-brass/10 disabled:opacity-40"
              >
                Generate Motion
              </button>
            </div>
            {finalTakes.length > 0 ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {finalTakes.map((take) => (
                  <TakeCard
                    key={take.id}
                    take={take}
                    active={selectedFinal?.id === take.id}
                    approved={shot.approved_final_take_id === take.id}
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
              <div className="mt-3 text-xs text-editorial-ivory-mute">No motion or postprocess takes yet.</div>
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
                  className="rounded border border-editorial-rule px-2 py-1 text-eyebrow-lg text-editorial-ivory hover:bg-editorial-ink-rise disabled:opacity-40"
                >
                  {tool.label}
                </button>
              ))}
              <select
                onChange={(event) => {
                  if (event.target.value) handleCorrect('color_grade', { preset: event.target.value })
                  event.target.value = ''
                }}
                disabled={!selectedFinal?.id}
                className="rounded border border-editorial-rule bg-editorial-ink-soft px-2 py-1 text-eyebrow-lg text-editorial-ivory disabled:opacity-40"
              >
                <option value="">Color Grade</option>
                {COLOR_PRESETS.map((preset) => (
                  <option key={preset.id} value={preset.id}>{preset.label}</option>
                ))}
              </select>
              <select
                onChange={(event) => {
                  if (event.target.value) handleCorrect('speed', { factor: parseFloat(event.target.value) })
                  event.target.value = ''
                }}
                disabled={!selectedFinal?.id}
                className="rounded border border-editorial-rule bg-editorial-ink-soft px-2 py-1 text-eyebrow-lg text-editorial-ivory disabled:opacity-40"
              >
                <option value="">Speed</option>
                {SPEED_OPTIONS.map((option) => (
                  <option key={option.factor} value={option.factor}>{option.label}</option>
                ))}
              </select>
              <button
                onClick={handleDiagnose}
                disabled={!activeTakeId || diagnosing}
                className="rounded border border-editorial-rule px-2 py-1 text-eyebrow-lg text-editorial-brass hover:bg-editorial-brass/10 disabled:opacity-40"
              >
                {diagnosing ? 'Diagnosing...' : 'Diagnose'}
              </button>
              <button
                onClick={handleDeepDiagnose}
                disabled={!activeTakeId || deepDiagnosing || diagnosis?.deep_available === false}
                className="rounded border border-editorial-warn/50 px-2 py-1 text-eyebrow-lg text-editorial-warn hover:bg-editorial-warn/10 disabled:opacity-40"
                title={diagnosis?.deep_available === false ? 'Deep diagnosis not available for this take' : 'Run LLM-powered deep diagnosis'}
              >
                {deepDiagnosing ? 'Deep diagnosing...' : 'Deep diagnose'}
              </button>
            </div>

            {(diagnosis?.recommendations?.length || latestDiagnostic?.recommendations?.length) ? (
              <div className="mt-3 rounded border border-editorial-warn/20 bg-editorial-warn/5 px-3 py-2 text-xs">
                {(diagnosis?.recommendations || latestDiagnostic?.recommendations || []).map((recommendation: { tool: string; reason: string }, index: number) => (
                  <div key={`${recommendation.tool}-${index}`} className="mt-1 flex items-center gap-2">
                    <span className="text-editorial-warn">{recommendation.tool}</span>
                    <span className="text-editorial-ivory-mute">{recommendation.reason}</span>
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
                <div className="mt-3 rounded border border-editorial-warn/30 bg-editorial-warn/5 px-3 py-3 text-xs space-y-2">
                  <div className="font-semibold uppercase tracking-wide text-editorial-warn text-eyebrow-lg">
                    Identity Remediation Advisory
                  </div>
                  {advisory.failure_reason && (
                    <div className="text-editorial-ivory-mute">{advisory.failure_reason}</div>
                  )}
                  {advisory.suggested_negative_prompt && (
                    <div className="space-y-1">
                      <div className="text-editorial-ivory-mute uppercase text-eyebrow tracking-wide">Suggested negative prompt</div>
                      <code className="block font-mono bg-editorial-ink px-2 py-1.5 rounded text-editorial-ivory break-all whitespace-pre-wrap">
                        {advisory.suggested_negative_prompt}
                      </code>
                      <button
                        onClick={() => setNegativePrompt(advisory.suggested_negative_prompt)}
                        className="text-editorial-brass hover:text-editorial-brass-deep underline underline-offset-2"
                      >
                        Apply negative prompt
                      </button>
                    </div>
                  )}
                  {advisory.suggested_pulid_adjustment && (
                    <div className="text-editorial-ivory-mute">
                      <span className="text-editorial-warn">PuLID adjustment:</span>{' '}
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
              <div className="mt-3 rounded border border-editorial-warn/30 bg-editorial-warn/5 px-3 py-3 text-xs space-y-2">
                <div className="font-semibold uppercase tracking-wide text-editorial-warn text-eyebrow-lg">
                  Deep Diagnosis
                  <span className="ml-2 rounded bg-editorial-ink px-1.5 py-0.5 text-editorial-ivory-mute font-normal normal-case tracking-normal">
                    {diagnosis.advisory_deep.source ?? 'llm'}
                  </span>
                </div>
                {diagnosis.advisory_deep.visual_findings && (
                  <div className="space-y-1">
                    <div className="text-editorial-ivory-mute uppercase text-eyebrow tracking-wide">Visual findings</div>
                    <div className="text-editorial-ivory-mute">{diagnosis.advisory_deep.visual_findings}</div>
                  </div>
                )}
                {diagnosis.advisory_deep.diagnosis && (
                  <div className="text-editorial-ivory-mute">{diagnosis.advisory_deep.diagnosis}</div>
                )}
                {diagnosis.advisory_deep.prompt_mutation && (
                  <div className="space-y-1">
                    <div className="text-editorial-ivory-mute uppercase text-eyebrow tracking-wide">Prompt mutation</div>
                    <code className="block font-mono bg-editorial-ink px-2 py-1.5 rounded text-editorial-ivory break-all whitespace-pre-wrap">
                      {diagnosis.advisory_deep.prompt_mutation}
                    </code>
                  </div>
                )}
                {diagnosis.advisory_deep.mutation_focus && (
                  <div className="text-editorial-ivory-mute">
                    <span className="text-editorial-warn">Focus:</span>{' '}
                    {diagnosis.advisory_deep.mutation_focus}
                  </div>
                )}
                {diagnosis.advisory_deep.decision && (
                  <div className="text-editorial-ivory-mute">
                    <span className="text-editorial-warn">Decision:</span>{' '}
                    {diagnosis.advisory_deep.decision}
                  </div>
                )}
              </div>
            )}

            {/* Deep error note */}
            {diagnosis?.deep_error && (
              <div className="mt-2 text-eyebrow-lg text-editorial-ivory-faint italic">
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
          <h2 className="text-lg font-semibold text-editorial-brass">Guided Production Review</h2>
          <p className="mt-1 text-xs text-editorial-ivory-mute">{stageCopy}</p>
        </div>
        <button
          onClick={() => void onProceedToAssembly()}
          disabled={!assemblyReady}
          className="rounded-lg bg-editorial-ready px-6 py-2.5 text-sm font-semibold text-white shadow-glow-success disabled:opacity-40"
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
        <div className="py-20 text-center text-editorial-ivory-mute">
          <p className="text-lg">No shots available</p>
        </div>
      )}
    </div>
  )
}
