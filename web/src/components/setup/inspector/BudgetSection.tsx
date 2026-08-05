import { Section } from '../../ui'
import { CostEstimatorSection } from './CostEstimatorSection'
import { NumberRow } from './controls'

interface Props {
  s: any
  update: (key: string, value: any) => void | Promise<void>
}

/**
 * Budget section — the per-video spend cap (read by CostTracker as a gate) plus
 * the production-only cost-estimate sub-view (stripped of the retired max tier).
 */
export function BudgetSection({ s, update }: Props) {
  return (
    <Section title="Budget">
      <div className="space-y-3">
        <NumberRow
          label="Budget limit (USD)"
          value={s.budget_limit_usd ?? 0}
          min={0}
          step={1}
          placeholder="0 = unlimited"
          onChange={(v) => update('budget_limit_usd', v)}
          hint="Hard cap for charged spend plus active paid-job reservations. 0 = unlimited. Blocked submissions do not call the provider."
        />

        <CostEstimatorSection s={s} />
      </div>
    </Section>
  )
}
