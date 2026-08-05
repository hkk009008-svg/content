import { FormEvent, useCallback, useEffect, useState } from 'react'

interface TraceEvent {
  event_id: number
  ts: string
  level: string
  logger: string
  message: string
  trace_id: string
  scene_id: string
  shot_id: string
  engine: string
  fields: Record<string, unknown>
}

interface TracePage {
  events: TraceEvent[]
  has_more: boolean
  next_before_event_id: number | null
}

interface Props {
  projectId: string | null
  isStreaming: boolean
}

function timeLabel(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleTimeString()
}

export default function TraceConsole({ projectId, isStreaming }: Props) {
  const [queryDraft, setQueryDraft] = useState('')
  const [traceDraft, setTraceDraft] = useState('')
  const [levelDraft, setLevelDraft] = useState('')
  const [filters, setFilters] = useState({ query: '', traceId: '', level: '' })
  const [page, setPage] = useState<TracePage>({ events: [], has_more: false, next_before_event_id: null })
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (
    beforeEventId: number | null = null,
    append = false,
    signal?: AbortSignal,
  ) => {
    if (!projectId) return
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (filters.query) params.set('q', filters.query)
      if (filters.traceId) params.set('trace_id', filters.traceId)
      if (filters.level) params.set('level', filters.level)
      if (beforeEventId != null) {
        params.set('before', String(beforeEventId))
      }
      params.set('limit', '25')
      const response = await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/traces?${params}`,
        { signal },
      )
      const body = await response.json() as TracePage & { error?: string }
      if (!response.ok) throw new Error(body.error || `Trace query failed (${response.status})`)
      if (!Array.isArray(body?.events)) throw new Error('Trace query returned an invalid response')
      setPage((current) => ({
        ...body,
        events: append ? [...current.events, ...body.events] : body.events,
      }))
      setStatus('')
    } catch (error) {
      if ((error as { name?: string })?.name !== 'AbortError') {
        setStatus(error instanceof Error ? error.message : 'Traces are unavailable.')
      }
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [filters, projectId])

  useEffect(() => {
    if (!projectId) {
      setPage({ events: [], has_more: false, next_before_event_id: null })
      setStatus('')
      return
    }
    const controller = new AbortController()
    load(null, false, controller.signal)
    return () => controller.abort()
  }, [filters, load, projectId])

  useEffect(() => {
    if (!projectId || !isStreaming) return
    const interval = window.setInterval(() => load(), 10_000)
    return () => window.clearInterval(interval)
  }, [isStreaming, load, projectId])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setFilters({ query: queryDraft.trim(), traceId: traceDraft.trim(), level: levelDraft })
  }

  return (
    <section className="border-t border-line px-4 py-5" aria-labelledby="trace-console-title">
      <div className="flex items-center justify-between gap-2">
        <h2 id="trace-console-title" className="font-mono text-eyebrow-lg uppercase tracking-wider text-dim">
          Searchable traces
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
      <form onSubmit={submit} className="mt-3 space-y-2" role="search">
        <label className="block">
          <span className="sr-only">Search trace messages and fields</span>
          <input
            type="search"
            value={queryDraft}
            onChange={(event) => setQueryDraft(event.target.value)}
            placeholder="Search message, shot, engine…"
            maxLength={200}
            className="w-full rounded border border-line bg-app px-2 py-1.5 text-xs text-tx placeholder:text-dim"
          />
        </label>
        <div className="flex gap-2">
          <label className="min-w-0 flex-1">
            <span className="sr-only">Trace ID</span>
            <input
              value={traceDraft}
              onChange={(event) => setTraceDraft(event.target.value)}
              placeholder="Trace ID"
              maxLength={128}
              className="w-full rounded border border-line bg-app px-2 py-1.5 font-mono text-[11px] text-tx placeholder:text-dim"
            />
          </label>
          <label>
            <span className="sr-only">Trace level</span>
            <select
              value={levelDraft}
              onChange={(event) => setLevelDraft(event.target.value)}
              className="rounded border border-line bg-app px-2 py-1.5 text-xs text-tx"
            >
              <option value="">All</option>
              <option value="INFO">Info</option>
              <option value="WARNING">Warning</option>
              <option value="ERROR">Error</option>
              <option value="CRITICAL">Critical</option>
            </select>
          </label>
          <button type="submit" className="rounded border border-line px-2 py-1.5 font-mono text-[10px] uppercase text-pri hover:bg-pri/10">
            Search
          </button>
        </div>
      </form>
      <div className="mt-3" aria-live="polite" aria-busy={loading}>
        {page.events.length === 0 && !status && (
          <p className="text-xs text-mut">No matching project traces.</p>
        )}
        {page.events.length > 0 && (
          <ol className="space-y-2" aria-label="Project trace events">
            {page.events.map((event) => (
              <li key={event.event_id} className="rounded border border-line bg-app px-2 py-2">
                <div className="flex items-center justify-between gap-2 font-mono text-[10px]">
                  <span className={event.level === 'ERROR' || event.level === 'CRITICAL' ? 'text-fail' : event.level === 'WARNING' ? 'text-warn' : 'text-dim'}>
                    {event.level}
                  </span>
                  <time className="text-dim" dateTime={event.ts}>{timeLabel(event.ts)}</time>
                </div>
                <p className="mt-1 break-words text-xs leading-4 text-tx">{event.message}</p>
                <p className="mt-1 break-all font-mono text-[10px] text-dim">
                  {[event.engine, event.shot_id, event.trace_id].filter(Boolean).join(' · ') || event.logger}
                </p>
              </li>
            ))}
          </ol>
        )}
        {page.has_more && (
          <button
            type="button"
            onClick={() => load(page.next_before_event_id, true)}
            disabled={loading}
            className="mt-3 w-full rounded border border-line px-2 py-1.5 font-mono text-[10px] uppercase text-mut hover:text-tx disabled:opacity-40"
          >
            Load older
          </button>
        )}
      </div>
      {status && <p role="status" className="mt-2 text-xs text-warn">{status}</p>}
    </section>
  )
}
