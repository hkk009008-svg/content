import { useEffect, useState } from 'react'
import type { Project, CapabilityScorecard, CapabilityDimension, CapabilityComponent, ScorecardMedia } from '../../types/project'
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

/** Human badge/dot for one capability row. A component's AUTHORED `status`
 *  (live/wired) is never trusted on its own — `engaged_static` is the
 *  server-validated fact (real consumer + passing evidence test on file).
 *  A status that CLAIMS engagement but fails that check renders as
 *  "unavailable", never as if it were live/wired. */
function componentDisplay(c: CapabilityComponent): { dot: Status; badge: BadgeVariant; label: string } {
  const claimsEngagement = c.status === 'live' || c.status === 'wired'
  if (claimsEngagement && !c.engaged_static) {
    return { dot: 'fail', badge: 'fail', label: 'unavailable' }
  }
  if (claimsEngagement && c.runtime_availability === 'unavailable') {
    return { dot: 'warn', badge: 'warn', label: `${c.status} · unavailable now` }
  }
  if (claimsEngagement) return { dot: 'ok', badge: 'ok', label: c.status }
  if (c.status === 'stubbed' || c.status === 'parked') return { dot: 'warn', badge: 'warn', label: c.status }
  if (c.status === 'dead') return { dot: 'fail', badge: 'fail', label: c.status }
  if (c.status === 'inactive') return { dot: 'idle', badge: 'neutral', label: c.status }
  return { dot: 'idle', badge: 'neutral', label: c.status || 'unknown' }
}

const SPEND_LABEL: Record<CapabilityComponent['spend_kind'], string> = {
  none: 'no spend',
  compute_local: 'local compute',
  paid_api: 'paid API',
  local_gpu: 'local GPU',
}

/** `KLING_NATIVE` -> `Kling Native`, `SORA_2` -> `Sora 2`, empty -> `—`.
 *  Engine identifiers are internal routing constants, not operator-facing
 *  labels — never render the raw uppercase/underscore token on the page. */
function humanizeEngineId(raw: string): string {
  if (!raw) return '—'
  return raw
    .split('_')
    .filter(Boolean)
    .map((w) => (w.length > 0 ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w))
    .join(' ')
}

function fmt(v: number | null): string {
  if (v === null) return '—'
  return v.toFixed(2)
}

// ── Section: one dimension card (Task 5, restyled Task 11) ──────────────────

