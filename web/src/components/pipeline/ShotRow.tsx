import { useState, useEffect } from 'react'
import type { Shot, ShotState, ApiInfo, AppConfig } from '../../types/project'
import ShotApprovalControls from './ShotApprovalControls'
import PromptEditor from './PromptEditor'
import { classifyShotType, getShotTemplate } from '../../lib/guidance'

// Module-level cache for API registry (shared across all ShotRow instances)
let _configCache: AppConfig | null = null

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
  const color = pct >= 80 ? 'bg-editorial-ready' : pct >= 60 ? 'bg-yellow-500' : 'bg-editorial-curtain'
  return (
    <span className={`${color} text-white text-eyebrow font-bold px-1.5 py-0.5 rounded`}>
      {label ? `${label} ` : ''}{pct}%
    </span>
  )
}

function getStatusBadge(status: string | undefined) {
  const map: Record<string, { color: string; label: string }> = {
    pending: { color: 'bg-editorial-ivory-mute/30', label: 'Pending' },
    generating_image: { color: 'bg-editorial-brass animate-pulse', label: 'Generating...' },
    image_review: { color: 'bg-yellow-500', label: 'Review' },
    generating_video: { color: 'bg-purple-500 animate-pulse', label: 'Video...' },
    post_processing: { color: 'bg-blue-500 animate-pulse', label: 'Processing...' },
    complete: { color: 'bg-editorial-ready', label: 'Done' },
    failed: { color: 'bg-editorial-curtain', label: 'Failed' },
  }
  const s = map[status || 'pending'] || map.pending
  return (
    <span className={`${s.color} text-white text-eyebrow px-1.5 py-0.5 rounded`}>
      {s.label}
    </span>
  )
}

export default function ShotRow({ shot, shotState, shotIndex, sceneId, projectId, onRegenerate }: Props) {
  const [editingPrompt, setEditingPrompt] = useState(false)
  const [regenerating, setRegenerating] = useState(false)
  const [config, setConfig] = useState<AppConfig | null>(_configCache)
  const apiRegistry: Record<string, ApiInfo> | null = config?.api_registry || null

  // Load API registry once (module-level cache shared across instances)
  useEffect(() => {
    if (_configCache) { setConfig(_configCache); return }
    fetch('/api/config').then(r => r.json()).then(cfg => {
      if (cfg.api_registry) {
        _configCache = cfg
        setConfig(cfg)
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
  const shotType = shotState?.shot_type || classifyShotType(shot)
  const shotTemplate = getShotTemplate(shot, config)
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
    <div className={`flex items-start gap-3 px-4 py-3 border-b border-editorial-rule/50 hover:bg-editorial-ink-soft/50
      ${status === 'generating_image' || status === 'generating_video' ? 'bg-editorial-brass/5' : ''}
      ${isFailed ? 'bg-editorial-curtain/5' : ''}
    `}>
      {/* Shot number + status */}
      <div className="flex flex-col items-center gap-1 min-w-[40px]">
        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
          ${status === 'complete' ? 'bg-editorial-ready/20 text-editorial-ready' :
            isFailed ? 'bg-editorial-curtain/20 text-editorial-curtain' :
            'bg-editorial-ink-soft text-editorial-ivory-mute'}
        `}>
          {shotIndex + 1}
        </div>
        {getStatusBadge(status)}
        {shotType && (
          <span className="text-eyebrow-sm text-editorial-ivory-mute font-mono">{shotType}</span>
        )}
      </div>

      {/* Prompt sections */}
      <div className="flex-1 min-w-0">
        {Object.keys(sections).length > 0 ? (
          <div className="space-y-0.5">
            {Object.entries(sections).map(([tag, text]) => (
              <div key={tag} className="flex gap-2 text-xs">
                <span className={`${sectionColors[tag]} font-mono font-bold shrink-0`}>[{tag}]</span>
                <span className="text-editorial-ivory/80 truncate">{text}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-editorial-ivory-mute truncate">{prompt.slice(0, 120)}...</p>
        )}

        {/* Metadata badges */}
        <div className="flex gap-2 mt-1.5 flex-wrap">
          <span className="text-eyebrow text-editorial-ivory-mute bg-editorial-ink-soft px-1.5 py-0.5 rounded">
            📷 {shot.camera}
          </span>
          {apiRegistry ? (
            <select
              className="text-eyebrow text-editorial-ivory-mute bg-editorial-ink-soft px-1 py-0.5 rounded border-0 cursor-pointer hover:text-editorial-ivory focus:ring-1 focus:ring-editorial-brass"
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
            <span className="text-eyebrow text-editorial-ivory-mute bg-editorial-ink-soft px-1.5 py-0.5 rounded">
              {shot.target_api}
            </span>
          )}
          {shotTemplate && (
            <>
              <span className="text-eyebrow text-editorial-ivory-mute bg-editorial-ink-soft px-1.5 py-0.5 rounded">
                Best: {apiRegistry?.[shotTemplate.target_api]?.label || shotTemplate.target_api}
              </span>
              <span className="text-eyebrow text-editorial-ivory-mute bg-editorial-ink-soft px-1.5 py-0.5 rounded">
                CFG {shotTemplate.guidance} / {shotTemplate.steps} steps
              </span>
            </>
          )}
        </div>

        {shotTemplate && (
          <p className="mt-1 text-eyebrow text-editorial-ivory-mute">
            {shotTemplate.description}
          </p>
        )}

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
          <p className="text-eyebrow text-editorial-curtain mt-1">
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
              className="w-[120px] h-[68px] object-cover rounded border border-editorial-rule"
            />
            {getScoreBadge(identityScore)}
          </div>
        ) : (
          <div className={`w-[120px] h-[68px] rounded border border-editorial-rule flex items-center justify-center
            ${status === 'generating_image' ? 'bg-editorial-brass/10 animate-pulse' :
              isFailed ? 'bg-editorial-curtain/10' : 'bg-editorial-ink-soft'}
          `}>
            <span className="text-editorial-ivory-mute text-xs">
              {status === 'generating_image' ? '⏳' : isFailed ? '✕' : '—'}
            </span>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-2 mt-1">
          <button
            onClick={() => setEditingPrompt(true)}
            className="text-eyebrow text-editorial-brass hover:text-editorial-brass"
          >
            ✎ Edit
          </button>
          {(isFailed || isReviewable) && onRegenerate && (
            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              className={`text-eyebrow ${regenerating ? 'text-editorial-ivory-mute' : 'text-editorial-brass hover:text-editorial-brass-deep'}`}
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
          shot={shot}
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
