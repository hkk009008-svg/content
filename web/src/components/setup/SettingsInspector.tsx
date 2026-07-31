import { useState } from 'react'
import type { Project, AppConfig } from '../../types/project'
import { Section, BusyState, ErrorState, LiveRegion } from '../ui'
import { SelectRow, TextRow } from './inspector/controls'
import { VideoSection } from './inspector/VideoSection'
import { ImageSection } from './inspector/ImageSection'
import { IdentitySection } from './inspector/IdentitySection'
import { VoiceSection } from './inspector/VoiceSection'
import { BudgetSection } from './inspector/BudgetSection'
import { apiPost, apiPut, type ApiResult } from '../../lib/api'

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
 *
 * Every write goes through `runMutation` below, so a rejection surfaces the
 * banner instead of silently no-op'ing. That is a realistic outcome here,
 * not a theoretical one: this route fails closed with 409
 * `settings_revision_conflict` whenever the project's `global_settings`
 * revision has moved on (web_server.py `api_update_project`), and the
 * controls render from `project.global_settings` — so without the banner a
 * rejected change just keeps showing the old value with no explanation.
 *
 * Slice 13b renders that banner through the shared `ErrorState` primitive
 * (still `role="alert"`, so it's the same element the runMutation tests
 * already pin) instead of a bespoke `<div>`, adds a `BusyState` pill while
 * an `update()` write is in flight (sliders/toggles/selects had no busy
 * feedback at all), and a polite `LiveRegion` confirmation on success --
 * NOT a persistent visible "Saved" card, which would fire on every
 * keystroke/drag tick and be exactly the noise the shared primitives exist
 * to replace.
 */
export default function SettingsInspector({ project, config, onRefresh }: Props) {
  const s = project.global_settings as any
  const [saveError, setSaveError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [savedNotice, setSavedNotice] = useState('')

  /** Sibling of ShotInspector's `runMutation` — same contract: surface and
   *  don't refresh on failure, clear and refresh on a confirmed success. */
  const runMutation = async (request: Promise<ApiResult<unknown>>): Promise<boolean> => {
    const result = await request
    if (!result.ok) {
      setSaveError(result.error)
      return false
    }
    setSaveError(null)
    onRefresh()
    return true
  }

  // Returns void rather than the boolean `runMutation` produces: the five
  // child sections type `update` as `=> void | Promise<void>`, and their
  // controls render straight from `project.global_settings` (server state),
  // so there is no optimistic local value for them to revert -- the banner
  // is the whole remedy.
  const update = async (key: string, value: any): Promise<void> => {
    setBusy(true)
    const ok = await runMutation(apiPut(`${API}/projects/${project.id}`, { global_settings: { ...s, [key]: value } }))
    setBusy(false)
    if (ok) setSavedNotice(`Saved ${key.replace(/_/g, ' ')}`)
  }

  return (
    <div>
      {busy && (
        <div className="border-b border-line px-3 py-2">
          <BusyState label="Saving settings" />
        </div>
      )}
      {saveError && (
        <ErrorState
          title="Setting not saved"
          message={saveError}
          onDismiss={() => setSaveError(null)}
          className="border-x-0 border-t-0"
        />
      )}
      <LiveRegion message={savedNotice} />
      <ProjectSection s={s} config={config} project={project} update={update} runMutation={runMutation} />
      <VideoSection s={s} config={config} update={update} />
      <ImageSection s={s} config={config} update={update} />
      <IdentitySection s={s} update={update} />
      <VoiceSection s={s} config={config} update={update} projectId={project.id} onRefresh={onRefresh} />
      <BudgetSection s={s} update={update} />
    </div>
  )
}

interface ProjectSectionProps {
  s: any
  config: AppConfig | null
  project: Project
  update: (key: string, value: any) => void | Promise<void>
  /** Threaded down instead of a bare `onRefresh` so the style-rules POST
   *  reports through the parent's single banner rather than needing its own. */
  runMutation: (request: Promise<ApiResult<unknown>>) => Promise<boolean>
}

function ProjectSection({ s, config, project, update, runMutation }: ProjectSectionProps) {
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
    await runMutation(apiPost(`${API}/projects/${project.id}/style-rules`, {
      mood: s.music_mood,
      color_palette: s.color_palette,
      music_mood: s.music_mood,
    }))
    setGenerating(false)
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
