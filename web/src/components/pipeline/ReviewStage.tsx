import { useState, useEffect } from 'react'
import type { Project, ShotState, Scene, Shot } from '../../types/project'

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
  shotStates: Map<string, Partial<ShotState>>
  onCorrect: (shotId: string, action: string, params?: Record<string, any>) => Promise<any>
  onDiagnose: (shotId: string) => Promise<any>
  onRegenerate: (shotId: string, positive?: string, negative?: string) => Promise<any>
  onProceedToAssembly: () => void
}

function ClipCard({
  shot, scene, projectId, shotState,
  onCorrect, onDiagnose, onRegenerate,
}: {
  shot: Shot; scene: Scene; projectId: string
  shotState: Partial<ShotState> | undefined
  onCorrect: Props['onCorrect']
  onDiagnose: Props['onDiagnose']
  onRegenerate: Props['onRegenerate']
}) {
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null)
  const [diagnosing, setDiagnosing] = useState(false)
  const [correcting, setCorrecting] = useState<string | null>(null)
  const [positivePrompt, setPositivePrompt] = useState(shot.prompt || '')
  const [negativePrompt, setNegativePrompt] = useState('blur, distort, deformed face, identity change, face morph')
  const [showRegenForm, setShowRegenForm] = useState(false)
  const [approved, setApproved] = useState(false)

  const imageUrl = shotState?.generated_image || shot.generated_image
  const videoUrl = shotState?.generated_video || shot.generated_video
  const identityScore = shotState?.identity_score
  const shotType = shotState?.shot_type || 'medium'

  const handleDiagnose = async () => {
    setDiagnosing(true)
    const result = await onDiagnose(shot.id)
    setDiagnosis(result)
    setDiagnosing(false)
  }

  const handleCorrect = async (action: string, params: Record<string, any> = {}) => {
    setCorrecting(action)
    await onCorrect(shot.id, action, params)
    setCorrecting(null)
    handleDiagnose() // Re-diagnose after correction
  }

  const handleRegenerate = async () => {
    setCorrecting('regenerate')
    await onRegenerate(shot.id, positivePrompt, negativePrompt)
    setCorrecting(null)
    setShowRegenForm(false)
  }

  // Auto-diagnose on mount
  useEffect(() => { handleDiagnose() }, [])

  const scoreBadge = (label: string, value: number | undefined) => {
    if (value == null) return null
    const pct = Math.round(value * 100)
    const color = pct >= 75 ? 'text-cinema-success' : pct >= 55 ? 'text-cinema-warning' : 'text-cinema-danger'
    return <span className={`text-xs font-mono ${color}`}>{label}: {pct}%</span>
  }

  return (
    <div className={`border rounded-lg overflow-hidden ${approved ? 'border-cinema-success/50 bg-cinema-success/5' : 'border-cinema-border bg-cinema-panel'}`}>
      {/* Header */}
      <div className="px-4 py-2 bg-cinema-bg/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs text-cinema-text font-medium">{scene.title}</span>
          <span className="text-[10px] text-cinema-muted font-mono">Shot {(shot as any).shot_index ?? '?'}</span>
          <span className="text-[10px] bg-cinema-panel px-1.5 py-0.5 rounded text-cinema-muted">{shotType}</span>
          <span className="text-[10px] bg-cinema-panel px-1.5 py-0.5 rounded text-cinema-muted">{shot.target_api}</span>
        </div>
        <div className="flex items-center gap-2">
          {approved && <span className="text-[10px] bg-cinema-success/20 text-cinema-success px-2 py-0.5 rounded">Approved</span>}
          {correcting && <span className="text-[10px] bg-cinema-accent/20 text-cinema-accent px-2 py-0.5 rounded animate-pulse">{correcting}...</span>}
        </div>
      </div>

      <div className="p-4 grid grid-cols-[240px_1fr] gap-4">
        {/* Left: Video/Image preview */}
        <div>
          {videoUrl ? (
            <video
              src={`${API}/projects/${projectId}/file?path=${encodeURIComponent(videoUrl)}`}
              controls className="w-full rounded border border-cinema-border aspect-video bg-black"
            />
          ) : imageUrl ? (
            <img
              src={`${API}/projects/${projectId}/file?path=${encodeURIComponent(imageUrl)}`}
              className="w-full rounded border border-cinema-border aspect-video object-cover"
            />
          ) : (
            <div className="w-full aspect-video bg-cinema-bg rounded border border-cinema-border flex items-center justify-center">
              <span className="text-cinema-muted text-sm">No clip</span>
            </div>
          )}
        </div>

        {/* Right: Scores + Tools */}
        <div className="space-y-3">
          {/* Quality scores */}
          <div className="flex items-center gap-4">
            {scoreBadge('ID', identityScore ?? undefined)}
            {scoreBadge('COH', diagnosis?.scores?.coherence)}
            {scoreBadge('MOT', diagnosis?.scores?.motion)}
            <button
              onClick={handleDiagnose} disabled={diagnosing}
              className="text-[10px] text-cinema-accent hover:text-cinema-accent2 ml-auto"
            >
              {diagnosing ? 'Analyzing...' : 'Re-diagnose'}
            </button>
          </div>

          {/* Recommendations */}
          {diagnosis?.recommendations && diagnosis.recommendations.length > 0 && (
            <div className="bg-cinema-warning/5 border border-cinema-warning/20 rounded px-3 py-2">
              {diagnosis.recommendations.map((rec, i) => (
                <div key={i} className="flex items-center gap-2 text-xs">
                  <span className="text-cinema-warning">Suggested:</span>
                  <button
                    onClick={() => handleCorrect(rec.tool)}
                    disabled={correcting !== null}
                    className="text-cinema-accent hover:text-cinema-accent2 underline"
                  >
                    {rec.tool.replace('_', ' ')}
                  </button>
                  <span className="text-cinema-muted">— {rec.reason}</span>
                </div>
              ))}
            </div>
          )}
          {diagnosis?.recommendations?.length === 0 && (
            <div className="text-xs text-cinema-success">No issues detected</div>
          )}

          {/* Correction toolbar */}
          <div className="flex flex-wrap gap-1.5">
            {[
              { action: 'face_swap', label: 'Face Swap', icon: '🎭' },
              { action: 'lip_sync', label: 'Lip Sync', icon: '🗣' },
              { action: 'rife', label: 'RIFE Smooth', icon: '⚡' },
              { action: 'upscale', label: 'Upscale', icon: '🔍' },
            ].map(tool => (
              <button key={tool.action}
                onClick={() => handleCorrect(tool.action)}
                disabled={correcting !== null}
                className="text-[10px] bg-cinema-bg hover:bg-cinema-panel-hover border border-cinema-border rounded px-2 py-1.5 text-cinema-text transition-colors disabled:opacity-40"
              >
                {tool.icon} {tool.label}
              </button>
            ))}

            {/* Color grade dropdown */}
            <select
              onChange={e => { if (e.target.value) handleCorrect('color_grade', { preset: e.target.value }); e.target.value = '' }}
              disabled={correcting !== null}
              className="text-[10px] bg-cinema-bg border border-cinema-border rounded px-2 py-1.5 text-cinema-text"
            >
              <option value="">🎨 Color Grade</option>
              {COLOR_PRESETS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>

            {/* Speed dropdown */}
            <select
              onChange={e => { if (e.target.value) handleCorrect('speed', { factor: parseFloat(e.target.value) }); e.target.value = '' }}
              disabled={correcting !== null}
              className="text-[10px] bg-cinema-bg border border-cinema-border rounded px-2 py-1.5 text-cinema-text"
            >
              <option value="">⏱ Speed</option>
              {SPEED_OPTIONS.map(s => <option key={s.factor} value={s.factor}>{s.label}</option>)}
            </select>
          </div>

          {/* Regenerate section */}
          {showRegenForm ? (
            <div className="space-y-2 bg-cinema-bg rounded p-3 border border-cinema-accent/30">
              <div>
                <label className="text-[10px] text-cinema-success block mb-1">Positive prompt (what to generate)</label>
                <textarea value={positivePrompt} onChange={e => setPositivePrompt(e.target.value)} rows={3}
                  className="w-full bg-cinema-panel border border-cinema-border rounded px-2 py-1.5 text-xs text-cinema-text focus:outline-none focus:border-cinema-accent resize-none font-mono" />
              </div>
              <div>
                <label className="text-[10px] text-cinema-danger block mb-1">Negative prompt (what to avoid)</label>
                <textarea value={negativePrompt} onChange={e => setNegativePrompt(e.target.value)} rows={2}
                  className="w-full bg-cinema-panel border border-cinema-border rounded px-2 py-1.5 text-xs text-cinema-text focus:outline-none focus:border-cinema-danger/50 resize-none font-mono" />
              </div>
              <div className="flex gap-2">
                <button onClick={handleRegenerate} disabled={correcting !== null}
                  className="flex-1 bg-cinema-accent hover:bg-cinema-accent2 disabled:opacity-40 py-1.5 rounded text-white text-xs font-medium">
                  {correcting === 'regenerate' ? 'Regenerating...' : 'Regenerate Image + Video'}
                </button>
                <button onClick={() => setShowRegenForm(false)} className="px-3 py-1.5 text-cinema-muted text-xs hover:text-cinema-text">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button onClick={() => setShowRegenForm(true)}
              className="text-xs text-cinema-gold hover:text-cinema-gold-dim">
              ↻ Regenerate with adjusted prompts...
            </button>
          )}

          {/* Approve */}
          <button
            onClick={() => setApproved(!approved)}
            className={`w-full py-2 rounded text-sm font-medium transition-colors ${
              approved
                ? 'bg-cinema-success/20 text-cinema-success border border-cinema-success/30 hover:bg-transparent'
                : 'bg-cinema-bg border border-cinema-border text-cinema-text hover:border-cinema-success hover:text-cinema-success'
            }`}
          >
            {approved ? '✓ Approved' : 'Approve clip'}
          </button>
        </div>
      </div>
    </div>
  )
}


