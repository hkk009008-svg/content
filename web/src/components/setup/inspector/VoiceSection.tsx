import { useEffect, useRef, useState } from 'react'
import { Section } from '../../ui'
import type { AppConfig } from '../../../types/project'
import { LipsyncPriorityList } from './LipsyncPriorityList'
import { apiPost } from '../../../lib/api'
import { RangeRow, SelectRow, ToggleRow, NumberRow } from './controls'

interface Props {
  s: any
  config: AppConfig | null
  update: (key: string, value: any) => void | Promise<void>
  /** Needed to invoke the per-project language-defaults contract below.
   *  Optional so existing shape-based tests that don't exercise that path
   *  can keep rendering without it. */
  projectId?: string
  onRefresh?: () => void
}

interface ApplyLanguageDefaultsResponse {
  language: string
  changed_fields: string[]
  applied_defaults: Record<string, unknown>
  recommended_voices: { male?: string; female?: string; available_count: number }
}

// ElevenLabs voice defaults per the brief — Eric (male) / Lily (female).
const ERIC_VOICE_ID = 'cjVigY5qzO86Huf0OWal'
const LILY_VOICE_ID = 'pFZP5JQG7iQjIQuC4Bku'

const LIP_SYNC_MODES = [
  { value: 'auto', label: 'Auto — AI picks by shot type + dialogue length' },
  { value: 'overlay', label: 'Overlay (MuseTalk) — replaces mouth only' },
  { value: 'generation', label: 'Generation (Omnihuman) — full talking head' },
  { value: 'skip', label: 'Skip — no lip sync' },
]

const MUSIC_MASTERING = [
  { value: 'none', label: 'None — raw, unmastered' },
  { value: 'cinema_master', label: 'Cinema Master — warm, wide, polished' },
  { value: 'lo_fi', label: 'Lo-Fi — vinyl warmth, tape hiss' },
  { value: 'epic_wide', label: 'Epic Wide — orchestral, boosted lows' },
  { value: 'intimate_acoustic', label: 'Intimate Acoustic — close, minimal' },
  { value: 'dark_ambient', label: 'Dark Ambient — deep, spacious' },
]

/**
 * Voice section — TTS provider + default male/female voices, dialogue-quality
 * enhancers, the reorderable lipsync cascade ([LipsyncPriorityList]), the
 * SyncNet validation gate, and dialogue pace.
 *
 * Pace is a target-WPM number (`dialogue_target_wpm`), applied via atempo
 * post-process — NOT a `speed` field, because eleven_v3 ignores speed.
 *
 * Language change also invokes the language-defaults contract
 * (`POST /api/projects/<id>/apply-language-defaults`, backed by
 * domain/language_defaults.py) — every field it can seed (tts_provider,
 * dialogue_mode_enabled, forced_alignment_enabled, lipsync_engine_priority,
 * lipsync_quality_validation, lipsync_validation_threshold) lives in this
 * section, so this is where the applied/changed-fields result surfaces.
 */
