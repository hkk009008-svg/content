import { useEffect, useMemo, useState } from 'react'
import type { AppConfig, Shot } from '../../types/project'
import { classifyShotType, getShotTemplate } from '../../lib/guidance'

interface Props {
  shot: Shot
  shotId: string
  projectId: string
  currentPrompt: string
  onClose: () => void
  onSaved: () => void
}

// Parse [SHOT][SCENE][ACTION][OUTFIT][QUALITY] sections
function parseStructured(prompt: string): Record<string, string> {
  const sections: Record<string, string> = {}
  for (const tag of ['SHOT', 'SCENE', 'ACTION', 'OUTFIT', 'QUALITY']) {
    const match = prompt.match(new RegExp(`\\[${tag}\\]\\s*(.+?)(?=\\[(?:SHOT|SCENE|ACTION|OUTFIT|QUALITY)\\]|$)`, 's'))
    if (match) sections[tag] = match[1].trim()
  }
  // If no sections found, put everything in SCENE
  if (Object.keys(sections).length === 0) {
    sections['SCENE'] = prompt
  }
  return sections
}

function assembleSections(sections: Record<string, string>): string {
  return Object.entries(sections)
    .filter(([, v]) => v.trim())
    .map(([k, v]) => `[${k}] ${v}`)
    .join(' ')
}

const SECTION_LABELS: Record<string, { label: string; color: string; placeholder: string }> = {
  SHOT: { label: 'Camera', color: 'text-cyan-400', placeholder: 'e.g. Medium shot, 85mm f/1.4 lens, shallow DoF' },
  SCENE: { label: 'Scene', color: 'text-indigo-400', placeholder: 'e.g. Snowy park with bare trees, overcast sky, 4500K' },
  ACTION: { label: 'Action', color: 'text-amber-400', placeholder: 'e.g. Walking toward camera, looking directly at camera' },
  OUTFIT: { label: 'Outfit', color: 'text-pink-400', placeholder: 'e.g. Red wool coat over white turtleneck' },
  QUALITY: { label: 'Quality', color: 'text-gray-400', placeholder: 'e.g. Shot on Arri Alexa, 4K RAW, photorealistic' },
}

