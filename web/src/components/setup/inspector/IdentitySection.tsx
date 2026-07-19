import { Section, Badge } from '../../ui'
import type { Project } from '../../../types/project'
import { RangeRow, ToggleRow } from './controls'

interface Props {
  s: any
  project: Project
  update: (key: string, value: any) => void | Promise<void>
}

/**
 * Identity section — face-lock strictness, retry, adaptive PuLID, guidance,
 * coherence, plus a read-only surface of the pod-gated per-character LoRA
 * training flag (the actual LoRA path/upload UI lives in CharacterPanel).
 */
export function IdentitySection({ s, project, update }: Props) {
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

        {/* Per-character LoRA training — pod-gated flag + pointer to CharacterPanel. */}
        <div className="space-y-1.5 border-t border-line pt-3">
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-tx">Per-character LoRA training</span>
            <Badge variant="pod">Pod</Badge>
          </div>
          <p className="text-[10px] leading-tight text-mut">
            Trained per character on the RunPod GPU. Assign a LoRA in the Character panel — it binds a
            secondary character PuLID alone can&apos;t hold.
          </p>
          {project.characters.length === 0 ? (
            <p className="text-[10px] italic text-dim">No characters yet.</p>
          ) : (
            <div className="flex flex-wrap gap-1">
              {project.characters.map((c) => (
                <span
                  key={c.id}
                  className="rounded border border-line bg-panel px-1.5 py-0.5 text-[10px] text-mut"
                >
                  {c.name}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </Section>
  )
}
