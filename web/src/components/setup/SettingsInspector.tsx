import { useState } from 'react'
import type { Project, AppConfig } from '../../types/project'
import { Section } from '../ui'
import { SelectRow, TextRow } from './inspector/controls'
import { VideoSection } from './inspector/VideoSection'
import { ImageSection } from './inspector/ImageSection'
import { IdentitySection } from './inspector/IdentitySection'
import { VoiceSection } from './inspector/VoiceSection'
import { BudgetSection } from './inspector/BudgetSection'

const API = '/api'

interface Props {
  project: Project
  config: AppConfig | null
  onRefresh: () => void
}

const FALLBACK_MOODS = [
  'melancholic', 'tense', 'hopeful', 'dark', 'cinematic',
  'mysterious', 'romantic', 'energetic', 'peaceful', 'dramatic',
]

/**
 * SettingsInspector — the reconciled Resolve-style right-column inspector for
 * SetupPage. Replaces the interim SettingsPanel mount. Composes:
 *   Project → Video → Image → Identity → Voice → Budget.
 *
 * Settings write contract (shared by every section): read `s =
 * project.global_settings`, write via `update(key, value)` which PUTs the
 * merged `global_settings` then refreshes.
 */
export default function SettingsInspector({ project, config, onRefresh }: Props) {
  const s = project.global_settings as any

  const update = async (key: string, value: any) => {
    const res = await fetch(`${API}/projects/${project.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ global_settings: { ...s, [key]: value } }),
    })
    if (res.ok) onRefresh()
  }

  return (
    <div>
      <ProjectSection s={s} config={config} project={project} update={update} onRefresh={onRefresh} />
      <VideoSection s={s} config={config} update={update} />
      <ImageSection s={s} config={config} update={update} />
      <IdentitySection s={s} update={update} />
      <VoiceSection s={s} config={config} update={update} />
      <BudgetSection s={s} update={update} />
    </div>
  )
}

interface ProjectSectionProps {
  s: any
  config: AppConfig | null
  project: Project
  update: (key: string, value: any) => void | Promise<void>
  onRefresh: () => void
}

function ProjectSection({ s, config, project, update, onRefresh }: ProjectSectionProps) {
  const [generating, setGenerating] = useState(false)
  const aspectRatios = config?.aspect_ratios ?? ['16:9']
  const moods = config?.music_moods?.length ? config.music_moods : FALLBACK_MOODS
  const languages = [
    'English', 'Korean', 'Japanese', 'Mandarin', 'Spanish', 'French',
    'German', 'Hindi', 'Arabic', 'Portuguese', 'Italian', 'Russian',
  ]
  const styleRules = (s.style_rules ?? {}) as Record<string, unknown>
  const hasStyleRules = Object.keys(styleRules).length > 0

  const generateStyleRules = async () => {
    setGenerating(true)
    await fetch(`${API}/projects/${project.id}/style-rules`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mood: s.music_mood,
        color_palette: s.color_palette,
        music_mood: s.music_mood,
      }),
    })
    setGenerating(false)
    onRefresh()
  }

  return (
    <Section title="Project">
      <div className="space-y-3">
        {/* Aspect ratio */}
        <div>
          <span className="mb-1 block font-mono text-[10px] uppercase tracking-[0.09em] text-mut">
            Aspect ratio
          </span>
          <div className="flex flex-wrap gap-1.5">
            {aspectRatios.map((ar) => {
              const active = (s.aspect_ratio ?? '16:9') === ar
              return (
                <button
                  key={ar}
                  type="button"
                  onClick={() => update('aspect_ratio', ar)}
                  aria-pressed={active}
                  className={[
                    'rounded border px-2.5 py-1 text-[11px] transition-colors',
                    active
                      ? 'border-acc bg-acc-dim text-tx'
                      : 'border-line bg-panel text-mut hover:text-tx',
                  ].join(' ')}
                >
                  {ar}
                </button>
              )
            })}
          </div>
        </div>

        <SelectRow
          label="Dialogue language"
          value={s.language ?? 'English'}
          options={languages}
          onChange={(v) => update('language', v)}
          hint="Drives the dialogue writer, TTS voice selection, and transcription language."
        />

        <SelectRow
          label="Music mood"
          value={s.music_mood ?? moods[0]}
          options={moods}
          onChange={(v) => update('music_mood', v)}
        />

        <TextRow
          label="Color palette"
          value={s.color_palette ?? ''}
          onChange={(v) => update('color_palette', v)}
          placeholder="e.g. warm amber vs cold blue"
        />

        {/* AI style rules */}
        <div>
          <div className="mb-1 flex items-center justify-between">
            <span className="font-mono text-[10px] uppercase tracking-[0.09em] text-mut">
              AI style rules
            </span>
            <button
              type="button"
              onClick={generateStyleRules}
              disabled={generating}
              className="text-[10px] font-medium text-acc hover:text-tx disabled:opacity-50"
            >
              {generating ? 'Generating…' : hasStyleRules ? '↻ Regenerate' : '+ Generate'}
            </button>
          </div>
          {hasStyleRules ? (
            <div className="max-h-40 space-y-2 overflow-y-auto rounded border border-line bg-panel p-2">
              {Object.entries(styleRules).map(([key, val]) => {
                let display: string
                if (typeof val === 'string') display = val
                else if (typeof val === 'object' && val !== null)
                  display = Object.entries(val as Record<string, unknown>)
                    .map(([k, v]) => `${k}: ${v}`)
                    .join(', ')
                else display = String(val)
                return (
                  <div key={key}>
                    <span className="font-mono text-[10px] uppercase tracking-[0.09em] text-acc">
                      {key.replace(/_/g, ' ')}
                    </span>
                    <p className="mt-0.5 text-[10px] leading-relaxed text-mut">{display.slice(0, 200)}</p>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-[10px] italic text-mut">
              Research-enhanced style rules generated from your mood + color palette.
            </p>
          )}
        </div>
      </div>
    </Section>
  )
}
