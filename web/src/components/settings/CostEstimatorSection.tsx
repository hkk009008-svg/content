import { useEffect, useState, type ReactNode } from 'react'
import { SettingsSection } from './SettingsSection'

const API = '/api'

interface Props {
  s: any
}

export function CostEstimatorSection({ s }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [costEstimate, setCostEstimate] = useState<any>(null)
  const [costShotCount, setCostShotCount] = useState(60)
  const [costDialogueRatio, setCostDialogueRatio] = useState(0.5)

  const isMaxTier = (s.quality_tier || 'production') === 'max'

  useEffect(() => {
    if (!expanded) return
    const body = {
      shot_count: costShotCount,
      has_dialogue: costDialogueRatio > 0,
      dialogue_shot_ratio: costDialogueRatio,
      quality_tier: isMaxTier ? 'max' : 'production',
      candidate_count: isMaxTier ? (s.max_candidate_count ?? 8) : 1,
    }
    fetch(`${API}/cost-estimate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(r => (r.ok ? r.json() : null))
      .then(setCostEstimate)
      .catch(() => setCostEstimate(null))
  }, [expanded, costShotCount, costDialogueRatio, isMaxTier, s.max_candidate_count])

  const titleNode: ReactNode = (
    <h2 className="text-eyebrow-lg font-semibold uppercase tracking-widest flex items-center gap-2">
      <span className="text-editorial-brass">Cost Estimator</span>
      {costEstimate && (
        <span className="text-eyebrow-sm font-mono bg-editorial-brass/20 text-editorial-brass px-1.5 py-0.5 rounded">
          ${costEstimate.totals?.grand_total?.toFixed(2)}
        </span>
      )}
    </h2>
  )

  return (
    <SettingsSection
      titleNode={titleNode}
      expanded={expanded}
      onToggle={setExpanded}
    >
      {/* Sliders */}
      <div>
        <div className="flex justify-between text-eyebrow text-editorial-ivory-mute mb-0.5">
          <span className="font-mono">Shot count</span>
          <span className="text-editorial-brass font-bold">{costShotCount}</span>
        </div>
        <input type="range" min={5} max={120} step={5}
          value={costShotCount}
          onChange={e => setCostShotCount(parseInt(e.target.value))}
          aria-label="Shot count"
          className="w-full accent-editorial-brass h-1" />
      </div>
      <div>
        <div className="flex justify-between text-eyebrow text-editorial-ivory-mute mb-0.5">
          <span className="font-mono">Dialogue shot ratio</span>
          <span className="text-editorial-brass font-bold">{(costDialogueRatio * 100).toFixed(0)}%</span>
        </div>
        <input type="range" min={0} max={1} step={0.05}
          value={costDialogueRatio}
          onChange={e => setCostDialogueRatio(parseFloat(e.target.value))}
          aria-label="Dialogue shot ratio"
          className="w-full accent-editorial-brass h-1" />
        <p className="text-eyebrow-sm text-editorial-ivory-mute">Fraction of shots with spoken dialogue (drives TTS + lipsync cost).</p>
      </div>

      {/* Breakdown */}
      {costEstimate && (
        <>
          <div className="rounded-lg border border-editorial-brass/20 bg-editorial-brass/5 p-3">
            <div className="text-eyebrow text-editorial-ivory-mute uppercase tracking-wider mb-1">Total ({costEstimate.quality_tier})</div>
            <div className="text-2xl font-bold text-editorial-brass">${costEstimate.totals?.grand_total?.toFixed(2)}</div>
            <div className="text-eyebrow text-editorial-ivory-mute mt-0.5">
              ${costEstimate.per_shot?.avg?.toFixed(3)}/shot avg · {costEstimate.shot_count} shots ({costEstimate.dialogue_shots} dialogue)
            </div>
          </div>

          <div className="rounded-lg border border-editorial-rule bg-editorial-ink overflow-hidden">
            <div className="text-eyebrow text-editorial-ivory-soft uppercase tracking-wider px-3 py-2 border-b border-editorial-rule">By modality</div>
            <table className="w-full text-eyebrow">
              <tbody>
                {Object.entries(costEstimate.totals).filter(([k]) => k !== 'grand_total').map(([k, v]: any) => (
                  <tr key={k} className="border-b border-editorial-rule/30 last:border-0">
                    <td className="px-3 py-1.5 text-editorial-ivory-mute font-mono">{k.replace(/_/g, ' ')}</td>
                    <td className="px-3 py-1.5 text-right text-editorial-ivory font-mono">${v.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="rounded-lg border border-editorial-rule bg-editorial-ink overflow-hidden">
            <div className="text-eyebrow text-editorial-ivory-soft uppercase tracking-wider px-3 py-2 border-b border-editorial-rule">By billing provider</div>
            <table className="w-full text-eyebrow">
              <tbody>
                {Object.entries(costEstimate.by_provider).map(([k, v]: any) => (
                  <tr key={k} className="border-b border-editorial-rule/30 last:border-0">
                    <td className="px-3 py-1.5 text-editorial-ivory-mute font-mono">{k}</td>
                    <td className="px-3 py-1.5 text-right text-editorial-ivory font-mono">${v.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {costEstimate.notes && costEstimate.notes.length > 0 && (
            <ul className="text-eyebrow-sm text-editorial-ivory-mute space-y-0.5 list-disc pl-4">
              {costEstimate.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}
            </ul>
          )}
        </>
      )}
      {!costEstimate && (
        <p className="text-eyebrow text-editorial-ivory-mute italic">Loading estimate…</p>
      )}
    </SettingsSection>
  )
}
