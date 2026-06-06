import { useEffect, useState } from 'react'
import type { Project, CapabilityScorecard, CapabilityDimension } from '../../types/project'

interface Props { project: Project | null; onBack: () => void }

// ── Color helpers ────────────────────────────────────────────────────────────

/** Returns a Tailwind class for a measured value vs its bar.
 *  null value → muted; no bar → neutral ink; pass → green; fail → accent. */
function scoreClass(value: number | null, bar: number | null): string {
  if (value === null) return 'text-console-ink-mute'
  if (bar === null) return 'text-console-ink'
  return value >= bar ? 'text-[#7fd17f]' : 'text-console-accent'
}

function verdictClass(verdict: 'ok' | 'warning' | 'rejected'): string {
  if (verdict === 'ok') return 'text-[#7fd17f]'
  if (verdict === 'warning') return 'text-[#e0b94e]'
  return 'text-console-accent'
}

function statusClass(status: string): string {
  if (status === 'live' || status === 'wired') return 'text-[#7fd17f]'
  if (status === 'stubbed' || status === 'parked') return 'text-[#e0b94e]'
  return 'text-console-ink-mute'
}

function fmt(v: number | null): string {
  if (v === null) return '—'
  return v.toFixed(2)
}

// ── Section: Scorecard dimension grid (Task 5) ───────────────────────────────

