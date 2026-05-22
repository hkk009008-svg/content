import { SettingsSection } from './SettingsSection'
import type { AppConfig } from '../../types/project'

interface Props {
  s: any
  config: AppConfig | null
  update: (key: string, value: any) => void | Promise<void>
}

export function BudgetSection({ s, config, update }: Props) {
  return (
    <SettingsSection title="Budget & Cost">
      <div>
        <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">
          Budget Limit (USD)
        </label>
        <input
          type="number"
          min={0}
          step={1}
          value={s.budget_limit_usd ?? 0}
          onChange={e => update('budget_limit_usd', parseFloat(e.target.value) || 0)}
          placeholder="0 = no limit"
          className="w-full bg-editorial-ink border border-editorial-rule rounded-lg px-3 py-2 text-sm text-editorial-ivory font-mono"
        />
        <p className="text-eyebrow-sm text-editorial-ivory-mute mt-0.5">
          Max spend per video. 0 = unlimited. Pipeline pauses when limit reached.
        </p>
      </div>

      <div>
        <label className="text-eyebrow text-editorial-ivory-soft block mb-1.5 uppercase tracking-wider">
          Cost Optimization
        </label>
        <select
          value={s.cost_optimization || 'quality_first'}
          onChange={e => update('cost_optimization', e.target.value)}
          className="w-full bg-editorial-ink border border-editorial-rule rounded-lg px-3 py-2 text-sm text-editorial-ivory"
        >
          {(config as any)?.cost_optimization_levels?.map((opt: any) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          )) || (
            <>
              <option value="quality_first">Quality First</option>
              <option value="balanced">Balanced</option>
              <option value="budget_conscious">Budget Conscious</option>
            </>
          )}
        </select>
        <p className="text-eyebrow-sm text-editorial-ivory-mute mt-0.5">
          Quality First = best API always. Budget Conscious = cheapest passing API.
        </p>
      </div>
    </SettingsSection>
  )
}
