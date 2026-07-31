import { useState, useEffect } from 'react'
import type { Shot, ShotState, ApiInfo, AppConfig } from '../../types/project'
import ShotApprovalControls from './ShotApprovalControls'
import PromptEditor from './PromptEditor'
import { classifyShotType, getShotTemplate } from '../../lib/guidance'
import { parsePromptSections } from '../../lib/promptSections'
import { videoEngines, humanizeEngineReason } from '../../lib/engines'
import { apiPut } from '../../lib/api'

// Module-level cache for API registry (shared across all ShotRow instances),
// keyed by projectId — `config.video_engines` is project-scoped (the server
// reads that project's persisted shot targets + api_engines overrides), so a
// cache hit for a different project would leak stale selectability.
let _configCache: AppConfig | null = null
let _configCacheProjectId: string | null = null

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
  const color = pct >= 80 ? 'bg-ok' : pct >= 60 ? 'bg-yellow-500' : 'bg-fail'
  return (
    <span className={`${color} text-white text-eyebrow font-bold px-1.5 py-0.5 rounded`}>
      {label ? `${label} ` : ''}{pct}%
    </span>
  )
}

function getStatusBadge(status: string | undefined) {
  const map: Record<string, { color: string; label: string }> = {
    pending: { color: 'bg-mut/30', label: 'Pending' },
    generating_image: { color: 'bg-acc animate-pulse', label: 'Generating...' },
    image_review: { color: 'bg-yellow-500', label: 'Review' },
    generating_video: { color: 'bg-purple-500 animate-pulse', label: 'Video...' },
    post_processing: { color: 'bg-blue-500 animate-pulse', label: 'Processing...' },
    complete: { color: 'bg-ok', label: 'Done' },
    failed: { color: 'bg-fail', label: 'Failed' },
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
  const [apiUpdateError, setApiUpdateError] = useState<string | null>(null)
  const [config, setConfig] = useState<AppConfig | null>(
    _configCacheProjectId === projectId ? _configCache : null,
  )
  const apiRegistry: Record<string, ApiInfo> | null = config?.api_registry || null

  // Load config once per project (module-level cache shared across instances).
  useEffect(() => {
    if (_configCacheProjectId === projectId && _configCache) {
      setConfig(_configCache)
      return
    }
    // project_id scopes `video_engines` (see lib/engines.ts) to this project's
    // api_engines overrides + persisted shot targets.
    fetch(`/api/config?project_id=${encodeURIComponent(projectId)}`).then(r => r.json()).then(cfg => {
      if (cfg.api_registry) {
        _configCache = cfg
        _configCacheProjectId = projectId
        setConfig(cfg)
      }
    }).catch(() => {})
  }, [projectId])

  // Sibling of PromptEditor's `handleSave` PUT to the same shots endpoint --
  // same truthfulness contract: a non-2xx (or network) failure must not be
  // painted as success. Only mutate `shot.target_api` (the existing
  // "optimistic update" -- this component has no setter for the parent's
  // `shot` object, so a confirmed-good value is written back onto the prop
  // in place) once the server has actually confirmed it; setting the error
  // state below forces a re-render either way, so a failure's rejected
  // value never sticks in the (controlled) select -- it re-renders showing
  // the still-true `shot.target_api` instead.
  const updateShotApi = async (newApi: string) => {
    setApiUpdateError(null)
    const result = await apiPut(`/api/projects/${projectId}/shots/${shot.id}`, { target_api: newApi })
    if (!result.ok) {
      setApiUpdateError(result.error)
      return
    }
    shot.target_api = newApi
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
  const engines = videoEngines(config)

  // Parse structured sections from prompt (shared with PromptEditor / ShotInspector)
  const prompt = shot.prompt || ''
  const sections = parsePromptSections(prompt)

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
    <div className={`flex items-start gap-3 px-4 py-3 border-b border-line/50 hover:bg-panel/50
      ${status === 'generating_image' || status === 'generating_video' ? 'bg-acc/5' : ''}
      ${isFailed ? 'bg-fail/5' : ''}
    `}>
      {/* Shot number + status */}
      <div className="flex flex-col items-center gap-1 min-w-[40px]">
        <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
          ${status === 'complete' ? 'bg-ok/20 text-ok' :
            isFailed ? 'bg-fail/20 text-fail' :
            'bg-panel text-mut'}
        `}>
          {shotIndex + 1}
        </div>
        {getStatusBadge(status)}
        {shotType && (
          <span className="text-eyebrow-sm text-mut font-mono">{shotType}</span>
        )}
      </div>

      {/* Prompt sections */}
      <div className="flex-1 min-w-0">
        {Object.keys(sections).length > 0 ? (
          <div className="space-y-0.5">
            {Object.entries(sections).map(([tag, text]) => (
              <div key={tag} className="flex gap-2 text-xs">
                <span className={`${sectionColors[tag]} font-mono font-bold shrink-0`}>[{tag}]</span>
                <span className="text-tx/80 truncate">{text}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-mut truncate">{prompt.slice(0, 120)}...</p>
        )}

        {/* Metadata badges */}
        <div className="flex gap-2 mt-1.5 flex-wrap">
          <span className="text-eyebrow text-mut bg-panel px-1.5 py-0.5 rounded">
            📷 {shot.camera}
          </span>
          {engines.length > 0 ? (
            <select
              className="text-eyebrow text-mut bg-panel px-1 py-0.5 rounded border-0 cursor-pointer hover:text-tx focus:ring-1 focus:ring-acc"
              value={shot.target_api || 'AUTO'}
              onChange={(e) => updateShotApi(e.target.value)}
              title={apiRegistry?.[shot.target_api]?.description || ''}
            >
              {engines.map((e) => (
                <option
                  key={e.key}
                  value={e.key}
                  disabled={!e.selectable}
                  title={e.reason ? humanizeEngineReason(e.reason) : undefined}
                >
                  {e.label}
                </option>
              ))}
            </select>
          ) : (
            <span className="text-eyebrow text-mut bg-panel px-1.5 py-0.5 rounded">
              {shot.target_api}
            </span>
          )}
          {shotTemplate && (
            <>
              <span className="text-eyebrow text-mut bg-panel px-1.5 py-0.5 rounded">
                Best: {apiRegistry?.[shotTemplate.target_api]?.label || shotTemplate.target_api}
              </span>
              <span className="text-eyebrow text-mut bg-panel px-1.5 py-0.5 rounded">
                CFG {shotTemplate.guidance} / {shotTemplate.steps} steps
              </span>
            </>
          )}
        </div>

        {apiUpdateError && (
          <p role="alert" className="mt-1 text-eyebrow text-fail">
            Could not change API: {apiUpdateError}
          </p>
        )}

        {shotTemplate && (
          <p className="mt-1 text-eyebrow text-mut">
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
          <p className="text-eyebrow text-fail mt-1">
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
              className="w-[120px] h-[68px] object-cover rounded border border-line"
            />
            {getScoreBadge(identityScore)}
          </div>
        ) : (
          <div className={`w-[120px] h-[68px] rounded border border-line flex items-center justify-center
            ${status === 'generating_image' ? 'bg-acc/10 animate-pulse' :
              isFailed ? 'bg-fail/10' : 'bg-panel'}
          `}>
            <span className="text-mut text-xs">
              {status === 'generating_image' ? '⏳' : isFailed ? '✕' : '—'}
            </span>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex gap-2 mt-1">
          <button
            onClick={() => setEditingPrompt(true)}
            className="text-eyebrow text-acc hover:text-acc"
          >
            ✎ Edit
          </button>
          {(isFailed || isReviewable) && onRegenerate && (
            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              className={`text-eyebrow ${regenerating ? 'text-mut' : 'text-acc hover:text-acc'}`}
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
