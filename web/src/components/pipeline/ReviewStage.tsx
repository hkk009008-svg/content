import { useEffect, useMemo, useState } from 'react'
import type { Project, ShotState, Scene, Shot, TakeRecord } from '../../types/project'

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
  onGenerateMotion: (shotId: string) => Promise<any>
  onApproveFinal: (shotId: string, takeId: string) => Promise<any>
  onCorrect: (shotId: string, action: string, params?: Record<string, any>, takeId?: string) => Promise<any>
  onDiagnose: (shotId: string, takeId?: string) => Promise<any>
  onRegenerate: (shotId: string, positive?: string, negative?: string) => Promise<any>
  onProceedToAssembly: () => Promise<any>
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
  const color = pct >= 75 ? 'text-cinema-success' : pct >= 55 ? 'text-cinema-warning' : 'text-cinema-danger'
  return <span className={`text-xs font-mono ${color}`}>{pct}%</span>
}

function renderTakeButton({
  take,
  active,
  approved,
  onSelect,
  onApprove,
}: {
  take: TakeRecord
  active: boolean
  approved: boolean
  onSelect: () => void
  onApprove: () => void
}) {
  return (
    <div key={take.id} className={`rounded border px-2 py-2 ${active ? 'border-cinema-accent bg-cinema-accent/10' : 'border-cinema-border bg-cinema-bg'}`}>
      <button onClick={onSelect} className="w-full text-left">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-cinema-text font-medium">{take.kind}</span>
          {approved && <span className="text-[10px] text-cinema-success">Approved</span>}
        </div>
        <div className="mt-1 text-[10px] text-cinema-muted font-mono break-all">{take.id}</div>
      </button>
      {!approved && (
        <button
          onClick={onApprove}
          className="mt-2 w-full rounded border border-cinema-success/50 px-2 py-1 text-[10px] text-cinema-success hover:bg-cinema-success/10"
        >
          Approve
        </button>
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
  onGenerateMotion,
  onApproveFinal,
  onCorrect,
  onDiagnose,
  onRegenerate,
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
  onGenerateMotion: Props['onGenerateMotion']
  onApproveFinal: Props['onApproveFinal']
  onCorrect: Props['onCorrect']
  onDiagnose: Props['onDiagnose']
  onRegenerate: Props['onRegenerate']
}) {
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null)
  const [diagnosing, setDiagnosing] = useState(false)
  const [loadingAction, setLoadingAction] = useState<string | null>(null)
  const [positivePrompt, setPositivePrompt] = useState(shot.prompt || '')
  const [negativePrompt, setNegativePrompt] = useState(shot.negative_constraints || '')
  const [showRegenForm, setShowRegenForm] = useState(false)
  const [rejectReason, setRejectReason] = useState(shot.plan_rejection_reason || '')
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
      : 'Final Review'

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

  const handleCorrect = async (action: string, params: Record<string, any> = {}) => {
    if (!selectedFinal?.id) return
    await runAction(action, () => onCorrect(shot.id, action, params, selectedFinal.id))
  }

  const handleGenerateKeyframeClick = async () => {
    await runAction('keyframe', () => onGenerateKeyframe(shot.id, positivePrompt, negativePrompt))
    setShowRegenForm(false)
  }

  const handleRegenerate = async () => {
    await runAction('regenerate', () => onGenerateKeyframe(shot.id, positivePrompt, negativePrompt))
    setShowRegenForm(false)
  }

  return (
    <div className="rounded-lg border border-cinema-border bg-cinema-panel">
      <div className="flex items-center justify-between gap-3 border-b border-cinema-border px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-cinema-text">{scene.title}</span>
            <span className="rounded bg-cinema-bg px-2 py-0.5 text-[10px] text-cinema-muted">{statusBadge}</span>
            {shot.plan_status === 'approved' && <span className="text-[10px] text-cinema-success">Plan approved</span>}
            {shot.approved_keyframe_take_id && <span className="text-[10px] text-cinema-success">Keyframe locked</span>}
            {shot.approved_final_take_id && <span className="text-[10px] text-cinema-success">Final locked</span>}
          </div>
          <div className="mt-1 text-xs text-cinema-muted">{shot.id}</div>
        </div>
        {loadingAction && <div className="text-xs text-cinema-accent">{loadingAction}...</div>}
      </div>

      <div className="grid gap-4 p-4 lg:grid-cols-[280px_1fr]">
        <div className="space-y-3">
          {videoUrl ? (
            <video
              src={`${API}/projects/${projectId}/file?path=${encodeURIComponent(videoUrl)}`}
              controls
              className="w-full rounded border border-cinema-border bg-black"
            />
          ) : imageUrl ? (
            <img
              src={`${API}/projects/${projectId}/file?path=${encodeURIComponent(imageUrl)}`}
              className="w-full rounded border border-cinema-border object-cover"
            />
          ) : (
            <div className="flex aspect-video items-center justify-center rounded border border-cinema-border bg-cinema-bg text-sm text-cinema-muted">
              No take yet
            </div>
          )}

          <div className="rounded border border-cinema-border bg-cinema-bg px-3 py-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-cinema-muted">Identity</span>
              {formatScore(shotState?.identity_score ?? latestDiagnostic?.scores?.identity)}
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-cinema-muted">Coherence</span>
              {formatScore(diagnosis?.scores?.coherence ?? latestDiagnostic?.scores?.coherence)}
            </div>
            <div className="mt-1 flex items-center justify-between">
              <span className="text-cinema-muted">Motion</span>
              {formatScore(diagnosis?.scores?.motion ?? latestDiagnostic?.scores?.motion)}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <section className="rounded border border-cinema-border bg-cinema-bg px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-cinema-muted">Plan</h3>
              <div className="flex gap-2">
                <button
                  onClick={() => runAction('approve-plan', () => onApprovePlan(shot.id))}
                  className="rounded border border-cinema-success/50 px-2 py-1 text-[11px] text-cinema-success hover:bg-cinema-success/10"
                >
                  Approve Plan
                </button>
                <button
                  onClick={() => runAction('reject-plan', () => onRejectPlan(shot.id, rejectReason))}
                  className="rounded border border-cinema-danger/50 px-2 py-1 text-[11px] text-cinema-danger hover:bg-cinema-danger/10"
                >
                  Reject Plan
                </button>
              </div>
            </div>
            <p className="mt-2 text-sm text-cinema-text">{shot.prompt}</p>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-cinema-muted">
              <span className="rounded bg-cinema-panel px-2 py-1">{shot.camera}</span>
              <span className="rounded bg-cinema-panel px-2 py-1">{shot.target_api}</span>
              {shot.continuity_constraints && <span className="rounded bg-cinema-panel px-2 py-1">{shot.continuity_constraints}</span>}
            </div>
            <input
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
              placeholder="Reason if rejecting this shot plan"
              className="mt-3 w-full rounded border border-cinema-border bg-cinema-panel px-2 py-1.5 text-xs text-cinema-text"
            />
          </section>

          <section className="rounded border border-cinema-border bg-cinema-bg px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-cinema-muted">Keyframes</h3>
              <button
                onClick={handleGenerateKeyframeClick}
                disabled={shot.plan_status !== 'approved'}
                className="rounded border border-cinema-accent/50 px-2 py-1 text-[11px] text-cinema-accent hover:bg-cinema-accent/10 disabled:opacity-40"
              >
                Generate Keyframe
              </button>
            </div>
            {keyframeTakes.length > 0 ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {keyframeTakes.map((take, index) => renderTakeButton({
                  take,
                  active: selectedKeyframe?.id === take.id,
                  approved: shot.approved_keyframe_take_id === take.id,
                  onSelect: () => setSelectedKeyframeTakeId(take.id),
                  onApprove: () => runAction(`approve-${take.id}`, () => onApproveKeyframe(shot.id, take.id)),
                }))}
              </div>
            ) : (
              <div className="mt-3 text-xs text-cinema-muted">No keyframe takes yet.</div>
            )}

            {showRegenForm ? (
              <div className="mt-3 space-y-2 rounded border border-cinema-accent/30 bg-cinema-panel px-3 py-3">
                <textarea
                  value={positivePrompt}
                  onChange={(event) => setPositivePrompt(event.target.value)}
                  rows={3}
                  className="w-full rounded border border-cinema-border bg-cinema-bg px-2 py-1.5 text-xs text-cinema-text"
                />
                <textarea
                  value={negativePrompt}
                  onChange={(event) => setNegativePrompt(event.target.value)}
                  rows={2}
                  className="w-full rounded border border-cinema-border bg-cinema-bg px-2 py-1.5 text-xs text-cinema-text"
                />
                <div className="flex gap-2">
                  <button
                    onClick={handleRegenerate}
                    className="rounded bg-cinema-accent px-3 py-1.5 text-xs text-white"
                  >
                    Create New Take
                  </button>
                  <button
                    onClick={() => setShowRegenForm(false)}
                    className="rounded border border-cinema-border px-3 py-1.5 text-xs text-cinema-muted"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setShowRegenForm(true)}
                className="mt-3 text-xs text-cinema-gold hover:text-cinema-gold-dim"
              >
                Adjust prompts and create another keyframe take
              </button>
            )}
          </section>

          <section className="rounded border border-cinema-border bg-cinema-bg px-3 py-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-cinema-muted">Motion and Final Takes</h3>
              <button
                onClick={() => runAction('motion', () => onGenerateMotion(shot.id))}
                disabled={!shot.approved_keyframe_take_id}
                className="rounded border border-cinema-accent/50 px-2 py-1 text-[11px] text-cinema-accent hover:bg-cinema-accent/10 disabled:opacity-40"
              >
                Generate Motion
              </button>
            </div>
            {finalTakes.length > 0 ? (
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {finalTakes.map((take) => renderTakeButton({
                  take,
                  active: selectedFinal?.id === take.id,
                  approved: shot.approved_final_take_id === take.id,
                  onSelect: () => setSelectedFinalTakeId(take.id),
                  onApprove: () => runAction(`approve-${take.id}`, () => onApproveFinal(shot.id, take.id)),
                }))}
              </div>
            ) : (
              <div className="mt-3 text-xs text-cinema-muted">No motion or postprocess takes yet.</div>
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
                  className="rounded border border-cinema-border px-2 py-1 text-[11px] text-cinema-text hover:bg-cinema-panel-hover disabled:opacity-40"
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
                className="rounded border border-cinema-border bg-cinema-panel px-2 py-1 text-[11px] text-cinema-text disabled:opacity-40"
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
                className="rounded border border-cinema-border bg-cinema-panel px-2 py-1 text-[11px] text-cinema-text disabled:opacity-40"
              >
                <option value="">Speed</option>
                {SPEED_OPTIONS.map((option) => (
                  <option key={option.factor} value={option.factor}>{option.label}</option>
                ))}
              </select>
              <button
                onClick={handleDiagnose}
                disabled={!activeTakeId || diagnosing}
                className="rounded border border-cinema-border px-2 py-1 text-[11px] text-cinema-accent hover:bg-cinema-accent/10 disabled:opacity-40"
              >
                {diagnosing ? 'Diagnosing...' : 'Diagnose'}
              </button>
            </div>

            {(diagnosis?.recommendations?.length || latestDiagnostic?.recommendations?.length) ? (
              <div className="mt-3 rounded border border-cinema-warning/20 bg-cinema-warning/5 px-3 py-2 text-xs">
                {(diagnosis?.recommendations || latestDiagnostic?.recommendations || []).map((recommendation, index) => (
                  <div key={`${recommendation.tool}-${index}`} className="mt-1 flex items-center gap-2">
                    <span className="text-cinema-warning">{recommendation.tool}</span>
                    <span className="text-cinema-muted">{recommendation.reason}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </section>
        </div>
      </div>
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
  onGenerateMotion,
  onApproveFinal,
  onCorrect,
  onDiagnose,
  onRegenerate,
  onProceedToAssembly,
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
      : 'Review motion and postprocess variants. Assembly only uses the approved final take for each shot.'

  const assemblyReady = allShots.length > 0 && allShots.every(({ shot }) => Boolean(shot.approved_final_take_id))

  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-cinema-gold">Guided Production Review</h2>
          <p className="mt-1 text-xs text-cinema-muted">{stageCopy}</p>
        </div>
        <button
          onClick={() => void onProceedToAssembly()}
          disabled={!assemblyReady}
          className="rounded-lg bg-cinema-success px-6 py-2.5 text-sm font-semibold text-white shadow-glow-success disabled:opacity-40"
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
              onGenerateMotion={onGenerateMotion}
              onApproveFinal={onApproveFinal}
              onCorrect={onCorrect}
              onDiagnose={onDiagnose}
              onRegenerate={onRegenerate}
            />
          ))}
        </div>
      ) : (
        <div className="py-20 text-center text-cinema-muted">
          <p className="text-lg">No shots available</p>
        </div>
      )}
    </div>
  )
}
