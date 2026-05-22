import { useEffect, useState } from 'react'
import type { Project, ShotState } from '../../types/project'

export interface TelemetryProps {
  project: Project
  shotStates: Map<string, Partial<ShotState>>
  failedShots: string[]
  isStreaming: boolean
  projectId: string | null
}

const SCORE_BINS = ['0–0.2', '0.2–0.4', '0.4–0.6', '0.6–0.8', '0.8–1.0']

function buildHistogram(shotStates: Map<string, Partial<ShotState>>): number[] {
  const bins = [0, 0, 0, 0, 0]
  for (const s of shotStates.values()) {
    const score = s.identity_score
    if (score == null) continue
    const idx = Math.min(4, Math.floor(score * 5))
    bins[idx]++
  }
  return bins
}

export default function Telemetry({ project, shotStates, failedShots, isStreaming, projectId }: TelemetryProps) {
  const [liveCost, setLiveCost] = useState<number | null>(null)

  // Live cost polling
  useEffect(() => {
    if (!isStreaming || !projectId) return
    const tick = async () => {
      try {
        const res = await fetch(`/api/projects/${projectId}/cost-live`)
        if (res.ok) {
          const data = await res.json()
          if (typeof data?.total_usd === 'number') setLiveCost(data.total_usd)
        }
      } catch { /* ignore */ }
    }
    tick()
    const id = setInterval(tick, 5000)
    return () => clearInterval(id)
  }, [isStreaming, projectId])

  const totalShots = project?.scenes?.reduce((sum, s) => sum + (s.shots?.length || 0), 0) || 0

  // Best-effort: find most-recent target_api
  let currentEngine: string | undefined
  for (const s of shotStates.values()) {
    if (s.target_api) currentEngine = s.target_api
  }

  const bins = buildHistogram(shotStates)
  const maxBin = Math.max(1, ...bins)

  return (
    <aside className="col-span-3 border-l border-console-rule px-4 py-6 bg-console-surface">
      <h2 className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute mb-3 font-console-mono">
        Telemetry
      </h2>
      <dl className="space-y-4 text-xs">
        <div>
          <dt className="text-console-ink-mute uppercase text-eyebrow-lg font-console-mono">Shots</dt>
          <dd className="mt-0.5 font-console-mono text-console-ink">
            {totalShots}
            {failedShots.length > 0 && (
              <span className="ml-2 text-console-accent font-normal">({failedShots.length} failed)</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-console-ink-mute uppercase text-eyebrow-lg font-console-mono">Engine</dt>
          <dd className="mt-0.5 font-console-mono text-console-gold">{currentEngine || '—'}</dd>
        </div>
        <div>
          <dt className="text-console-ink-mute uppercase text-eyebrow-lg mb-1 font-console-mono">Identity scores</dt>
          <dd className="flex items-end gap-1 h-10">
            {bins.map((count, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
                <div
                  className="w-full rounded-sm bg-console-gold/60"
                  style={{ height: `${Math.round((count / maxBin) * 32) + 2}px` }}
                  title={`${SCORE_BINS[i]}: ${count}`}
                />
              </div>
            ))}
          </dd>
          <div className="flex justify-between text-console-ink-mute mt-0.5 font-console-mono">
            <span>0</span><span>1</span>
          </div>
        </div>
        <div>
          <dt className="text-console-ink-mute uppercase text-eyebrow-lg font-console-mono">Live cost</dt>
          <dd className="mt-0.5 font-console-mono text-console-ink">
            {liveCost != null ? `$${liveCost.toFixed(4)}` : '—'}
          </dd>
        </div>
      </dl>
    </aside>
  )
}