export default function ReviewStage({ project, shotStates, onCorrect, onDiagnose, onRegenerate, onProceedToAssembly }: Props) {
  // Collect all shots across scenes
  const allShots: { shot: Shot; scene: Scene }[] = []
  for (const scene of project.scenes) {
    for (const shot of (scene.shots || [])) {
      allShots.push({ shot, scene })
    }
  }

  return (
    <div className="p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-cinema-gold">Director's Cut</h2>
          <p className="text-xs text-cinema-muted mt-1">
            Review each clip. Apply corrections, regenerate with adjusted prompts, or approve to proceed.
          </p>
        </div>
        <button
          onClick={onProceedToAssembly}
          className="bg-cinema-success hover:bg-cinema-success-dim px-6 py-2.5 rounded-lg text-white font-semibold text-sm shadow-glow-success"
        >
          Proceed to Assembly →
        </button>
      </div>

      {/* Clip grid */}
      <div className="space-y-3">
        {allShots.map(({ shot, scene }) => (
          <ClipCard
            key={shot.id}
            shot={shot}
            scene={scene}
            projectId={project.id}
            shotState={shotStates.get(shot.id)}
            onCorrect={onCorrect}
            onDiagnose={onDiagnose}
            onRegenerate={onRegenerate}
          />
        ))}
      </div>

      {allShots.length === 0 && (
        <div className="text-center py-20 text-cinema-muted">
          <p className="text-lg">No clips to review</p>
          <p className="text-sm mt-2">Clips will appear here once generation completes</p>
        </div>
      )}

      {/* Bottom CTA */}
      {allShots.length > 0 && (
        <div className="flex justify-center pt-4">
          <button
            onClick={onProceedToAssembly}
            className="bg-cinema-success hover:bg-cinema-success-dim px-8 py-3 rounded-lg text-white font-semibold text-base shadow-glow-success"
          >
            All clips reviewed — Proceed to Final Assembly →
          </button>
        </div>
      )}
    </div>
  )
}