export default function PromptEditor({ shot, shotId, projectId, currentPrompt, onClose, onSaved }: Props) {
  const [sections, setSections] = useState(() => parseStructured(currentPrompt))
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [saving, setSaving] = useState(false)
  const [targetApi, setTargetApi] = useState(shot.target_api || 'AUTO')
  const [camera, setCamera] = useState(shot.camera || 'zoom_in_slow')
  const [visualEffect, setVisualEffect] = useState(shot.visual_effect || 'cinematic_glow')
  const [negativeConstraints, setNegativeConstraints] = useState(shot.negative_constraints || '')
  const [continuityConstraints, setContinuityConstraints] = useState(shot.continuity_constraints || '')
  const [intentNotes, setIntentNotes] = useState(shot.intent_notes || '')

  useEffect(() => {
    fetch('/api/config').then(r => r.json()).then(setConfig).catch(() => {})
  }, [])

  const livePrompt = useMemo(() => assembleSections(sections), [sections])
  const liveShot = useMemo(() => ({ ...shot, prompt: livePrompt, camera }), [shot, livePrompt, camera])
  const shotType = classifyShotType(liveShot)
  const template = getShotTemplate(liveShot, config)

  const handleSave = async () => {
    setSaving(true)
    await fetch(`/api/projects/${projectId}/shots/${shotId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: livePrompt,
        target_api: targetApi,
        camera,
        visual_effect: visualEffect,
        negative_constraints: negativeConstraints,
        continuity_constraints: continuityConstraints,
        intent_notes: intentNotes,
      }),
    })
    setSaving(false)
    onSaved()
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-cinema-panel border border-cinema-border rounded-xl w-full max-w-2xl max-h-[80vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-cinema-border">
          <h3 className="text-sm font-semibold text-cinema-text">Edit Shot Prompt</h3>
          <button onClick={onClose} className="text-cinema-muted hover:text-cinema-text text-lg">&times;</button>
        </div>

        <div className="p-5 space-y-4">
          <div className="rounded border border-cinema-accent/20 bg-cinema-accent/5 p-3">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold capitalize text-cinema-text">{shotType} footage guidance</div>
                <p className="mt-1 text-xs leading-relaxed text-cinema-muted">
                  {template?.description || 'Use one clear visual objective per shot and keep identity, motion, and environment constraints explicit.'}
                </p>
              </div>
              <span className="rounded bg-cinema-bg px-2 py-0.5 text-[10px] uppercase tracking-wide text-cinema-accent">{shotType}</span>
            </div>
            {template && (
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="rounded bg-cinema-bg px-2 py-0.5 text-[10px] text-cinema-muted">
                  Recommended API: {config?.api_registry?.[template.target_api]?.label || template.target_api}
                </span>
                <span className="rounded bg-cinema-bg px-2 py-0.5 text-[10px] text-cinema-muted">
                  CFG {template.guidance}
                </span>
                <span className="rounded bg-cinema-bg px-2 py-0.5 text-[10px] text-cinema-muted">
                  {template.steps} steps
                </span>
                <span className="rounded bg-cinema-bg px-2 py-0.5 text-[10px] text-cinema-muted">
                  Denoise {template.denoise_default}
                </span>
                <span className="rounded bg-cinema-bg px-2 py-0.5 text-[10px] text-cinema-muted">
                  PuLID {template.pulid_weight}
                </span>
              </div>
            )}
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-mono font-bold text-cinema-accent">API</label>
              <select
                value={targetApi}
                onChange={e => setTargetApi(e.target.value)}
                className="w-full rounded border border-cinema-border bg-cinema-bg px-3 py-2 text-sm text-cinema-text"
              >
                {config?.api_registry ? Object.entries(config.api_registry).map(([key, info]) => (
                  <option key={key} value={key}>{info.label}</option>
                )) : (
                  <>
                    <option value="AUTO">Auto</option>
                    <option value="KLING_NATIVE">Kling</option>
                    <option value="SORA_NATIVE">Sora</option>
                    <option value="VEO_NATIVE">Veo</option>
                    <option value="LTX">LTX</option>
                  </>
                )}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-mono font-bold text-cinema-accent">Camera Motion</label>
              <select
                value={camera}
                onChange={e => setCamera(e.target.value)}
                className="w-full rounded border border-cinema-border bg-cinema-bg px-3 py-2 text-sm text-cinema-text"
              >
                {(config?.camera_motions || [camera]).map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-mono font-bold text-cinema-accent">Finish</label>
              <select
                value={visualEffect}
                onChange={e => setVisualEffect(e.target.value)}
                className="w-full rounded border border-cinema-border bg-cinema-bg px-3 py-2 text-sm text-cinema-text"
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
                className="w-full bg-cinema-bg border border-cinema-border rounded px-3 py-2 text-sm text-cinema-text
                  focus:border-cinema-accent focus:outline-none resize-none"
              />
            </div>
          ))}

          <div>
            <label className="mb-1 block text-xs font-mono font-bold text-cinema-danger">Negative Constraints</label>
            <textarea
              value={negativeConstraints}
              onChange={e => setNegativeConstraints(e.target.value)}
              rows={2}
              placeholder="What must never happen in this shot"
              className="w-full resize-none rounded border border-cinema-border bg-cinema-bg px-3 py-2 text-sm text-cinema-text focus:border-cinema-accent focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-mono font-bold text-cinema-accent">Continuity Constraints</label>
            <textarea
              value={continuityConstraints}
              onChange={e => setContinuityConstraints(e.target.value)}
              rows={2}
              placeholder="Spatial position, lighting state, prop continuity, eyeline"
              className="w-full resize-none rounded border border-cinema-border bg-cinema-bg px-3 py-2 text-sm text-cinema-text focus:border-cinema-accent focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-mono font-bold text-cinema-accent">Intent Notes</label>
            <textarea
              value={intentNotes}
              onChange={e => setIntentNotes(e.target.value)}
              rows={2}
              placeholder="What this shot must accomplish emotionally or narratively"
              className="w-full resize-none rounded border border-cinema-border bg-cinema-bg px-3 py-2 text-sm text-cinema-text focus:border-cinema-accent focus:outline-none"
            />
          </div>

          <div className="bg-cinema-bg border border-cinema-border rounded p-3">
            <p className="text-[10px] text-cinema-muted mb-1 font-mono">ASSEMBLED PROMPT:</p>
            <p className="text-xs text-cinema-text/70">{livePrompt}</p>
          </div>
        </div>

        <div className="flex justify-end gap-3 px-5 py-3 border-t border-cinema-border">
          <button
            onClick={onClose}
            className="text-sm px-4 py-2 rounded text-cinema-muted hover:text-cinema-text"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="text-sm px-5 py-2 rounded bg-cinema-accent hover:bg-cinema-accent2 text-white font-medium
              disabled:opacity-40"
          >
            {saving ? 'Saving...' : 'Save & Regenerate'}
          </button>
        </div>
      </div>
    </div>
  )
}
