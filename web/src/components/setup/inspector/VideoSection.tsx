import { Section, Badge, Toggle } from '../../ui'
import type { AppConfig } from '../../../types/project'
import { videoEngines } from '../../../lib/engines'
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
 * Video section — engine picker + cascade + post-processing.
 *
 * Engines come from `videoEngines(config)` (Task 7): the reconciled,
 * Google-first-ordered list with Sora/Runway/Hedra/AUTO already excluded and
 * GEMINI_OMNI marked primary. Each row's cloud-vs-pod badge is derived from
 * `isPodGated` — provider-keyed, so a future pod-billed video engine surfaces
 * ⚙ Pod without a code change here. Enable state writes the whole nested
 * `api_engines` object (settings write contract).
 */
export function VideoSection({ s, config, update }: Props) {
  const engines = videoEngines(config)
  const engineState = s.api_engines ?? {}

  const setEngineEnabled = (key: string, enabled: boolean) => {
    const current = s.api_engines ?? config?.api_engine_defaults ?? {}
    const existing = current[key] ?? config?.api_engine_defaults?.[key] ?? { enabled: true }
    update('api_engines', { ...current, [key]: { ...existing, enabled } })
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
            const cfg = engineState[e.key] ?? config?.api_engine_defaults?.[e.key] ?? { enabled: true }
            const enabled = cfg.enabled !== false
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
          value={s.cascade_retry_limit ?? 2}
          min={0}
          max={5}
          step={1}
          onChange={(v) => update('cascade_retry_limit', v)}
          hint="Full cascade retries before giving up. 0 = no retries, 2 = default."
        />

        <div className="space-y-3 border-t border-line pt-3">
          <SelectRow
            label="Color grade"
            value={s.color_grade_preset ?? 'warm_cinema'}
            options={COLOR_GRADE_PRESETS}
            onChange={(v) => update('color_grade_preset', v)}
            hint="Applied on final assembly. Auto-mapped from mood if unset."
          />

          <RangeRow
            label="Motion quality gate"
            value={s.motion_quality_threshold ?? 0.4}
            min={0}
            max={1}
            step={0.05}
            format={(v) => v.toFixed(2)}
            onChange={(v) => update('motion_quality_threshold', v)}
            hint="Min smoothness score to accept video. Below → auto RIFE or regenerate."
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
            hint="FAL PixVerse post-video face swap."
          />
        </div>
      </div>
    </Section>
  )
}
