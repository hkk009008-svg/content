import { Section, Badge } from '../../ui'
import type { AppConfig } from '../../../types/project'
import { RangeRow, SelectRow, ToggleRow } from './controls'

interface Props {
  s: any
  config: AppConfig | null
  update: (key: string, value: any) => void | Promise<void>
}

const SAMPLERS = [
  { value: 'dpmpp_2m', label: 'DPM++ 2M (default)' },
  { value: 'euler', label: 'Euler (fast, lower quality)' },
  { value: 'dpmpp_2m_sde', label: 'DPM++ 2M SDE (creative)' },
  { value: 'dpmpp_3m_sde', label: 'DPM++ 3M SDE' },
  { value: 'uni_pc', label: 'UniPC (fast convergence)' },
]

/**
 * Image / identity backend section.
 *
 * `identity_backend` selects who renders the keyframe + binds identity:
 *   - 'gemini_multiref' (DEFAULT) — Nano Banana, cloud, Google-first primary;
 *     binds identity via reference images (phase_c_assembly.py:218).
 *   - 'pod' — ComfyUI FLUX + PuLID on RunPod; opt-out, ⚙ pod-gated.
 * The sampler/steps only apply on the pod path, so they render only then.
 */
export function ImageSection({ s, update }: Props) {
  const backend: string = s.identity_backend ?? 'gemini_multiref'
  const isPod = backend === 'pod'

  return (
    <Section title="Image">
      <div className="space-y-3">
        {/* Nano Banana (cloud primary) row */}
        <div className="flex items-center justify-between gap-2 rounded border border-line bg-panel px-2 py-1.5">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <span className="truncate text-[11px] text-tx">Nano Banana (Gemini multi-ref)</span>
            <Badge variant="cloud">Cloud</Badge>
            {!isPod && <Badge variant="pri">Primary</Badge>}
          </div>
        </div>

        {/* ComfyUI FLUX + PuLID (pod) row */}
        <div className="flex items-center justify-between gap-2 rounded border border-line bg-panel px-2 py-1.5">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <span className="truncate text-[11px] text-tx">ComfyUI FLUX + PuLID</span>
            <Badge variant="pod">Pod</Badge>
            {isPod && <Badge variant="pri">Active</Badge>}
          </div>
        </div>

        <ToggleRow
          label="Use ComfyUI FLUX + PuLID (pod)"
          checked={isPod}
          onChange={(v) => update('identity_backend', v ? 'pod' : 'gemini_multiref')}
          hint="Off = Nano Banana (cloud, Google-first default). On = opt into the pod FLUX + PuLID identity backend."
        />

        {isPod && (
          <div className="space-y-3 border-t border-line pt-3">
            <SelectRow
              label="Sampler"
              value={s.comfyui_sampler ?? 'dpmpp_2m'}
              options={SAMPLERS}
              onChange={(v) => update('comfyui_sampler', v)}
              hint="ComfyUI sampler for the FLUX keyframe pass."
            />
            <RangeRow
              label="Sampling steps"
              value={s.comfyui_steps ?? 20}
              min={10}
              max={40}
              step={1}
              onChange={(v) => update('comfyui_steps', v)}
              hint="Higher = more detail but slower. 20 is balanced, 25+ for portraits."
            />
          </div>
        )}
      </div>
    </Section>
  )
}
