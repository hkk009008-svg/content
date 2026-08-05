import { useEffect, useRef, useState } from 'react'
import type { Project, AppConfig, GpuWorkerStatus } from '../../types/project'
import { Section, BusyState, ErrorState, LiveRegion } from '../ui'
import { SelectRow, TextRow, ToggleRow } from './inspector/controls'
import { VideoSection } from './inspector/VideoSection'
import { ImageSection } from './inspector/ImageSection'
import { GpuWorkersSection } from './inspector/GpuWorkersSection'
import { IdentitySection } from './inspector/IdentitySection'
import { VoiceSection } from './inspector/VoiceSection'
import { AutoApproveSection } from './inspector/AutoApproveSection'
import { BudgetSection } from './inspector/BudgetSection'
import { apiPatch, apiPost, type ApiResult } from '../../lib/api'
import { settingsRevisionConflict } from '../../lib/settingsRevision'

const API = '/api'

interface Props {
  project: Project
  config: AppConfig | null
  onRefresh: () => void | Promise<void>
}

const FALLBACK_MOODS = [
  'melancholic', 'tense', 'hopeful', 'dark', 'cinematic',
  'mysterious', 'romantic', 'energetic', 'peaceful', 'dramatic',
]

/**
 * SettingsInspector — the reconciled Resolve-style right-column inspector for
 * SetupPage. Replaces the interim SettingsPanel mount. Composes:
 *   Project → Video → Image → Identity → Voice → Auto-Approve → Budget.
 *
 * Settings write contract (shared by every section): read `s =
 * project.global_settings`, write via `update(key, value)` which PATCHes one
 * revision-bound setting then refreshes authoritative project state.
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
  const [imageWorker, setImageWorker] = useState<GpuWorkerStatus | null>(null)
  const currentProjectIdRef = useRef(project.id)
  const revisionByProjectRef = useRef(new Map<string, number>())
  // Last server-confirmed snapshot. Functional nested-setting updates are
  // evaluated against this map when their queued request actually runs, so
  // a conflict rebase cannot drop fields another writer added meanwhile.
  const authoritativeSettingsByProjectRef = useRef(new Map<string, Record<string, any>>())
  // Optimistic composition snapshot used only while enqueueing rapid local
  // edits. It is reconciled back to the authoritative map when the queue
  // drains.
  const settingsByProjectRef = useRef(new Map<string, Record<string, any>>())
  const settingsWriteQueueRef = useRef<Promise<void>>(Promise.resolve())
  const pendingSettingsWritesRef = useRef(0)

  // Keep the queue's authoritative revision/snapshot aligned with parent
  // refreshes, but never roll it backward while a queued response is newer
  // than the currently rendered project prop.
  useEffect(() => {
    currentProjectIdRef.current = project.id
    const renderedRevision = Number.isInteger(s.revision) ? s.revision : 0
    const knownRevision = revisionByProjectRef.current.get(project.id) ?? -1
    if (renderedRevision >= knownRevision) {
      revisionByProjectRef.current.set(project.id, renderedRevision)
      authoritativeSettingsByProjectRef.current.set(project.id, { ...s })
      if (pendingSettingsWritesRef.current === 0) {
        settingsByProjectRef.current.set(project.id, { ...s })
      }
    }
  }, [project.id, s])

  /** Sibling of ShotInspector's `runMutation`: ordinary failures surface
   *  without refresh; a revision conflict also adopts/refreshes the server
   *  snapshot so an explicit retry cannot remain pinned to stale state. */
  const runMutation = async (request: Promise<ApiResult<unknown>>): Promise<boolean> => {
    const pid = project.id
    const result = await request
    if (!result.ok) {
      const conflict = settingsRevisionConflict(result)
      if (conflict) {
        const adoptedSettings = {
          ...conflict.globalSettings,
          revision: conflict.currentRevision,
        }
        revisionByProjectRef.current.set(pid, conflict.currentRevision)
        authoritativeSettingsByProjectRef.current.set(pid, adoptedSettings)
        if (pendingSettingsWritesRef.current === 0) {
          settingsByProjectRef.current.set(pid, { ...adoptedSettings })
        }
      }
      if (currentProjectIdRef.current === pid) {
        setSaveError(result.error)
        // A second raced conflict is not retried forever. Refresh the rendered
        // project once so the next explicit action starts from the adopted
        // server revision instead of repeating the same stale request.
        if (conflict) await onRefresh()
      }
      return false
    }
    if (currentProjectIdRef.current === pid) {
      setSaveError(null)
      await onRefresh()
    }
    return true
  }

  // Serialize settings writes. Range/text controls emit on every input event;
  // sending those concurrently with one rendered revision makes all but an
  // arbitrary first request conflict. Each queued PATCH instead uses the
  // revision returned by its predecessor. A functional value lets nested
  // objects (api_engines/auto_approve) merge against the latest queued
  // snapshot rather than a stale render.
  const update = async (
    key: string,
    value: any | ((current: any) => any),
  ): Promise<void> => {
    const pid = project.id
    const renderedRevision = Number.isInteger(s.revision) ? s.revision : 0
    const shadow = settingsByProjectRef.current.get(pid) ?? { ...s }
    const optimisticValue = typeof value === 'function' ? value(shadow[key]) : value
    settingsByProjectRef.current.set(pid, { ...shadow, [key]: optimisticValue })

    pendingSettingsWritesRef.current += 1
    setBusy(true)

    const execute = async () => {
      let revision = revisionByProjectRef.current.get(pid) ?? renderedRevision
      let baseSettings = authoritativeSettingsByProjectRef.current.get(pid) ?? { ...s }
      let resolvedValue = typeof value === 'function' ? value(baseSettings[key]) : value
      const sendPatch = (expectedRevision: number, nextValue: any) =>
        apiPatch<Project>(`${API}/projects/${pid}`, {
          global_settings: { revision: expectedRevision, [key]: nextValue },
        })

      let result = await sendPatch(revision, resolvedValue)
      const firstConflict = settingsRevisionConflict(result)
      if (firstConflict) {
        // Adopt the server snapshot, rebase this one user intent, and retry
        // exactly once. Even if that retry races and conflicts again, the
        // second payload is adopted below so future edits do not remain
        // wedged on the original stale revision.
        revision = firstConflict.currentRevision
        baseSettings = {
          ...firstConflict.globalSettings,
          revision,
        }
        revisionByProjectRef.current.set(pid, revision)
        authoritativeSettingsByProjectRef.current.set(pid, baseSettings)
        resolvedValue = typeof value === 'function' ? value(baseSettings[key]) : value
        result = await sendPatch(revision, resolvedValue)
      }

      if (!result.ok) {
        const finalConflict = settingsRevisionConflict(result)
        if (finalConflict) {
          const adoptedSettings = {
            ...finalConflict.globalSettings,
            revision: finalConflict.currentRevision,
          }
          revisionByProjectRef.current.set(pid, finalConflict.currentRevision)
          authoritativeSettingsByProjectRef.current.set(pid, adoptedSettings)
        }
        if (currentProjectIdRef.current === pid) setSaveError(result.error)
        return
      }

      const returnedSettings = result.data?.global_settings
      const returnedRevision = Number.isInteger(returnedSettings?.revision)
        ? returnedSettings.revision!
        : revision + 1
      revisionByProjectRef.current.set(pid, returnedRevision)
      authoritativeSettingsByProjectRef.current.set(
        pid,
        returnedSettings
          ? { ...returnedSettings, revision: returnedRevision }
          : { ...baseSettings, [key]: resolvedValue, revision: returnedRevision },
      )

      if (currentProjectIdRef.current === pid) {
        setSaveError(null)
        setSavedNotice(`Saved ${key.replace(/_/g, ' ')}`)
        await onRefresh()
      }
    }

    const operation = settingsWriteQueueRef.current.then(execute, execute)
    settingsWriteQueueRef.current = operation.then(() => undefined, () => undefined)
    try {
      await operation
    } finally {
      pendingSettingsWritesRef.current -= 1
      if (pendingSettingsWritesRef.current === 0) {
        const authoritative = authoritativeSettingsByProjectRef.current.get(pid)
        if (authoritative) settingsByProjectRef.current.set(pid, { ...authoritative })
      }
      if (
        currentProjectIdRef.current === pid
        && pendingSettingsWritesRef.current === 0
      ) {
        setBusy(false)
      }
    }
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
      <ImageSection s={s} config={config} imageWorker={imageWorker} update={update} />
      <GpuWorkersSection onImageWorker={setImageWorker} />
      <IdentitySection s={s} update={update} />
      <VoiceSection s={s} config={config} update={update} projectId={project.id} onRefresh={onRefresh} />
      <AutoApproveSection s={s} update={update} />
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
    const request = (expectedRevision: number) => apiPost(`${API}/projects/${project.id}/style-rules`, {
      expected_revision: expectedRevision,
      mood: s.music_mood,
      color_palette: s.color_palette,
      music_mood: s.music_mood,
    })
    let result = await request(Number.isInteger(s.revision) ? s.revision : 0)
    const conflict = settingsRevisionConflict(result)
    if (conflict) result = await request(conflict.currentRevision)
    await runMutation(Promise.resolve(result))
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

        <ToggleRow
          label="Research location references"
          checked={s.location_research === true}
          onChange={(v) => update('location_research', v)}
          hint="When you add a location, search for visual references to supplement your uploads. Requires Tavily; off by default."
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
