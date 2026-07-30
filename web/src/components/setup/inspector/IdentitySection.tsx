import { Section, Badge } from '../../ui'
import { RangeRow, ToggleRow } from './controls'

interface Props {
  s: any
  update: (key: string, value: any) => void | Promise<void>
}

/**
 * Identity section — face-lock strictness, retry, adaptive PuLID, guidance,
 * coherence, active reference-based identity guidance, and the explicit
 * inactive/read-only LoRA policy.
 */
export function IdentitySection({ s, update }: Props) {
  return (
    <Section title="Identity">
      <div className="space-y-3">
        <RangeRow
          label="Identity strictness"
          value={s.identity_strictness ?? 0.6}
          min={0}
          max={1}
          step={0.05}
          format={(v) => v.toFixed(2)}
          onChange={(v) => update('identity_strictness', v)}
          hint="Below this score → recommends face-swap. Higher = stricter face matching."
        />

        <RangeRow
          label="Identity retry max"
          value={s.identity_retry_max ?? 3}
          min={1}
          max={5}
          step={1}
          onChange={(v) => update('identity_retry_max', v)}
          hint="Max video regeneration attempts when face identity fails."
        />

        <ToggleRow
          label="Adaptive PuLID"
          checked={s.adaptive_pulid !== false}
          onChange={(v) => update('adaptive_pulid', v)}
          hint="Auto-adjust face-lock strength from rolling identity scores. Off = shot-type defaults."
        />

        <RangeRow
          label="FLUX guidance scale"
          value={s.flux_guidance ?? 3.5}
          min={2.0}
          max={5.0}
          step={0.1}
          format={(v) => v.toFixed(1)}
          onChange={(v) => update('flux_guidance', v)}
          hint="Prompt adherence. 3.5 = FLUX sweet spot. Higher = stricter but risks oversaturation."
        />

        <RangeRow
          label="Coherence threshold"
          value={s.coherence_threshold ?? 0.6}
          min={0.3}
          max={1.0}
          step={0.05}
          format={(v) => v.toFixed(2)}
          onChange={(v) => update('coherence_threshold', v)}
          hint="Min scene coherence score to accept. Below → mutation retry."
        />

        {/* LoRA is policy-inactive; reference conditioning is the active path. */}
        <div className="space-y-1.5 border-t border-line pt-3">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-tx">Per-character LoRA</span>
            <Badge variant="neutral">Inactive</Badge>
          </div>
          <p className="text-[10px] leading-tight text-mut">
            Training, registration, and production use are unavailable. Historical records are read-only.
          </p>
          <p className="text-[10px] leading-tight text-dim">
            Use clear reference images for the active identity path: Gemini multi-reference first,
            with PuLID reference conditioning on the ComfyUI fallback.
          </p>
        </div>
      </div>
    </Section>
  )
}
