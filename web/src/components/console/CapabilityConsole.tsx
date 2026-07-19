import { useEffect, useState } from 'react'
import type { Project, CapabilityScorecard, CapabilityDimension, ScorecardMedia } from '../../types/project'
import { Badge, Meter, StatusDot, Section, MICRO_LABEL, type BadgeVariant, type MeterTone, type Status } from '../ui'

interface Props { project: Project | null }

// ── Color helpers ────────────────────────────────────────────────────────────

/** Returns a token text class for a measured value vs its bar.
 *  null value → dim; no bar → plain ink; pass → ok; fail → fail. */
function scoreClass(value: number | null, bar: number | null): string {
  if (value === null) return 'text-dim'
  if (bar === null) return 'text-tx'
  return value >= bar ? 'text-ok' : 'text-fail'
}

function verdictVariant(verdict: 'ok' | 'warning' | 'rejected'): BadgeVariant {
  if (verdict === 'ok') return 'ok'
  if (verdict === 'warning') return 'warn'
  return 'fail'
}

function componentDot(status: string): Status {
  if (status === 'live' || status === 'wired') return 'ok'
  if (status === 'stubbed' || status === 'parked') return 'warn'
  if (status === 'dead') return 'fail'
  return 'idle'
}

function componentBadge(status: string): BadgeVariant {
  if (status === 'live' || status === 'wired') return 'ok'
  if (status === 'stubbed' || status === 'parked') return 'warn'
  if (status === 'dead') return 'fail'
  return 'neutral'
}

function fmt(v: number | null): string {
  if (v === null) return '—'
  return v.toFixed(2)
}

// ── Section: one dimension card (Task 5, restyled Task 11) ──────────────────

