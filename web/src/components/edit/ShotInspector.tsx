import { useEffect, useState, type ReactNode } from 'react'
import type { AppConfig, Project, Scene, Shot, ShotState } from '../../types/project'
import { Badge, LiveRegion, MICRO_LABEL, Section, SelectPill, Toggle } from '../ui'
import { classifyShotType, getShotTemplate } from '../../lib/guidance'
import { videoEngines, humanizeEngineReason } from '../../lib/engines'
import { PROMPT_SECTION_TAGS, parsePromptSections, assemblePromptSections } from '../../lib/promptSections'
import { apiPut, type ApiResult } from '../../lib/api'

interface Props {
  project: Project
  config: AppConfig | null
  scene: Scene | null
  shot: Shot | null
  shotState: Partial<ShotState> | undefined
  apiBase?: string
  onRefreshProject: () => Promise<void> | void
}

interface ShotForm {
  sections: Record<string, string>
  negativeConstraints: string
  continuityConstraints: string
  intentNotes: string
  targetApi: string
  camera: string
  visualEffect: string
}

function buildForm(shot: Shot | null): ShotForm {
  return {
    sections: shot ? parsePromptSections(shot.prompt || '', true) : {},
    negativeConstraints: shot?.negative_constraints || '',
    continuityConstraints: shot?.continuity_constraints || '',
    intentNotes: shot?.intent_notes || '',
    targetApi: shot?.target_api || 'AUTO',
    camera: shot?.camera || '',
    visualEffect: shot?.visual_effect || '',
  }
}

const FIELD_CLS =
  'w-full resize-none rounded border border-line bg-panel px-2 py-1.5 text-[11px] text-tx ' +
  'focus:border-acc focus:outline-none'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <span className={`${MICRO_LABEL} mb-1 block`}>{label}</span>
      {children}
    </div>
  )
}

function ReadOnlyRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="text-mut">{label}</span>
      <span className="font-mono text-tx">{value}</span>
    </div>
  )
}

/**
 * ShotInspector — right rail of the Edit workspace. Four sections:
 *   Prompt (positive/negative, shared `promptSections` parse/assemble)
 *   Dialogue (scene line + primary character's voice + pace wpm)
 *   Shot (type, primary API, duration)
 *   Identity (PuLID weight/threshold display + the pod-keyframe toggle)
 *
 * Prompt/Shot fields save through the PromptEditor PUT contract
 * (`PUT /api/projects/{pid}/shots/{sid}` — verbatim field names). Voice
 * saves through the character PUT (partial update). Pace + the identity
 * backend toggle are project-level `global_settings` and save through the
 * same `PUT /api/projects/{pid}` merge contract SettingsInspector uses.
 *
 * Every write above goes through `apiPut` + the shared `runMutation` helper
 * below: a non-2xx/network failure surfaces the inline error banner and
 * never refreshes; only a confirmed success clears it and pulls the
 * authoritative project.
 */
