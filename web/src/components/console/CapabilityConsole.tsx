import { useEffect, useState } from 'react'
import type { Project, CapabilityScorecard } from '../../types/project'

interface Props { project: Project | null; onBack: () => void }

export default function CapabilityConsole({ project, onBack }: Props) {
  const projectId = project?.id || null
  const [sc, setSc] = useState<CapabilityScorecard | null>(null)
  const [state, setState] = useState<'loading'|'ready'|'empty'|'error'>('loading')

  const load = () => {
    if (!projectId) { setState('empty'); return }
    setState('loading')
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`/api/projects/${projectId}/capability-scorecard`)
        if (!res.ok) throw new Error(String(res.status))
        const data: CapabilityScorecard = await res.json()
        if (cancelled) return
        setSc(data)
        setState(data.summary.shots_total === 0 ? 'empty' : 'ready')
      } catch { if (!cancelled) setState('error') }
    })()
    return () => { cancelled = true }
  }
  useEffect(load, [projectId])  // eslint-disable-line react-hooks/exhaustive-deps

  const Label = ({ children }: { children: React.ReactNode }) =>
    <div className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute font-console-mono">{children}</div>

  return (
    <div className="min-h-screen bg-console-bg text-console-ink">
      <header className="border-b border-console-rule px-6 py-4 flex items-center justify-between">
        <div>
          <button onClick={onBack} className="text-eyebrow-lg uppercase tracking-wider text-console-ink-mute hover:text-console-gold font-console-mono">← Back to setup</button>
          <h1 className="mt-1 text-2xl font-display text-console-gold">
            {project?.name || 'No project'}<span className="ml-2 text-sm font-normal text-console-ink-dim font-console-mono">· Capability</span>
          </h1>
        </div>
        <div className="text-right text-xs font-console-mono text-console-ink-dim">
          {sc && <span><span className="bg-console-gold text-black px-2 rounded">{sc.tier.toUpperCase()}</span> · {sc.summary.shots_clearing_all_bars}/{sc.summary.shots_total} clear all bars</span>}
          <button onClick={load} className="ml-3 text-console-ink-mute hover:text-console-gold">↻ refresh</button>
        </div>
      </header>

      {state === 'loading' && <div className="p-8 text-console-ink-mute font-console-mono">Loading capability data…</div>}
      {state === 'error' && <div className="p-8 text-console-accent font-console-mono">Could not load the scorecard. <button onClick={load} className="underline">Retry</button></div>}
      {state === 'empty' && <div className="p-8 text-console-ink-mute font-console-mono">No capability data yet — run the pipeline to populate scores.</div>}
      {state === 'ready' && sc && (
        <div className="px-6 py-6 space-y-6">
          {/* sections added in Chunk 3; pass `sc` down */}
          <Label>Capability scorecard</Label>
        </div>
      )}
    </div>
  )
}
