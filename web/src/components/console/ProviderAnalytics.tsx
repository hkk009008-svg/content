import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'

type HealthStatus = 'healthy' | 'degraded' | 'unhealthy' | 'unknown'

interface ProviderMetric {
  key: string
  terminal_count: number
  active_count: number
  succeeded: number
  failed_billed: number
  failed_unbilled: number
  failed_observed: number
  accepted_unknown: number
  success_rate: number | null
  average_terminal_latency_s: number | null
  p95_terminal_latency_s: number | null
  charged_cost_usd: number
  token_cost_usd: number
  active_reservation_usd: number
  sample_count: number
  health: {
    status: HealthStatus
    score: number | null
    sample_minimum: number
    reasons: string[]
  }
}

interface ProviderAnalyticsSnapshot {
  scope: 'project' | 'routing'
  scope_video_id: string
  terminal_limit: number
  cost_basis: 'reconciled_estimate'
  by_provider: Record<string, ProviderMetric>
}

interface Props {
  projectId: string | null
  isStreaming: boolean
}

const STATUS_ORDER: Record<HealthStatus, number> = {
  unhealthy: 0,
  degraded: 1,
  unknown: 2,
  healthy: 3,
}

const STATUS_TONE: Record<HealthStatus, string> = {
  healthy: 'text-ok',
  degraded: 'text-warn',
  unhealthy: 'text-fail',
  unknown: 'text-dim',
}

function secondsLabel(value: number | null): string {
  if (value == null) return '—'
  if (value < 60) return `${value.toFixed(1)}s`
  return `${(value / 60).toFixed(1)}m`
}

function reasonLabel(reason: string): string {
  return reason.replace(/_/g, ' ').replace(/:/g, ': ')
}

export default function ProviderAnalytics({ projectId, isStreaming }: Props) {
  const [scope, setScope] = useState<'project' | 'routing'>('project')
  const [snapshot, setSnapshot] = useState<ProviderAnalyticsSnapshot | null>(null)
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (signal?: AbortSignal) => {
    if (!projectId) return
    setLoading(true)
    try {
      const params = new URLSearchParams({ scope })
      const response = await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/provider-analytics?${params}`,
        { signal },
      )
      const body = await response.json() as ProviderAnalyticsSnapshot & { error?: string }
      if (!response.ok) throw new Error(body.error || `Analytics query failed (${response.status})`)
      if (!body?.by_provider || typeof body.by_provider !== 'object') {
        throw new Error('Analytics query returned an invalid response')
      }
      setSnapshot(body)
      setStatus('')
    } catch (error) {
      if ((error as { name?: string })?.name !== 'AbortError') {
        setStatus(error instanceof Error ? error.message : 'Provider analytics are unavailable.')
      }
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [projectId, scope])

  useEffect(() => {
    if (!projectId) {
      setSnapshot(null)
      setStatus('')
      return
    }
    const controller = new AbortController()
    load(controller.signal)
    const interval = window.setInterval(() => load(), isStreaming ? 10_000 : 30_000)
    return () => {
      controller.abort()
      window.clearInterval(interval)
    }
  }, [isStreaming, load, projectId])

  const providers = useMemo(() => Object.values(snapshot?.by_provider || {}).sort((a, b) => {
    const healthDelta = STATUS_ORDER[a.health.status] - STATUS_ORDER[b.health.status]
    return healthDelta || b.charged_cost_usd - a.charged_cost_usd || a.key.localeCompare(b.key)
  }), [snapshot])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    load()
  }

  return (
    <section className="border-t border-line px-4 py-5" aria-labelledby="provider-analytics-title">
      <div className="flex items-center justify-between gap-2">
        <h2 id="provider-analytics-title" className="font-mono text-eyebrow-lg uppercase tracking-wider text-dim">
          Provider health
        </h2>
        <button
          type="button"
          onClick={() => load()}
          disabled={loading || !projectId}
          className="font-mono text-[10px] uppercase tracking-wide text-mut hover:text-tx disabled:opacity-40"
        >
          Refresh
        </button>
      </div>
      <form onSubmit={submit} className="mt-3">
        <label className="block font-mono text-[10px] uppercase tracking-wide text-dim" htmlFor="provider-analytics-scope">
          Evidence scope
        </label>
        <select
          id="provider-analytics-scope"
          value={scope}
          onChange={(event) => setScope(event.target.value as 'project' | 'routing')}
          className="mt-1 w-full rounded border border-line bg-app px-2 py-1.5 text-xs text-tx"
        >
          <option value="project">This project</option>
          <option value="routing">Global routing history</option>
        </select>
      </form>
      {scope === 'routing' && (
        <p className="mt-2 text-[11px] leading-4 text-mut">
          AUTO video routing avoids engines scored unhealthy. Unknown and degraded engines remain eligible.
        </p>
      )}
      <p className="mt-2 text-[11px] leading-4 text-mut">
        Costs combine reconciled media estimates and token-list estimates; they are not provider invoices.
      </p>
      <div aria-live="polite" aria-busy={loading} className="mt-3">
        {providers.length === 0 && !status && (
          <p className="text-xs text-mut">No provider history yet.</p>
        )}
        {providers.length > 0 && (
          <ul className="space-y-2" aria-label="Provider usage and health">
            {providers.map((provider) => (
              <li key={provider.key} className="rounded border border-line bg-app px-2 py-2">
                <div className="flex items-center justify-between gap-2 font-mono text-xs">
                  <span className="truncate text-tx">{provider.key}</span>
                  <span className={STATUS_TONE[provider.health.status]}>
                    {provider.health.status}{provider.health.score == null ? '' : ` · ${provider.health.score}`}
                  </span>
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[10px] text-mut">
                  <div><dt>Success</dt><dd className="text-tx">{provider.success_rate == null ? 'Unknown' : `${(provider.success_rate * 100).toFixed(0)}%`}</dd></div>
                  <div><dt>P95 latency</dt><dd className="text-tx">{secondsLabel(provider.p95_terminal_latency_s)}</dd></div>
                  <div><dt>Estimated usage</dt><dd className="text-tx">${provider.charged_cost_usd.toFixed(4)}</dd></div>
                  <div><dt>Reserved</dt><dd className="text-tx">${provider.active_reservation_usd.toFixed(4)}</dd></div>
                  <div><dt>Outcomes</dt><dd className="text-tx">{provider.sample_count}</dd></div>
                  <div><dt>Unresolved</dt><dd className="text-tx">{provider.accepted_unknown}</dd></div>
                </dl>
                <p className="mt-2 text-[10px] leading-4 text-dim">
                  {provider.health.reasons.map(reasonLabel).join(' · ')}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
      {status && <p role="status" className="mt-2 text-xs text-warn">{status}</p>}
    </section>
  )
}
