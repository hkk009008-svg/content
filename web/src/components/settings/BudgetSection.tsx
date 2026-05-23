import { SettingsSection } from './SettingsSection'

interface Props {
  s: any
  update: (key: string, value: any) => void | Promise<void>
}

export function BudgetSection({ s, update }: Props) {
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
          Max spend per video. 0 = unlimited. Pipeline pauses at this cap (CostTracker gate).
        </p>
      </div>
    </SettingsSection>
  )
}