function DimensionCard({ d }: { d: CapabilityDimension }) {
  const tone: MeterTone = d.value === null ? 'acc' : d.pass === false ? 'fail' : 'ok'
  const isLipsync = d.key === 'lipsync'
  return (
    <div className="rounded border border-line bg-panel p-2">
      <div className={MICRO_LABEL}>{d.label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${scoreClass(d.value, d.bar)}`}>
        {d.value !== null ? d.value.toFixed(2) : '—'}
        {d.value !== null && d.bar !== null && (
          <span className="ml-1 text-xs font-normal text-dim">/ {d.bar.toFixed(2)}</span>
        )}
      </div>
      <div className="mt-1.5" data-testid="dimension-meter">
        <Meter value={d.value ?? 0} max={1} tone={tone} />
      </div>
      <div className="mt-1 text-[10px] text-dim">
        {d.n_measured} shot{d.n_measured !== 1 ? 's' : ''} measured
      </div>
      {isLipsync && (
        <div className="mt-1.5 flex items-center gap-1 text-[10px] text-warn">
          <StatusDot status="warn" />
          gate needs recal
        </div>
      )}
    </div>
  )
}

function ScorecardGrid({ sc }: { sc: CapabilityScorecard }) {
  return (
    <div>
      <div className="grid grid-cols-4 gap-2">
        {sc.dimensions.map((d: CapabilityDimension) => (
          <DimensionCard key={d.key} d={d} />
        ))}
      </div>

      {/* Media conformance tiles (U3) — real when sc.media present, dashed placeholders otherwise */}
      <MediaConformanceTiles media={sc.media ?? null} />

      {/* Future dimensions — greyed / dashed */}
      {sc.future_dimensions.length > 0 && (
        <div className="mt-2 grid grid-cols-4 gap-2">
          {sc.future_dimensions.map((fd: string) => (
            <div key={fd} className="rounded border border-dashed border-line p-2 opacity-40">
              <div className={MICRO_LABEL}>{fd.replace(/_/g, ' ')}</div>
              <div className="mt-1 text-[11px] text-dim">— not yet measured</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Media conformance tiles (U3) ─────────────────────────────────────────────

/** AUDIO LUFS + FORMAT tiles. Renders real data when sc.media is present;
 *  dashed/greyed placeholders identical to future_dimensions style otherwise. */
function MediaConformanceTiles({ media }: { media: ScorecardMedia | null }) {
  const passClass = (pass: boolean | undefined) =>
    pass === true ? 'text-ok' : pass === false ? 'text-fail' : 'text-dim'

  if (!media) {
    return (
      <div className="mt-2 grid grid-cols-4 gap-2">
        {(['audio_lufs', 'format_codec'] as const).map((fd) => (
          <div key={fd} className="rounded border border-dashed border-line p-2 opacity-40">
            <div className={MICRO_LABEL}>{fd.replace(/_/g, ' ')}</div>
            <div className="mt-1 text-[11px] text-dim">— not yet measured</div>
          </div>
        ))}
      </div>
    )
  }

  const { lufs, format } = media

  return (
    <div className="mt-2 grid grid-cols-4 gap-2">
      {/* AUDIO LUFS tile */}
      {lufs ? (
        <div className="rounded border border-line bg-panel p-2">
          <div className={MICRO_LABEL}>Audio LUFS</div>
          <div className={`mt-1 text-lg font-semibold tabular-nums ${passClass(lufs.pass)}`}>
            {lufs.value.toFixed(2)} LUFS
          </div>
          <div className="mt-1 text-[10px] text-dim">
            target {lufs.target} ±{lufs.tolerance}
          </div>
        </div>
      ) : (
        <div className="rounded border border-dashed border-line p-2 opacity-40">
          <div className={MICRO_LABEL}>Audio LUFS</div>
          <div className="mt-1 text-[11px] text-dim">— not measured</div>
        </div>
      )}

      {/* FORMAT tile */}
      {format ? (
        <div className="rounded border border-line bg-panel p-2">
          <div className={MICRO_LABEL}>Format</div>
          <div className={`mt-1 text-lg font-semibold tabular-nums ${passClass(format.pass)}`}>
            {format.width ?? '?'}×{format.height ?? '?'}
          </div>
          <div className="mt-1 text-[10px] text-dim">
            {format.vcodec ?? '?'}+{format.acodec ?? '?'}
          </div>
        </div>
      ) : (
        <div className="rounded border border-dashed border-line p-2 opacity-40">
          <div className={MICRO_LABEL}>Format</div>
          <div className="mt-1 text-[11px] text-dim">— not measured</div>
        </div>
      )}
    </div>
  )
}

// ── Section: Per-shot scores table (Task 6) ──────────────────────────────────

function PerShotTable({ sc }: { sc: CapabilityScorecard }) {
  if (sc.per_shot.length === 0) return <div className="text-[11px] italic text-dim">No shots yet</div>

  const barFor = (key: string): number | null =>
    sc.dimensions.find((d: CapabilityDimension) => d.key === key)?.bar ?? null

  const identityBar = barFor('identity')
  const coherenceBar = barFor('coherence')
  const motionBar = barFor('motion')
  const lipsyncBar = barFor('lipsync')

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr className="border-b border-line text-mut">
            <th className={`${MICRO_LABEL} py-1 pr-3 text-left`}>Shot</th>
            <th className={`${MICRO_LABEL} py-1 px-2 text-right`}>Identity</th>
            <th className={`${MICRO_LABEL} py-1 px-2 text-right`}>Coherence</th>
            <th className={`${MICRO_LABEL} py-1 px-2 text-right`}>Motion</th>
            <th className={`${MICRO_LABEL} py-1 px-2 text-right`}>Lipsync</th>
            <th className={`${MICRO_LABEL} py-1 pl-3 text-left`}>Engine</th>
          </tr>
        </thead>
        <tbody>
          {sc.per_shot.map((row) => (
            <tr key={row.shot_id} className="border-b border-line hover:bg-head/60">
              <td className="py-1 pr-3 text-dim">{row.shot_id}</td>
              <td className={`py-1 px-2 text-right tabular-nums ${scoreClass(row.identity, identityBar)}`}>{fmt(row.identity)}</td>
              <td className={`py-1 px-2 text-right tabular-nums ${scoreClass(row.coherence, coherenceBar)}`}>{fmt(row.coherence)}</td>
              <td className={`py-1 px-2 text-right tabular-nums ${scoreClass(row.motion, motionBar)}`}>{fmt(row.motion)}</td>
              <td className={`py-1 px-2 text-right tabular-nums ${scoreClass(row.lipsync, lipsyncBar)}`}>{fmt(row.lipsync)}</td>
              <td className="py-1 pl-3 text-dim">{row.engine || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Section: Cascade provenance (Task 6 / U8) ────────────────────────────────

function CascadeProvenance({ sc }: { sc: CapabilityScorecard }) {
  if (sc.provenance.length === 0) return <div className="text-[11px] italic text-dim">No shots yet</div>

  const hasFallbacks = sc.provenance.some((r) => r.fallback || r.attempts.length > 1)

  return (
    <div className="space-y-1 text-[11px]">
      {sc.provenance.map((row) => {
        const showChain = row.fallback || row.attempts.length > 1
        return (
          <div key={row.shot_id} className="flex flex-wrap items-center gap-2 border-b border-line/40 py-0.5">
            <span className="text-dim">{row.shot_id}</span>
            <span className="text-dim">·</span>
            <span className="text-tx">{row.engine || '—'}</span>
            {showChain && row.attempts.length > 0 && (
              <span className="text-mut">[{row.attempts.join(' → ')}]</span>
            )}
            {row.fallback && <Badge variant="fail">silent fallback</Badge>}
          </div>
        )
      })}
      {!hasFallbacks && <div className="italic text-dim">All shots routed on first try</div>}
    </div>
  )
}

// ── Section: Gate audit (Task 7) ─────────────────────────────────────────────

function GateAudit({ sc }: { sc: CapabilityScorecard }) {
  const gates = (['plan', 'image', 'motion', 'final'] as const)

  return (
    <div className="space-y-1 text-[11px]">
      {gates.map((g) => {
        const entry = sc.gates[g]
        const total = entry.approved + entry.vetoed
        const topVeto = entry.top_vetoes[0]
        return (
          <div key={g} className="flex items-baseline gap-2">
            <span className={`${MICRO_LABEL} w-14 shrink-0`}>{g}</span>
            <span className={entry.vetoed > 0 ? 'text-warn' : 'text-ok'}>
              {entry.approved}/{total}
            </span>
            {topVeto && (
              <span className="text-dim">
                · {topVeto[0]} <span className="text-fail">×{topVeto[1]}</span>
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
    return <div className="text-[11px] italic text-dim">No character LoRAs</div>
  }

  return (
    <div className="space-y-1 text-[11px]">
      {sc.lora.map((row) => (
        <div key={row.char_id} className="flex items-baseline gap-2">
          <span className="text-dim">{row.char_id}</span>
          {row.strength !== null && <span className="text-mut">str {row.strength.toFixed(2)}</span>}
          {row.score !== null && (
            <span className={row.verdict === 'ok' ? 'text-ok' : row.verdict === 'warning' ? 'text-warn' : 'text-fail'}>
              {row.score.toFixed(2)}
            </span>
          )}
          <Badge variant={verdictVariant(row.verdict)}>{row.verdict}</Badge>
        </div>
      ))}
    </div>
  )
}

// ── Section: Component status (Task 7) ───────────────────────────────────────

function ComponentStatus({ sc }: { sc: CapabilityScorecard }) {
  if (sc.components.length === 0) return <div className="text-[11px] italic text-dim">No component manifest</div>

  return (
    <div className="flex flex-wrap gap-2">
      {sc.components.map((c) => (
        <div
          key={c.id}
          title={c.note || c.title}
          className="flex items-center gap-1.5 rounded border border-line bg-panel px-2 py-1 text-[11px]"
        >
          <StatusDot status={componentDot(c.status)} />
          <span className="text-tx">{c.id}</span>
          <Badge variant={componentBadge(c.status)}>{c.status}</Badge>
        </div>
      ))}
    </div>
  )
}

// ── Section: Available — not engaged (Task 11) ───────────────────────────────

/** Curated capability inventory (ComfyUI max keyframe, second-character LoRA
 *  — per the redesign spec §"Page 4 — Capability") plus any component the
 *  manifest marks `stubbed`/`parked` (code exists but isn't reached / is
 *  blocked on external state, e.g. the pod). Second-char LoRA is hidden once
 *  the project actually has ≥2 characters with a LoRA row (sourced from
 *  `sc.lora`, not fabricated). Foley is deliberately excluded: it's a live,
 *  unconditional step in every scene (`cinema_pipeline.py:_ensure_scene_foley`),
 *  not a dormant/available-only capability — listing it here would misrepresent
 *  real pipeline state. */
function AvailableNotEngaged({ sc }: { sc: CapabilityScorecard }) {
  const secondCharLoraEngaged = sc.lora.length >= 2

  const curated: { id: string; label: string; note: string; pod: boolean }[] = [
    { id: 'comfy_max_keyframe', label: 'ComfyUI max keyframe', note: 'FLUX + PuLID keyframe fallback — needs the RunPod pod running.', pod: true },
    ...(secondCharLoraEngaged
      ? []
      : [{ id: 'second_char_lora', label: 'Second-character LoRA', note: 'Per-character LoRA training for a secondary cast member — trains on the pod.', pod: true }]),
  ]

  const stubbedComponents = sc.components.filter((c) => c.status === 'stubbed' || c.status === 'parked')

  return (
    <div className="flex flex-wrap gap-2">
      {curated.map((item) => (
        <div
          key={item.id}
          title={item.note}
          className="flex items-center gap-1.5 rounded border border-line bg-panel px-2 py-1 text-[11px]"
        >
          <StatusDot status="idle" />
          <span className="text-tx">{item.label}</span>
          <Badge variant={item.pod ? 'pod' : 'cloud'}>{item.pod ? 'Pod off' : 'Cloud'}</Badge>
        </div>
      ))}
      {stubbedComponents.map((c) => (
        <div
          key={c.id}
          title={c.note || c.title}
          className="flex items-center gap-1.5 rounded border border-line bg-panel px-2 py-1 text-[11px]"
        >
          <StatusDot status="idle" />
          <span className="text-tx">{c.title}</span>
          <Badge variant="neutral">{c.status}</Badge>
        </div>
      ))}
    </div>
  )
}

// ── Main component ───────────────────────────────────────────────────────────

export default function CapabilityConsole({ project }: Props) {
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

  const engagedCount = sc ? sc.components.filter((c) => c.status === 'live' || c.status === 'wired').length : 0
  const totalComponents = sc ? sc.components.length : 0
  const measuredDims = sc ? sc.dimensions.filter((d) => d.value !== null) : []
  const overallScore = measuredDims.length > 0
    ? Math.round((measuredDims.reduce((sum, d) => sum + (d.value as number), 0) / measuredDims.length) * 100)
    : null

  return (
    <div className="min-h-full bg-app text-tx">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-head px-4 py-2.5">
        <div>
          <div className={MICRO_LABEL}>{project?.name || 'No project'} · Capability</div>
          <div className="mt-1 flex items-baseline gap-3">
            <span className="font-mono text-2xl font-semibold tabular-nums text-tx">
              {overallScore !== null ? overallScore : '—'}
              <span className="text-sm font-normal text-dim">/100</span>
            </span>
            {sc && totalComponents > 0 && (
              <span className="text-[11px] text-mut">{engagedCount} of {totalComponents} systems engaged</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          {sc && (
            <span className="flex items-center gap-2 font-mono text-[11px] text-dim">
              <Badge variant="pri">{sc.tier.toUpperCase()}</Badge>
              {sc.summary.shots_clearing_all_bars}/{sc.summary.shots_total} clear all bars
            </span>
          )}
          <button onClick={load} className="font-mono text-[11px] uppercase tracking-wide text-mut hover:text-tx">
            ↻ refresh
          </button>
        </div>
      </header>

      {state === 'loading' && <div className="p-8 text-[13px] text-mut">Loading capability data…</div>}
      {state === 'error' && (
        <div className="p-8 text-[13px] text-fail">
          Could not load the scorecard. <button onClick={load} className="underline">Retry</button>
        </div>
      )}
      {state === 'empty' && (
        <div className="p-8 text-[13px] text-mut">No capability data yet — run the pipeline to populate scores.</div>
      )}
      {state === 'ready' && sc && (
        <div className="px-4 py-2">
          <Section title="Capability scorecard">
            <ScorecardGrid sc={sc} />
          </Section>

          <Section title="Per-shot scores">
            <PerShotTable sc={sc} />
          </Section>

          <Section title="Cascade provenance">
            <CascadeProvenance sc={sc} />
          </Section>

          <Section title="Gate audit">
            <GateAudit sc={sc} />
          </Section>

          <Section title="LoRA quality">
            <LoraSummary sc={sc} />
          </Section>

          <Section title="Components">
            <ComponentStatus sc={sc} />
          </Section>

          <Section title="Available — not engaged">
            <AvailableNotEngaged sc={sc} />
          </Section>
        </div>
      )}
    </div>
  )
}
