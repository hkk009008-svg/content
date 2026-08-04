import { Section, Badge, Toggle } from '../../ui'
import type { AppConfig } from '../../../types/project'
import { cascadeEngineOptions, humanizeEngineReason } from '../../../lib/engines'
import { isPodGated } from '../../../lib/podGating'
import { RangeRow, ToggleRow, SelectRow } from './controls'

interface Props {
  s: any
  config: AppConfig | null
  update: (key: string, value: any) => void | Promise<void>
}

const COLOR_GRADE_PRESETS = [
  { value: 'warm_cinema', label: 'Warm Cinema' },
  { value: 'cool_noir', label: 'Cool Noir' },
  { value: 'vibrant', label: 'Vibrant' },
  { value: 'desaturated', label: 'Desaturated' },
  { value: 'golden_hour', label: 'Golden Hour' },
  { value: 'moonlight', label: 'Moonlight' },
  { value: 'high_contrast', label: 'High Contrast' },
  { value: 'pastel', label: 'Pastel' },
]

/**
 * Video section — engine cascade toggles + post-processing.
 *
 * Engines come from `cascadeEngineOptions(config)` — a cascade
 * PARTICIPATION list (which dispatchable engines the project's video
 * cascade may try), distinct from the shot-level picker view
 * (`videoEngines(config)`). Retention here is keyed on `can_configure`
 * (product-configurable), NOT `can_select`: `can_select` folds in this
 * project's own disable state, so keying retention on it would make
 * disabling a not-yet-in-use engine delete its row — and therefore its
 * toggle — with no way to re-enable it. `AUTO` is excluded (a routing
 * directive, not a dispatchable engine you toggle on/off). The primary badge
 * follows the server-provided workflow templates. Each row's cloud-vs-pod badge is derived from
 * `isPodGated` — provider-keyed, so a future pod-billed video engine
 * surfaces ⚙ Pod without a code change here. Enable state writes the whole
 * nested `api_engines` object (settings write contract), with the touched
 * engine's entry narrowed to the only live automatic-cascade field:
 * `enabled`.
 */
export function VideoSection({ s, config, update }: Props) {
  const engines = cascadeEngineOptions(config)
  const engineState = s.api_engines ?? {}

  // Enable/disable is the only per-engine write path. Rebuild the touched
  // entry from the one field automatic routing reads rather than spreading a
  // possibly stale compatibility entry wholesale. Deprecated explicit-only
  // engines never reach this list because the server marks them
  // can_configure=false; their sibling JSON remains untouched.
  const setEngineEnabled = (key: string, enabled: boolean) => {
    update('api_engines', (queued: typeof engineState | undefined) => ({
      ...(queued ?? s.api_engines ?? config?.api_engine_defaults ?? {}),
      [key]: { enabled },
    }))
  }

  const sceneTransitions = s.scene_transitions === true
  const coherenceOn = s.coherence_check_enabled !== false

  return (
    <Section title="Video">
      <div className="space-y-3">
        <div className="space-y-1.5">
          {engines.length === 0 && (
            <p className="text-[11px] italic text-mut">No video engines available.</p>
          )}
          {engines.map((e) => {
            const pod = isPodGated(e.key, config)
            const localCfg = engineState[e.key]
            const enabled = localCfg ? localCfg.enabled !== false : e.configuredEnabled
            return (
              <div
                key={e.key}
                data-testid="video-engine-row"
                data-engine-key={e.key}
                className="flex items-center justify-between gap-2 rounded border border-line bg-panel px-2 py-1.5"
              >
                <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                  <span className="truncate text-[11px] text-tx">{e.label}</span>
                  <Badge variant={pod ? 'pod' : 'cloud'}>{pod ? 'Pod' : 'Cloud'}</Badge>
                  {e.primary && <Badge variant="pri">Primary</Badge>}
                  {!e.selectable && e.reason && (
                    <Badge variant="warn" className="normal-case">
                      {humanizeEngineReason(e.reason)}
                    </Badge>
                  )}
                </div>
                <Toggle
                  checked={enabled}
                  onChange={(v) => setEngineEnabled(e.key, v)}
                  aria-label={`Enable ${e.label}`}
                />
              </div>
            )
          })}
        </div>

        <RangeRow
          label="Cascade retry limit"
          value={s.cascade_retry_limit ?? 1}
          min={0}
          max={5}
          step={1}
          onChange={(v) => update('cascade_retry_limit', v)}
          hint="Full cascade retries before giving up. 0 = no retries, 1 = default (phase_c_ffmpeg.py MAX_CASCADE_RETRIES)."
        />

        <ToggleRow
          label="Native dialogue audio"
          checked={s.dialogue_voice_mode === 'native'}
          onChange={(v) => update('dialogue_voice_mode', v ? 'native' : 'overlay')}
          hint="Requests embedded dialogue only when Veo runs through Vertex AI with ADC. The Veo Developer API and other routes use the F1b TTS/lip-sync overlay. Native audio without measured lip-sync is UNKNOWN and requires review."
        />

        <div className="space-y-3 border-t border-line pt-3">
          <SelectRow
            label="Color grade"
            value={s.color_grade_preset ?? 'warm_cinema'}
            options={COLOR_GRADE_PRESETS}
            onChange={(v) => update('color_grade_preset', v)}
            hint="Used by the manual per-clip Color Grade correction. Automatic final-assembly grading currently keys off mood only, not this value (tracked gap — cinema_pipeline.py)."
          />

          <RangeRow
            label="Motion quality gate"
            value={s.motion_quality_threshold ?? 0.5}
            min={0}
            max={1}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(v) => update('motion_quality_threshold', v)}
            hint="Overrides the per-shot-type motion-fidelity floor for performance-capture-driven takes only (defaults: portrait 0.42 / medium 0.55 / action 0.60 / wide 0.65). Below floor → take flagged for regeneration."
          />

          <ToggleRow
            label="Coherence analysis"
            checked={coherenceOn}
            onChange={(v) => update('coherence_check_enabled', v)}
            hint="Color / lighting / composition consistency between shots."
          />

          {coherenceOn && (
            <RangeRow
              label="Color drift sensitivity"
              value={s.color_drift_sensitivity ?? 0.3}
              min={0.1}
              max={0.5}
              step={0.05}
              format={(v) => v.toFixed(2)}
              onChange={(v) => update('color_drift_sensitivity', v)}
              hint="Max color-histogram drift before prompt adjustment. Lower = stricter."
            />
          )}

          <ToggleRow
            label="Scene transitions"
            checked={sceneTransitions}
            onChange={(v) => update('scene_transitions', v)}
            hint="Cross-dissolve between scenes (re-encodes on assembly)."
          />

          {sceneTransitions && (
            <RangeRow
              label="Transition duration (s)"
              value={s.transition_duration ?? 0.5}
              min={0.2}
              max={2.0}
              step={0.1}
              format={(v) => v.toFixed(1)}
              onChange={(v) => update('transition_duration', v)}
              hint="Length of the cross-dissolve in seconds."
            />
          )}

          <ToggleRow
            label="Face swap"
            checked={s.face_swap_enabled === true}
            onChange={(v) => update('face_swap_enabled', v)}
            hint="FAL PixVerse / FaceFusion post-video face swap — a billed per-clip correction. Off by default."
          />
        </div>
      </div>
    </Section>
  )
}
