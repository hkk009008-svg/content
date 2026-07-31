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
          hint="Max spend per video. 0 = unlimited. Pipeline pauses at this cap (CostTracker gate)."
        />

        <CostEstimatorSection s={s} />
      </div>
    </Section>
  )
}