export function VoiceSection({ s, config, update, projectId, onRefresh }: Props) {
  const ttsOptions = config?.api_registry
    ? Object.entries(config.api_registry)
        .filter(([, info]) => info.modality === 'tts')
        .map(([key, info]) => ({ value: key, label: info.label }))
    : [{ value: 'ELEVENLABS_V3', label: 'ElevenLabs v3' }]

  const voiceOptions = (config?.voice_pool ?? []).map((v) => ({
    value: v.id,
    label: `${v.name} — ${v.style}`,
  }))
  const maleVoiceOptions = voiceOptions.length
    ? voiceOptions
    : [{ value: ERIC_VOICE_ID, label: 'Eric' }]
  const femaleVoiceOptions = voiceOptions.length
    ? voiceOptions
    : [{ value: LILY_VOICE_ID, label: 'Lily' }]

  const validationOn = s.lipsync_quality_validation !== false

  // Apply per-language optimized defaults whenever the project's language
  // actually CHANGES (not on initial mount/every unrelated refresh — the ref
  // starts at the first-seen value, so the first effect run always sees
  // prev === next and skips). Non-destructive: overwrite_existing defaults
  // to false server-side, so a field the operator already customized is
  // left alone; only unset fields get seeded.
  const prevLanguageRef = useRef<string | undefined>(s.language)
  const [langNotice, setLangNotice] = useState<
    { language: string; changed: string[] } | { error: string } | null
  >(null)

  useEffect(() => {
    const prev = prevLanguageRef.current
    const next = s.language
    prevLanguageRef.current = next
    if (!next || prev === next || !projectId) return

    let cancelled = false
    apiPost<ApplyLanguageDefaultsResponse>(`/api/projects/${projectId}/apply-language-defaults`, {
      language: next,
    }).then((result) => {
      if (cancelled) return
      if (result.ok) {
        setLangNotice({ language: result.data.language, changed: result.data.changed_fields })
        if (result.data.changed_fields.length) onRefresh?.()
      } else {
        setLangNotice({ error: result.error })
      }
    })
    return () => {
      cancelled = true
    }
  }, [s.language, projectId, onRefresh])

  return (
    <Section title="Voice">
      <div className="space-y-3">
        {langNotice && 'error' in langNotice && (
          // Message body in `text-tx` (not `text-fail`): the fail token
          // measures ~4.2-4.4:1 on this column's backgrounds, under WCAG
          // AA's 4.5:1 floor for 10px text (slice 13b contrast audit).
          // Mirrors ErrorState's own convention -- a short fail-colored
          // label, full-contrast message -- rather than coloring the whole
          // line.
          <p role="alert" className="text-[10px] leading-tight text-tx">
            <span className="text-fail">Couldn't apply language defaults:</span> {langNotice.error}
          </p>
        )}
        {langNotice && 'changed' in langNotice && (
          <p className="text-[10px] leading-tight text-ok">
            {langNotice.changed.length
              ? `Applied ${langNotice.language} voice/lipsync defaults — changed: ${langNotice.changed.join(', ')}`
              : `${langNotice.language} defaults already match — nothing to change.`}
          </p>
        )}

        <SelectRow
          label="Dialogue TTS provider"
          value={s.tts_provider ?? 'ELEVENLABS_V3'}
          options={ttsOptions}
          onChange={(v) => update('tts_provider', v)}
          hint="Active TTS engine for dialogue + narration."
        />

        <SelectRow
          label="Default male voice"
          value={s.default_male_voice ?? ERIC_VOICE_ID}
          options={maleVoiceOptions}
          onChange={(v) => update('default_male_voice', v)}
        />

        <SelectRow
          label="Default female voice"
          value={s.default_female_voice ?? LILY_VOICE_ID}
          options={femaleVoiceOptions}
          onChange={(v) => update('default_female_voice', v)}
        />

        <div className="space-y-3 border-t border-line pt-3">
          <ToggleRow
            label="ElevenLabs dialogue mode"
            checked={s.dialogue_mode_enabled !== false}
            onChange={(v) => update('dialogue_mode_enabled', v)}
            hint="Route multi-line dialogue through the dedicated endpoint — natural turn-taking + prosody continuity."
          />
          <ToggleRow
            label="Forced alignment (WhisperX)"
            checked={s.forced_alignment_enabled !== false}
            onChange={(v) => update('forced_alignment_enabled', v)}
            hint="Word-level timestamps + DTW correction. Lipsync accuracy ↑↑."
          />
        </div>

        <div className="space-y-2 border-t border-line pt-3">
          <SelectRow
            label="Lip sync mode"
            value={s.lip_sync_mode ?? 'auto'}
            options={LIP_SYNC_MODES}
            onChange={(v) => update('lip_sync_mode', v)}
          />

          <div>
            <span className="mb-1 block font-mono text-[10px] uppercase tracking-[0.09em] text-mut">
              Lipsync engine priority
            </span>
            <div className="space-y-1 rounded border border-line bg-panel p-1.5">
              <LipsyncPriorityList s={s} config={config} update={update} />
            </div>
            <p className="mt-1 text-[10px] leading-tight text-mut">
              Reordering is saved but not yet read by the overlay/generation
              cascades — each still tries its own fixed engine order
              (lip_sync.py). Kept here as a staged preference for that wiring.
            </p>
          </div>

          <ToggleRow
            label="Lipsync quality gate (SyncNet)"
            checked={validationOn}
            onChange={(v) => update('lipsync_quality_validation', v)}
            hint="Score lipsync output via SyncNet. Below threshold → escalate to the next engine."
          />
          {validationOn && (
            <RangeRow
              label="SyncNet confidence threshold"
              value={s.lipsync_validation_threshold ?? 0.65}
              min={0.3}
              max={0.95}
              step={0.05}
              format={(v) => v.toFixed(2)}
              onChange={(v) => update('lipsync_validation_threshold', v)}
              hint='0.65 = "convincing in-context"; 0.85+ = "passes close-up scrutiny".'
            />
          )}
        </div>

        <div className="space-y-3 border-t border-line pt-3">
          <NumberRow
            label="Dialogue pace (target WPM)"
            value={s.dialogue_target_wpm ?? 145}
            min={80}
            max={220}
            step={5}
            onChange={(v) => update('dialogue_target_wpm', v)}
            hint="Target words-per-minute — measured against the assembled line(s) and applied via an atempo post-process (eleven_v3 ignores speed). 0 disables pacing."
          />

          <SelectRow
            label="Music mastering"
            value={s.music_mastering ?? 'cinema_master'}
            options={MUSIC_MASTERING}
            onChange={(v) => update('music_mastering', v)}
          />
        </div>
      </div>
    </Section>
  )
}