function DimensionCard({ d }: { d: CapabilityDimension }) {
  const tone: MeterTone = d.pass === false ? 'fail' : d.value === null ? 'acc' : 'ok'
  const isLipsync = d.key === 'lipsync'
  const unknown = d.n_unknown ?? 0
  const failed = d.n_failed ?? 0
  const applicable = d.n_applicable ?? d.n_measured
  const emptyLabel = isLipsync
    ? unknown > 0
      ? 'UNKNOWN'
      : applicable === 0
        ? 'N/A'
        : '—'
    : '—'
  return (
    <div className="rounded border border-line bg-panel p-2">
      <div className={MICRO_LABEL}>{d.label}</div>
      <div className={`mt-1 text-lg font-semibold tabular-nums ${scoreClass(d.value, d.bar)}`}>
        {d.value !== null ? d.value.toFixed(2) : emptyLabel}
        {d.value !== null && d.bar !== null && (
          <span className="ml-1 text-xs font-normal text-dim">/ {d.bar.toFixed(2)}</span>
        )}
      </div>
      <div className="mt-1.5" data-testid="dimension-meter">
        <Meter value={d.value ?? 0} max={1} tone={tone} />
      </div>
      <div className="mt-1 text-[10px] text-dim">
        {d.n_measured}/{applicable} applicable shot{applicable !== 1 ? 's' : ''} measured
      </div>
      {isLipsync && unknown > 0 && (
        <div className="mt-1.5 flex items-center gap-1 text-[10px] text-warn">
          <StatusDot status="warn" />
          {unknown} unknown · manual review required
        </div>
      )}
      {isLipsync && failed > 0 && (
        <div className="mt-1 flex items-center gap-1 text-[10px] text-fail">
          <StatusDot status="fail" />
          {failed} measured failure{failed === 1 ? '' : 's'}
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
              <td className={`py-1 px-2 text-right tabular-nums ${
                row.lipsync_state === 'UNKNOWN'
                  ? 'text-warn'
                  : row.lipsync_state === 'FAIL'
                    ? 'text-fail'
                    : scoreClass(row.lipsync, lipsyncBar)
              }`}>
                {row.lipsync_state === 'NOT_APPLICABLE'
                  ? 'N/A'
                  : row.lipsync_state === 'UNKNOWN'
                    ? 'UNKNOWN'
                    : fmt(row.lipsync)}
              </td>
              <td className="py-1 pl-3 text-dim">{humanizeEngineId(row.engine)}</td>
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
            <span className="text-tx">{humanizeEngineId(row.engine)}</span>
            {showChain && row.attempts.length > 0 && (
              <span className="text-mut">[{row.attempts.map(humanizeEngineId).join(' → ')}]</span>
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
        const deferred = entry.deferred ?? 0
        const total = entry.approved + entry.vetoed + deferred
        const topVeto = entry.top_vetoes[0]
        return (
          <div key={g} className="flex items-baseline gap-2">
            <span className={`${MICRO_LABEL} w-14 shrink-0`}>{g}</span>
            <span className={entry.vetoed > 0 ? 'text-warn' : 'text-ok'}>
              {entry.approved}/{total}
            </span>
            {deferred > 0 && (
              <span className="text-warn">· {deferred} review required</span>
            )}
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

// ── Section: Component status (Task 7, evidence-backed Slice 12) ────────────

/** One capability chip. Shows the human title + a status badge computed
 *  from the server-validated `engaged_static`/`runtime_availability` (never
 *  the authored `status` string alone — see componentDisplay). The `title`
 *  attribute and the visible caption both carry only `reason`: a human
 *  next-action sentence. Raw anchors/ids/hashes/dev notes are diagnostic-only
 *  and never reach this component — the server's operator projection
 *  (cinema.capability_manifest.to_operator_view) already strips them. */
function ComponentChip({ c }: { c: CapabilityComponent }) {
  const disp = componentDisplay(c)
  const showReason = !c.engaged_static || c.runtime_availability === 'unavailable'
  const reasonText = c.engaged_static ? c.runtime_reason : c.reason
  return (
    <div
      title={c.reason}
      className="flex max-w-[240px] flex-col gap-0.5 rounded border border-line bg-panel px-2 py-1 text-[11px]"
    >
      <div className="flex items-center gap-1.5">
        <StatusDot status={disp.dot} />
        <span className="text-tx">{c.title}</span>
        <Badge variant={disp.badge}>{disp.label}</Badge>
      </div>
      <div className="flex items-center gap-1.5 text-[10px] text-dim">
        <span>{SPEND_LABEL[c.spend_kind] ?? c.spend_kind}</span>
        <span>·</span>
        <span>{c.exposure}</span>
      </div>
      {showReason && reasonText && <div className="text-[10px] text-mut">{reasonText}</div>}
    </div>
  )
}

function ComponentStatus({ sc }: { sc: CapabilityScorecard }) {
  if (sc.components.length === 0) return <div className="text-[11px] italic text-dim">No component manifest</div>

  return (
    <div className="flex flex-wrap gap-2">
      {sc.components.map((c) => (
        <ComponentChip key={c.id} c={c} />
      ))}
    </div>
  )
}

// ── Section: Available — not engaged (Task 11) ───────────────────────────────

/** Manifest entries marked `stubbed`/`parked`. Retired providers and retained
 *  history are deliberately absent: neither is an available capability. Foley
 *  is also excluded because it is a live, unconditional scene step. */
function AvailableNotEngaged({ sc }: { sc: CapabilityScorecard }) {
  const stubbedComponents = sc.components.filter((c) => c.status === 'stubbed' || c.status === 'parked')

  return (
    <div className="flex flex-wrap gap-2">
      {stubbedComponents.map((c) => (
        <div
          key={c.id}
          className="rounded border border-line bg-panel px-2 py-1 text-[11px]"
        >
          <div className="flex items-center gap-1.5">
            <StatusDot status="idle" />
            <span className="text-tx">{c.title}</span>
            <Badge variant="neutral">{c.status}</Badge>
          </div>
          {c.reason && <p className="mt-1 max-w-64 text-[10px] leading-4 text-mut">{c.reason}</p>}
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

  // engaged_static, NOT the authored status string — a component claiming
  // "live"/"wired" without a server-verified consumer + evidence test must
  // not count toward this headline (comprehensive-unification audit: claims
  // advertised as wired on syntactic anchors alone).
  const engagedCount = sc ? sc.components.filter((c) => c.engaged_static).length : 0
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
              {/* "max" is a retired, pre-WS1 tier value that may still be
                  persisted on old projects. It no longer selects a distinct
                  image pipeline, so the UI labels it as history. */}
              <span title={sc.tier === 'max' ? 'Legacy value — runs identically to production; the max tier was retired.' : undefined}>
                <Badge variant={sc.tier === 'max' ? 'neutral' : 'pri'}>
                  {sc.tier === 'max' ? 'MAX (legacy)' : sc.tier.toUpperCase()}
                </Badge>
              </span>
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
