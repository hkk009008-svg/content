import { useState, useEffect } from 'react'
import type { Shot, ShotState, ApiInfo } from '../../types/project'
import ShotApprovalControls from './ShotApprovalControls'
import PromptEditor from './PromptEditor'

// Module-level cache for API registry (shared across all ShotRow instances)
let _apiRegistryCache: Record<string, ApiInfo> | null = null

interface Props {
  shot: Shot
  shotState: Partial<ShotState> | undefined
  shotIndex: number
  sceneId: string
  projectId: string
  onRegenerate?: (shotId: string) => void
}

function getScoreBadge(score: number | null | undefined, label?: string) {
  if (score == null) return null
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? 'bg-cinema-success' : pct >= 60 ? 'bg-yellow-500' : 'bg-cinema-danger'
  return (
    <span className={`${color} text-white text-[10px] font-bold px-1.5 py-0.5 rounded`}>
      {label ? `${label} ` : ''}{pct}%
    </span>
  )
}

function getStatusBadge(status: string | undefined) {
  const map: Record<string, { color: string; label: string }> = {
    pending: { color: 'bg-cinema-muted/30', label: 'Pending' },
    generating_image: { color: 'bg-cinema-accent animate-pulse', label: 'Generating...' },
    image_review: { color: 'bg-yellow-500', label: 'Review' },
    generating_video: { color: 'bg-purple-500 animate-pulse', label: 'Video...' },
    post_processing: { color: 'bg-blue-500 animate-pulse', label: 'Processing...' },
    complete: { color: 'bg-cinema-success', label: 'Done' },
    failed: { color: 'bg-cinema-danger', label: 'Failed' },
  }
  const s = map[status || 'pending'] || map.pending
  return (
    <span className={`${s.color} text-white text-[10px] px-1.5 py-0.5 rounded`}>
      {s.label}
    </span>
  )
}

