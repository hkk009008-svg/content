import { Section } from '../../ui'
import { RangeRow } from './controls'

interface Props {
  s: any
  update: (key: string, value: any) => void | Promise<void>
}

/**
 * Identity section — provider-neutral face validation, retry, and coherence.
 * Provider-specific image model controls belong to Image setup and are shown
 * only when that backend has a validated runtime contract.
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
      </div>
    </Section>
  )
}