function ScorecardGrid({ sc }: { sc: CapabilityScorecard }) {
  return (
    <div>
      <div className="grid grid-cols-4 gap-2">
        {sc.dimensions.map((d: CapabilityDimension) => (
          <div key={d.key} className="border border-console-rule rounded p-2 font-console-mono text-xs">
            <div className="text-console-ink-mute uppercase tracking-wider mb-1">{d.label}</div>
            <div className={`text-lg font-bold ${scoreClass(d.value, d.bar)}`}>
              {d.value !== null ? d.value.toFixed(2) : '— not measured'}
              {d.value !== null && d.bar !== null && (
                <span className="text-xs font-normal text-console-ink-mute ml-1">/ {d.bar.toFixed(2)}</span>
              )}
            </div>
            {/* Mini progress bar */}
            <div className="mt-1 h-1 bg-console-rule rounded overflow-hidden">
              <div
                className={`h-full rounded ${d.value !== null && d.bar !== null && d.value >= d.bar ? 'bg-[#7fd17f]' : d.value !== null ? 'bg-console-accent' : 'bg-console-rule'}`}
                style={{ width: `${Math.min((d.value ?? 0) * 100, 100)}%` }}
              />
            </div>
            <div className="mt-1 text-console-ink-mute">
              {d.n_measured} shot{d.n_measured !== 1 ? 's' : ''} measured
            </div>
          </div>
        ))}
      </div>

      {/* Future dimensions — greyed / dashed */}
      {sc.future_dimensions.length > 0 && (
        <div className="mt-2 grid grid-cols-4 gap-2">
          {sc.future_dimensions.map((fd: string) => (
            <div key={fd} className="border border-dashed border-console-rule rounded p-2 opacity-40 font-console-mono text-xs">
              <div className="text-console-ink-mute uppercase tracking-wider">{fd.replace(/_/g, ' ')}</div>
              <div className="text-console-ink-mute mt-1">— not yet measured</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Section: Per-shot scores table (Task 6) ──────────────────────────────────

function PerShotTable({ sc }: { sc: CapabilityScorecard }) {
  if (sc.per_shot.length === 0) return null

  const barFor = (key: string): number | null =>
    sc.dimensions.find((d: CapabilityDimension) => d.key === key)?.bar ?? null

  const identityBar = barFor('identity')
  const coherenceBar = barFor('coherence')
  const motionBar = barFor('motion')
  const lipsyncBar = barFor('lipsync')

  return (
    <div className="overflow-x-auto">
      <table className="w-full font-console-mono text-xs border-collapse">
        <thead>
          <tr className="border-b border-console-rule text-console-ink-mute uppercase tracking-wider">
            <th className="text-left py-1 pr-3">Shot</th>
            <th className="text-right py-1 px-2">Identity</th>
            <th className="text-right py-1 px-2">Coherence</th>
            <th className="text-right py-1 px-2">Motion</th>
            <th className="text-right py-1 px-2">Lipsync</th>
            <th className="text-left py-1 pl-3">Engine</th>
          </tr>
        </thead>
        <tbody>
          {sc.per_shot.map((row) => (
            <tr key={row.shot_id} className="border-b border-console-rule hover:bg-console-rule/20">
              <td className="py-1 pr-3 text-console-ink-dim">{row.shot_id}</td>
              <td className={`text-right py-1 px-2 ${scoreClass(row.identity, identityBar)}`}>{fmt(row.identity)}</td>
              <td className={`text-right py-1 px-2 ${scoreClass(row.coherence, coherenceBar)}`}>{fmt(row.coherence)}</td>
              <td className={`text-right py-1 px-2 ${scoreClass(row.motion, motionBar)}`}>{fmt(row.motion)}</td>
              <td className={`text-right py-1 px-2 ${scoreClass(row.lipsync, lipsyncBar)}`}>{fmt(row.lipsync)}</td>
              <td className="py-1 pl-3 text-console-ink-dim">{row.engine || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Section: Cascade provenance (Task 6 / U8) ────────────────────────────────

function CascadeProvenance({ sc }: { sc: CapabilityScorecard }) {
  if (sc.provenance.length === 0) return null

  const hasFallbacks = sc.provenance.some((r) => r.fallback || r.attempts.length > 1)

  return (
    <div className="font-console-mono text-xs space-y-1">
      {sc.provenance.map((row) => {
        const showChain = row.fallback || row.attempts.length > 1
        return (
          <div key={row.shot_id} className="flex flex-wrap items-center gap-2 py-0.5 border-b border-console-rule/40">
            <span className="text-console-ink-dim">{row.shot_id}</span>
            <span className="text-console-ink-mute">·</span>
            <span className="text-console-ink">{row.engine || '—'}</span>
            {showChain && row.attempts.length > 0 && (
              <span className="text-console-ink-mute">
                [{row.attempts.join(' → ')}]
              </span>
            )}
            {row.fallback && (
              <span className="bg-[#3a1212] text-[#e88888] rounded px-1 py-0.5 text-[10px]">
                silent fallback
              </span>
            )}
          </div>
        )
      })}
      {!hasFallbacks && (
        <div className="text-console-ink-mute italic">All shots routed on first try</div>
      )}
    </div>
  )
}

// ── Section: Gate audit (Task 7) ─────────────────────────────────────────────

function GateAudit({ sc }: { sc: CapabilityScorecard }) {
  const gates = (['plan', 'image', 'motion', 'final'] as const)

  return (
    <div className="font-console-mono text-xs space-y-1">
      {gates.map((g) => {
        const entry = sc.gates[g]
        const total = entry.approved + entry.vetoed
        const topVeto = entry.top_vetoes[0]
        return (
          <div key={g} className="flex items-baseline gap-2">
            <span className="text-console-ink-mute uppercase tracking-wider w-14 shrink-0">{g}</span>
            <span className={entry.vetoed > 0 ? 'text-[#e0b94e]' : 'text-[#7fd17f]'}>
              {entry.approved}/{total}
            </span>
            {topVeto && (
              <span className="text-console-ink-mute">
                · {topVeto[0]} <span className="text-console-accent">×{topVeto[1]}</span>
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Section: LoRA summary (Task 7) ───────────────────────────────────────────

function LoraSummary({ sc }: { sc: CapabilityScorecard }) {
  if (sc.lora.length === 0) {
    return <div className="text-console-ink-mute font-console-mono text-xs italic">No character LoRAs</div>
  }

  return (
    <div className="font-console-mono text-xs space-y-1">
      {sc.lora.map((row) => (
        <div key={row.char_id} className="flex items-baseline gap-2">
          <span className="text-console-ink-dim">{row.char_id}</span>
          {row.strength !== null && (
            <span className="text-console-ink-mute">str {row.strength.toFixed(2)}</span>
          )}
          {row.score !== null && (
            <span className={verdictClass(row.verdict)}>{row.score.toFixed(2)}</span>
          )}
          <span className={verdictClass(row.verdict)}>{row.verdict}</span>
        </div>
      ))}
    </div>
  )
}

// ── Section: Component status (Task 7) ───────────────────────────────────────

function ComponentStatus({ sc }: { sc: CapabilityScorecard }) {
  if (sc.components.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2">
      {sc.components.map((c) => (
        <span
          key={c.id}
          title={c.note || c.title}
          className={`font-console-mono text-xs border border-console-rule rounded px-2 py-0.5 ${statusClass(c.status)}`}
        >
          {c.id} <span className="opacity-60">●</span>{c.status}
        </span>
      ))}
    </div>
  )
}

// ── Main component ───────────────────────────────────────────────────────────

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

          {/* ── 1. Scorecard dimension grid (Task 5) ── */}
          <div>
            <Label>Capability scorecard</Label>
            <div className="mt-3">
              <ScorecardGrid sc={sc} />
            </div>
          </div>

          <div className="border-t border-console-rule" />

          {/* ── 2. Per-shot scores table (Task 6) ── */}
          <div>
            <Label>Per-shot scores</Label>
            <div className="mt-3">
              <PerShotTable sc={sc} />
            </div>
          </div>

          <div className="border-t border-console-rule" />

          {/* ── 3. Cascade provenance (Task 6 / U8) ── */}
          <div>
            <Label>Cascade provenance</Label>
            <div className="mt-2">
              <CascadeProvenance sc={sc} />
            </div>
          </div>

          <div className="border-t border-console-rule" />

          {/* ── 4–6. Gates / LoRA / Components — two-column layout (Task 7) ── */}
          <div className="grid grid-cols-2 gap-6">
            {/* Left: Gate audit */}
            <div>
              <Label>Gate audit</Label>
              <div className="mt-2">
                <GateAudit sc={sc} />
              </div>
            </div>

            {/* Right: LoRA summary + component status */}
            <div className="space-y-4">
              <div>
                <Label>LoRA quality</Label>
                <div className="mt-2">
                  <LoraSummary sc={sc} />
                </div>
              </div>
              <div>
                <Label>Components</Label>
                <div className="mt-2">
                  <ComponentStatus sc={sc} />
                </div>
              </div>
            </div>
          </div>

        </div>
      )}
    </div>
  )
}