export default function ShotInspector({ project, config, scene, shot, shotState, apiBase = '', onRefreshProject }: Props) {
  const base = apiBase || '/api'
  const [form, setForm] = useState<ShotForm>(() => buildForm(shot))
  // Sibling of PromptEditor's `handleSave` PUT to the same shots endpoint --
  // same truthfulness contract: surfaced here since this panel has no
  // modal/"editor" of its own to keep open, so an inline banner is the
  // equivalent of PromptEditor's `saveError`.
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    setForm(buildForm(shot))
    setSaveError(null)
  }, [shot?.id])

  if (!shot) {
    return (
      <aside className="w-[300px] flex-none overflow-y-auto border-l border-line bg-gutter">
        <div className="px-3 py-4 text-[11px] italic text-dim">Select a shot to inspect it.</div>
      </aside>
    )
  }

  /** Shared truthfulness plumbing for every mutation in this panel: a
   *  non-2xx or network failure surfaces via the inline error banner above
   *  and does NOT refresh -- the server state didn't change, so there is
   *  nothing new to pull and the banner is what the user needs to see. A
   *  success clears the banner and re-fetches the authoritative project
   *  (mirrors `withRefresh` in App.tsx) so every field reflects what the
   *  backend actually persisted. Same "never paint success on a non-2xx"
   *  contract PromptEditor's `handleSave` enforces for the sibling shots
   *  endpoint -- factored out once three call sites in this panel
   *  (persistShot, updateGlobalSetting, setVoice) needed the identical
   *  check-then-refresh-or-surface shape. */
  const runMutation = async (request: Promise<ApiResult<unknown>>): Promise<boolean> => {
    const result = await request
    if (!result.ok) {
      setSaveError(result.error)
      return false
    }
    setSaveError(null)
    await onRefreshProject()
    return true
  }

  /** Returns whether the save landed, so callers that applied an optimistic
   *  local update (`updateField` below) can revert it on failure instead of
   *  leaving a value showing that the server never actually confirmed. */
  const persistShot = (next: ShotForm): Promise<boolean> =>
    runMutation(
      apiPut(`${base}/projects/${project.id}/shots/${shot.id}`, {
        prompt: assemblePromptSections(next.sections),
        target_api: next.targetApi,
        camera: next.camera,
        visual_effect: next.visualEffect,
        negative_constraints: next.negativeConstraints,
        continuity_constraints: next.continuityConstraints,
        intent_notes: next.intentNotes,
      }),
    )

  // Global-settings (project-level) writer — mirrors SettingsInspector's
  // `update(key, value)` contract (PUT /api/projects/{pid}, merge global_settings).
  // Was a sibling defect of persistShot's pre-fix shape: a raw `fetch` with
  // no `.ok` check that refreshed unconditionally, so a rejected write (the
  // pace wpm field, the identity-backend toggle) surfaced no error and was
  // indistinguishable from a success. Migrated onto apiPut + runMutation.
  const gs = project.global_settings as any
  const updateGlobalSetting = (key: string, value: unknown): Promise<boolean> =>
    runMutation(apiPut(`${base}/projects/${project.id}`, { global_settings: { ...gs, [key]: value } }))

  const primaryCharacter = project.characters.find((c) => c.id === shot.primary_character) ?? null
  // Same sibling defect as updateGlobalSetting above, on the character PUT
  // that backs the Voice pill.
  const setVoice = async (voiceId: string): Promise<boolean> => {
    if (!primaryCharacter) return false
    return runMutation(apiPut(`${base}/projects/${project.id}/characters/${primaryCharacter.id}`, { voice_id: voiceId }))
  }

  const updateSectionLocal = (tag: string, value: string) => {
    setForm((prev) => ({ ...prev, sections: { ...prev.sections, [tag]: value } }))
  }
  // Free-text fields: the operator's keystrokes already live in `form`
  // (updateSectionLocal/setForm above) independent of the network call, so
  // a failed commit surfaces the error but deliberately does NOT wipe what
  // they typed -- same "keep the edits intact, don't discard on failure"
  // behavior as PromptEditor's modal staying open on a rejected save.
  const commitSections = () => { void persistShot(form) }

  // Instant-commit controls (the API pill below): unlike free text, there
  // is no separate "unsaved draft" -- the pill's displayed value IS the
  // save target. Revert it on failure so a rejected change never sits
  // there looking saved (the literal "paints optimistic success on a
  // non-2xx" defect) -- `persistShot`'s own error banner explains why.
  const updateField = (patch: Partial<ShotForm>) => {
    const previous = form
    const next = { ...form, ...patch }
    setForm(next)
    void persistShot(next).then((ok) => {
      if (!ok) setForm(previous)
    })
  }

  const shotType = classifyShotType(shot)
  const template = getShotTemplate(shot, config)

  const engineOptions = videoEngines(config).map((e) => ({
    value: e.key,
    label: e.label,
    disabled: !e.selectable,
    title: e.reason ? humanizeEngineReason(e.reason) : undefined,
  }))
  // Defensive: the server always includes the project's persisted target_api
  // values as rows, but `config` may not be project-scoped yet (still
  // loading, or fetched without project_id) — keep the current value
  // representable rather than rendering a value-less select.
  if (form.targetApi && !engineOptions.some((o) => o.value === form.targetApi)) {
    engineOptions.unshift({ value: form.targetApi, label: form.targetApi, disabled: false, title: undefined })
  }

  const voiceOptions = (config?.voice_pool ?? []).map((v) => ({ value: v.id, label: `${v.name} — ${v.style}` }))

  const identityBackend: string = gs.identity_backend ?? 'gemini_multiref'
  const isPod = identityBackend === 'pod'
  const identityStrictness: number = gs.identity_strictness ?? 0.6
  const dialogueWpm: number = gs.dialogue_target_wpm ?? 145

  const perShotDuration =
    scene && scene.duration_seconds && (scene.shots?.length || scene.num_shots)
      ? scene.duration_seconds / (scene.shots?.length || scene.num_shots)
      : null

  return (
    <aside className="w-[300px] flex-none overflow-y-auto border-l border-line bg-gutter">
      {saveError && (
        <LiveRegion
          politeness="assertive"
          visuallyHidden={false}
          message={`Could not save: ${saveError}`}
          className="mx-3 mt-3 rounded border border-fail/50 bg-fail/10 px-3 py-2 text-[11px] text-fail"
        />
      )}
      <Section title="Prompt">
        <div className="space-y-3">
          {PROMPT_SECTION_TAGS.map((tag) => (
            <Field key={tag} label={tag}>
              <textarea
                value={form.sections[tag] || ''}
                onChange={(e) => updateSectionLocal(tag, e.target.value)}
                onBlur={commitSections}
                rows={tag === 'SCENE' ? 3 : 2}
                className={FIELD_CLS}
              />
            </Field>
          ))}
          <Field label="Negative constraints">
            <textarea
              value={form.negativeConstraints}
              onChange={(e) => setForm((prev) => ({ ...prev, negativeConstraints: e.target.value }))}
              onBlur={commitSections}
              rows={2}
              placeholder="What must never happen in this shot"
              className={FIELD_CLS}
            />
          </Field>
        </div>
      </Section>

      <Section title="Dialogue">
        <div className="space-y-3">
          <Field label="Line">
            <p className="text-[11px] leading-relaxed text-mut">{scene?.dialogue || '—'}</p>
          </Field>
          <Field label="Voice">
            {primaryCharacter ? (
              <SelectPill
                aria-label="Voice"
                value={primaryCharacter.voice_id || ''}
                options={voiceOptions.length ? voiceOptions : [{ value: primaryCharacter.voice_id || '', label: '—' }]}
                onChange={setVoice}
              />
            ) : (
              <span className="text-[11px] italic text-dim">No primary character on this shot.</span>
            )}
          </Field>
          <Field label="Pace (target wpm)">
            <input
              type="number"
              min={80}
              max={220}
              step={5}
              value={dialogueWpm}
              onChange={(e) => updateGlobalSetting('dialogue_target_wpm', parseFloat(e.target.value) || 0)}
              aria-label="Pace (target wpm)"
              className={`${FIELD_CLS} font-mono`}
            />
          </Field>
        </div>
      </Section>

      <Section title="Shot">
        <div className="space-y-3">
          <ReadOnlyRow label="Type" value={<span className="capitalize">{shotType}</span>} />
          <Field label="Primary API">
            <SelectPill aria-label="Primary API" value={form.targetApi} options={engineOptions} onChange={(v) => updateField({ targetApi: v })} />
          </Field>
          <ReadOnlyRow
            label="Duration"
            value={perShotDuration != null ? `~${perShotDuration.toFixed(1)}s` : '—'}
          />
        </div>
      </Section>

      <Section title="Identity">
        <div className="space-y-3">
          <ReadOnlyRow label="PuLID weight" value={template ? template.pulid_weight.toFixed(2) : '—'} />
          <ReadOnlyRow label="Threshold" value={identityStrictness.toFixed(2)} />
          <div className="flex items-start justify-between gap-3 border-t border-line pt-3">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-[11px] text-tx">
                <span>ComfyUI keyframe</span>
                <Badge variant="pod">Pod</Badge>
              </div>
              <p className="mt-1 text-[10px] leading-tight text-mut">
                Off = Nano Banana (cloud, Google-first default). On = this shot&apos;s keyframe renders through the pod
                FLUX + PuLID identity backend.
              </p>
            </div>
            <Toggle
              checked={isPod}
              onChange={(v) => updateGlobalSetting('identity_backend', v ? 'pod' : 'gemini_multiref')}
              aria-label="ComfyUI keyframe (pod)"
            />
          </div>
        </div>
      </Section>

      {shotState?.identity_score != null && (
        <div className="px-3 py-2 text-[10px] text-mut">Last identity score: {(shotState.identity_score * 100).toFixed(0)}%</div>
      )}
    </aside>
  )
}
