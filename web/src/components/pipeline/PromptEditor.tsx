import { useEffect, useMemo, useState } from 'react'
import type { AppConfig, Shot } from '../../types/project'
import { classifyShotType, getShotTemplate } from '../../lib/guidance'
import { parsePromptSections, assemblePromptSections, SECTION_LABELS } from '../../lib/promptSections'
import { videoEngines, humanizeEngineReason } from '../../lib/engines'
import { apiGet, apiPut } from '../../lib/api'

interface Props {
  shot: Shot
  shotId: string
  projectId: string
  currentPrompt: string
  onClose: () => void
  onSaved: () => void
}

export default function PromptEditor({ shot, shotId, projectId, currentPrompt, onClose, onSaved }: Props) {
  const [sections, setSections] = useState(() => parsePromptSections(currentPrompt, true))
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [targetApi, setTargetApi] = useState(shot.target_api || 'AUTO')
  const [camera, setCamera] = useState(shot.camera || 'zoom_in_slow')
  const [visualEffect, setVisualEffect] = useState(shot.visual_effect || 'cinematic_glow')
  const [negativeConstraints, setNegativeConstraints] = useState(shot.negative_constraints || '')
  const [continuityConstraints, setContinuityConstraints] = useState(shot.continuity_constraints || '')
  const [intentNotes, setIntentNotes] = useState(shot.intent_notes || '')

  useEffect(() => {
    // project_id scopes the response's `video_engines` server-selectable
    // view (web_server.py:_project_video_engine_rows reads per-project
    // api_engines overrides + persisted shot targets) — see lib/engines.ts.
    // Routed through the typed client for consistency with App.tsx's
    // identical-purpose GET; guarded the same way against a stale response
    // landing after this editor unmounts/re-targets a different project.
    let cancelled = false
    apiGet<AppConfig>(`/api/config?project_id=${encodeURIComponent(projectId)}`).then((result) => {
      if (cancelled) return
      if (result.ok) setConfig(result.data)
    })
    return () => { cancelled = true }
  }, [projectId])

  const livePrompt = useMemo(() => assemblePromptSections(sections), [sections])
  const liveShot = useMemo(() => ({ ...shot, prompt: livePrompt, camera }), [shot, livePrompt, camera])
  const shotType = classifyShotType(liveShot)
  const template = getShotTemplate(liveShot, config)

  const engines = videoEngines(config)

  const handleSave = async () => {
    setSaving(true)
    setSaveError(null)
    const result = await apiPut(`/api/projects/${projectId}/shots/${shotId}`, {
      prompt: livePrompt,
      target_api: targetApi,
      camera,
      visual_effect: visualEffect,
      negative_constraints: negativeConstraints,
      continuity_constraints: continuityConstraints,
      intent_notes: intentNotes,
    })
    setSaving(false)
    // Slice 8 requirement 5: a non-2xx (or network/parse) failure is an
    // error, not optimistic success -- keep the editor open with the
    // unsaved edits intact and surface the error, rather than closing as
    // if the save had landed.
    if (!result.ok) {
      setSaveError(result.error)
      return
    }
    onSaved()
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-panel border border-line rounded-xl w-full max-w-2xl max-h-[80vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-line">
          <h3 className="text-sm font-semibold text-tx">Edit Shot Prompt</h3>
          <button onClick={onClose} className="text-mut hover:text-tx text-lg">&times;</button>
        </div>

        <div className="p-5 space-y-4">
          <div className="rounded border border-acc/20 bg-acc/5 p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold capitalize text-tx">{shotType} footage guidance</div>
                <p className="mt-1 text-xs leading-relaxed text-mut">
                  {template?.description || 'Use one clear visual objective per shot and keep identity, motion, and environment constraints explicit.'}
                </p>
              </div>
              <span className="rounded bg-app px-2 py-0.5 text-eyebrow uppercase tracking-wide text-acc">{shotType}</span>
            </div>
            {template && (
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="rounded bg-app px-2 py-0.5 text-eyebrow text-mut">
                  Recommended API: {config?.api_registry?.[template.target_api]?.label || template.target_api}
                </span>
                <span className="rounded bg-app px-2 py-0.5 text-eyebrow text-mut">
                  CFG {template.guidance}
                </span>
                <span className="rounded bg-app px-2 py-0.5 text-eyebrow text-mut">
                  {template.steps} steps
                </span>
                <span className="rounded bg-app px-2 py-0.5 text-eyebrow text-mut">
                  Denoise {template.denoise_default}
                </span>
                <span className="rounded bg-app px-2 py-0.5 text-eyebrow text-mut">
                  PuLID {template.pulid_weight}
                </span>
              </div>
            )}
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-mono font-bold text-acc">API</label>
              <select
                value={targetApi}
                onChange={e => setTargetApi(e.target.value)}
                className="w-full rounded border border-line bg-app px-3 py-2 text-sm text-tx"
              >
                {engines.length ? engines.map((e) => (
                  <option
                    key={e.key}
                    value={e.key}
                    disabled={!e.selectable}
                    title={e.reason ? humanizeEngineReason(e.reason) : undefined}
                  >
                    {e.label}
                  </option>
                )) : (
                  // Server view not loaded yet (or config isn't project-scoped) —
                  // keep the current value representable rather than guessing engines.
                  <option value={targetApi}>{targetApi}</option>
                )}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-mono font-bold text-acc">Camera Motion</label>
              <select
                value={camera}
                onChange={e => setCamera(e.target.value)}
                className="w-full rounded border border-line bg-app px-3 py-2 text-sm text-tx"
              >
                {(config?.camera_motions || [camera]).map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-mono font-bold text-acc">Finish</label>
              <select
                value={visualEffect}
                onChange={e => setVisualEffect(e.target.value)}
                className="w-full rounded border border-line bg-app px-3 py-2 text-sm text-tx"
              >
                {(config?.visual_effects || [visualEffect]).map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>
          </div>

          {Object.entries(SECTION_LABELS).map(([tag, cfg]) => (
            <div key={tag}>
              <label className={`text-xs font-mono font-bold ${cfg.color} mb-1 block`}>
                [{tag}] {cfg.label}
              </label>
              <textarea
                value={sections[tag] || ''}
                onChange={e => setSections(s => ({ ...s, [tag]: e.target.value }))}
                placeholder={cfg.placeholder}
                rows={tag === 'SCENE' ? 3 : 2}
                className="w-full bg-app border border-line rounded px-3 py-2 text-sm text-tx
                  focus:border-acc focus:outline-none resize-none"
              />
            </div>
          ))}

          <div>
            <label className="mb-1 block text-xs font-mono font-bold text-fail">Negative Constraints</label>
            <textarea
              value={negativeConstraints}
              onChange={e => setNegativeConstraints(e.target.value)}
              rows={2}
              placeholder="What must never happen in this shot"
              className="w-full resize-none rounded border border-line bg-app px-3 py-2 text-sm text-tx focus:border-acc focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-mono font-bold text-acc">Continuity Constraints</label>
            <textarea
              value={continuityConstraints}
              onChange={e => setContinuityConstraints(e.target.value)}
              rows={2}
              placeholder="Spatial position, lighting state, prop continuity, eyeline"
              className="w-full resize-none rounded border border-line bg-app px-3 py-2 text-sm text-tx focus:border-acc focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-mono font-bold text-acc">Intent Notes</label>
            <textarea
              value={intentNotes}
              onChange={e => setIntentNotes(e.target.value)}
              rows={2}
              placeholder="What this shot must accomplish emotionally or narratively"
              className="w-full resize-none rounded border border-line bg-app px-3 py-2 text-sm text-tx focus:border-acc focus:outline-none"
            />
          </div>

          <div className="bg-app border border-line rounded p-3">
            <p className="text-eyebrow text-mut mb-1 font-mono">ASSEMBLED PROMPT:</p>
            <p className="text-xs text-tx/70">{livePrompt}</p>
          </div>
        </div>

        {saveError && (
          <div role="alert" className="mx-5 mb-3 rounded border border-fail/50 bg-fail/10 px-3 py-2 text-xs text-fail">
            Could not save: {saveError}
          </div>
        )}

        <div className="flex justify-end gap-3 px-5 py-3 border-t border-line">
          <button
            onClick={onClose}
            className="text-sm px-4 py-2 rounded text-mut hover:text-tx"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="text-sm px-5 py-2 rounded bg-acc hover:bg-acc text-white font-medium
              disabled:opacity-40"
          >
            {saving ? 'Saving...' : 'Save & Regenerate'}
          </button>
        </div>
      </div>
    </div>
  )
}