export default function ShotRow({ shot, shotState, shotIndex, sceneId, projectId, onRegenerate }: Props) {
  const [editingPrompt, setEditingPrompt] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [apiRegistry, setApiRegistry] = useState<Record<string, ApiInfo> | null>(_apiRegistryCache)

  // Load API registry once (module-level cache shared across instances)
  useEffect(() => {
    if (_apiRegistryCache) { setApiRegistry(_apiRegistryCache); return }
    fetch('/api/config').then(r => r.json()).then(cfg => {
      if (cfg.api_registry) {
        _apiRegistryCache = cfg.api_registry
        setApiRegistry(cfg.api_registry)
      }
    }).catch(() => {})
  }, [])

  const updateShotApi = async (newApi: string) => {
    await fetch(`/api/projects/${projectId}/shots/${shot.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_api: newApi }),
    })
    shot.target_api = newApi  // optimistic update
  }
  const status = shotState?.status || 'pending'
  const imageUrl = shotState?.generated_image || shot.generated_image
  const identityScore = shotState?.identity_score
  const coherenceScore = shotState?.coherence_score
  const motionScore = shotState?.motion_score
  const failureReason = shotState?.failure_reason
  const shotType = shotState?.shot_type
  const isReviewable = status === 'image_review' || (imageUrl && status !== 'generating_image')
  const isFailed = status === 'failed'

  // Parse structured sections from prompt
  const prompt = shot.prompt || ''
  const sections: Record<string, string> = {}
  for (const tag of ['SHOT', 'SCENE', 'ACTION', 'OUTFIT', 'QUALITY']) {
    const match = prompt.match(new RegExp(`\\[${tag}\\]\\s*(.+?)(?=\\[(?:SHOT|SCENE|ACTION|OUTFIT|QUALITY)\\]|$)`, 's'))
    if (match) sections[tag] = match[1].trim()
  }

  const sectionColors: Record<string, string> = {
    SHOT: 'text-cyan-400',
    SCENE: 'text-indigo-400',
    ACTION: 'text-amber-400',
    OUTFIT: 'text-pink-400',
    QUALITY: 'text-gray-500',
  }

  const handleRegenerate = async () => {
    if (!onRegenerate) return
    setRegenerating(true)
    await onRegenerate(shot.id)
    setRegenerating(false)
  }

  return (
    <div className={`flex items-start gap-3 px-4 py-3 border-b border-cinema-border/50 hover:bg-cinema-panel/50
      ${status === 'generating_image' || status === 'generating_video' ? 'bg-cinema-accent/5' : ''}
      ${isFailed ? 'bg-cinema-danger/5' : ''}
    `}>
      {/* Shot number + status */}
      <div className="flex flex-col items-center gap-1 min-w-[40px]">
        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
          ${status === 'complete' ? 'bg-cinema-success/20 text-cinema-success' :
            isFailed ? 'bg-cinema-danger/20 text-cinema-danger' :
            'bg-cinema-panel text-cinema-muted'}
        `}>
          {shotIndex + 1}
        </div>
        {getStatusBadge(status)}
        {shotType && (
          <span className="text-[9px] text-cinema-muted font-mono">{shotType}</span>
        )}
      </div>

      {/* Prompt sections */}
      <div className="flex-1 min-w-0">
        {Object.keys(sections).length > 0 ? (
          <div className="space-y-0.5">
            {Object.entries(sections).map(([tag, text]) => (
              <div key={tag} className="flex gap-2 text-xs">
                <span className={`${sectionColors[tag]} font-mono font-bold shrink-0`}>[{tag}]</span>
                <span className="text-cinema-text/80 truncate">{text}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-cinema-muted truncate">{prompt.slice(0, 120)}...</p>
        )}

        {/* Metadata badges */}
        <div className="flex gap-2 mt-1.5 flex-wrap">
          <span className="text-[10px] text-cinema-muted bg-cinema-panel px-1.5 py-0.5 rounded">
            📷 {shot.camera}
          </span>
          {apiRegistry ? (
            <select
              className="text-[10px] text-cinema-muted bg-cinema-panel px-1 py-0.5 rounded border-0 cursor-pointer hover:text-cinema-text focus:ring-1 focus:ring-cinema-accent"
              value={shot.target_api || 'AUTO'}
              onChange={(e) => updateShotApi(e.target.value)}
              title={apiRegistry[shot.target_api]?.description || ''}
            >
              {(['smart', 'native', 'fal_proxy'] as const).map(cat => {
                const label = cat === 'smart' ? 'Smart' : cat === 'native' ? 'Native APIs' : 'FAL Proxy'
                const entries = Object.entries(apiRegistry).filter(([, v]) => v.category === cat)
                return entries.length > 0 ? (
                  <optgroup key={cat} label={label}>
                    {entries.map(([key, info]) => (
                      <option key={key} value={key}>{info.label}</option>
                    ))}
                  </optgroup>
                ) : null
              })}
            </select>
          ) : (
            <span className="text-[10px] text-cinema-muted bg-cinema-panel px-1.5 py-0.5 rounded">
              {shot.target_api}
            </span>
          )}
        </div>

        {/* Quality metrics row */}
        {(identityScore != null || coherenceScore != null || motionScore != null) && (
          <div className="flex gap-2 mt-1.5">
            {getScoreBadge(identityScore, 'ID')}
            {getScoreBadge(coherenceScore, 'COH')}
            {getScoreBadge(motionScore, 'MOT')}
          </div>
        )}

        {/* Failure reason */}
        {failureReason && isFailed && (
          <p className="text-[10px] text-cinema-danger mt-1">
            Reason: {failureReason.replace(/_/g, ' ')}
          </p>
        )}
      </div>

      {/* Image preview */}
      <div className="relative shrink-0">
        {imageUrl ? (
          <div className="relative">
            <img
              src={`/api/projects/${projectId}/file?path=${encodeURIComponent(imageUrl)}`}
              alt={`Shot ${shotIndex + 1}`}
              className="w-[120px] h-[68px] object-cover rounded border border-cinema-border"
            />
            {getScoreBadge(identityScore)}
          </div>
        ) : (
          <div className={`w-[120px] h-[68px] rounded border border-cinema-border flex items-center justify-center
            ${status === 'generating_image' ? 'bg-cinema-accent/10 animate-pulse' :
              isFailed ? 'bg-cinema-danger/10' : 'bg-cinema-panel'}
          `}>
            <span className="text-cinema-muted text-xs">
              {status === 'generating_image' ? '⏳' : isFailed ? '✕' : '—'}
            </span>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-2 mt-1">
          <button
            onClick={() => setEditingPrompt(true)}
            className="text-[10px] text-cinema-accent hover:text-cinema-accent2"
          >
            ✎ Edit
          </button>
          {(isFailed || isReviewable) && onRegenerate && (
            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              className={`text-[10px] ${regenerating ? 'text-cinema-muted' : 'text-cinema-gold hover:text-cinema-gold-dim'}`}
            >
              {regenerating ? '↻ Regen...' : '↻ Regen'}
            </button>
          )}
        </div>
      </div>

      {/* Approval controls */}
      {isReviewable && imageUrl && !isFailed && (
        <div className="shrink-0 ml-2">
          <ShotApprovalControls
            shot={shotState || {}}
            shotId={shot.id}
            projectId={projectId}
            onAction={() => {}}
          />
        </div>
      )}

      {/* Prompt editor modal */}
      {editingPrompt && (
        <PromptEditor
          shotId={shot.id}
          projectId={projectId}
          currentPrompt={shot.prompt}
          onClose={() => setEditingPrompt(false)}
          onSaved={() => setEditingPrompt(false)}
        />
      )}
    </div>
  )
}
