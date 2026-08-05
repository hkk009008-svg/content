import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  GpuWorkerState,
  GpuWorkerStatus,
  GpuWorkersResponse,
} from '../../../types/project'
import { apiGet } from '../../../lib/api'
import { Badge, BusyState, LiveRegion, LoadingState, Section, type BadgeVariant } from '../../ui'

const ENDPOINT = '/api/runtime/gpu-workers'

const STATE_PRESENTATION: Record<
  GpuWorkerState,
  { label: string; badge: BadgeVariant }
> = {
  unconfigured: { label: 'Not configured', badge: 'neutral' },
  not_installed: { label: 'Not installed', badge: 'neutral' },
  needs_benchmark: { label: 'Benchmark required', badge: 'warn' },
  offline: { label: 'Offline', badge: 'fail' },
  unauthorized: { label: 'Authorization failed', badge: 'fail' },
  blocked: { label: 'Blocked', badge: 'fail' },
  // Reachability proves only that the service answered. It is intentionally
  // warning-toned and worded differently from the node/model contract gate.
  reachable: { label: 'Reachable, not ready', badge: 'warn' },
  ready: { label: 'Ready', badge: 'ok' },
  incompatible: { label: 'Incompatible', badge: 'fail' },
}

const WORKER_STATES = new Set<GpuWorkerState>(Object.keys(STATE_PRESENTATION) as GpuWorkerState[])

function isWorker(value: unknown): value is GpuWorkerStatus {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const worker = value as Partial<GpuWorkerStatus>
  const optionalNumber = (candidate: unknown) => (
    candidate === undefined || (typeof candidate === 'number' && Number.isFinite(candidate))
  )
  return (
    (worker.role === 'image' || worker.role === 'performance')
    && typeof worker.label === 'string'
    && typeof worker.configured === 'boolean'
    && typeof worker.dedicated === 'boolean'
    && typeof worker.state === 'string'
    && WORKER_STATES.has(worker.state as GpuWorkerState)
    && typeof worker.message === 'string'
    && (worker.gpu_name === undefined || typeof worker.gpu_name === 'string')
    && optionalNumber(worker.vram_total_gib)
    && optionalNumber(worker.vram_free_gib)
    && optionalNumber(worker.running)
    && optionalNumber(worker.pending)
    && (worker.blocker_code === undefined || typeof worker.blocker_code === 'string')
    && (worker.benchmark_state === undefined || typeof worker.benchmark_state === 'string')
    && (worker.startup_ready === undefined || typeof worker.startup_ready === 'boolean')
    && (worker.execution_proven === undefined || typeof worker.execution_proven === 'boolean')
    && (
      worker.missing_node_classes === undefined
      || (
        Array.isArray(worker.missing_node_classes)
        && worker.missing_node_classes.every((nodeClass) => typeof nodeClass === 'string')
      )
    )
  )
}

function isGpuWorkersResponse(value: unknown): value is GpuWorkersResponse {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const response = value as Partial<GpuWorkersResponse>
  return (
    Array.isArray(response.workers)
    && response.workers.every(isWorker)
    && typeof response.checked_at === 'string'
  )
}

function formatGib(value: number | undefined): string | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null
  return `${value.toFixed(1)} GiB`
}

function checkedAtLabel(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString()
}

function statusAnnouncement(snapshot: GpuWorkersResponse): string {
  const outcomes = snapshot.workers
    .map((worker) => `${worker.label}: ${STATE_PRESENTATION[worker.state].label}`)
    .join('; ')
  return `GPU worker status updated. ${snapshot.workers.length} workers checked.${outcomes ? ` ${outcomes}.` : ''}`
}

function WorkerCard({ worker }: { worker: GpuWorkerStatus }) {
  const presentation = STATE_PRESENTATION[worker.state]
  const totalVram = formatGib(worker.vram_total_gib)
  const freeVram = formatGib(worker.vram_free_gib)
  const hasQueue = typeof worker.running === 'number' || typeof worker.pending === 'number'
  const missingNodes = worker.missing_node_classes ?? []

  return (
    <li className="rounded border border-line bg-panel px-2 py-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[11px] font-medium text-tx">{worker.label}</p>
          <p className="mt-0.5 font-mono text-[10px] uppercase tracking-wide text-mut">
            {worker.role} · {worker.configured ? (worker.dedicated ? 'Dedicated' : 'Shared') : 'No endpoint'}
          </p>
        </div>
        <Badge variant={presentation.badge}>{presentation.label}</Badge>
      </div>

      <p className="mt-2 text-[10px] leading-4 text-mut">{worker.message}</p>

      {(worker.gpu_name || totalVram || freeVram || hasQueue) && (
        <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[10px] text-mut">
          {worker.gpu_name && (
            <div className="col-span-2">
              <dt>GPU</dt>
              <dd className="break-words text-tx">{worker.gpu_name}</dd>
            </div>
          )}
          {totalVram && <div><dt>Total VRAM</dt><dd className="text-tx">{totalVram}</dd></div>}
          {freeVram && <div><dt>Free VRAM</dt><dd className="text-tx">{freeVram}</dd></div>}
          {typeof worker.running === 'number' && (
            <div><dt>Running</dt><dd className="text-tx">{worker.running}</dd></div>
          )}
          {typeof worker.pending === 'number' && (
            <div><dt>Pending</dt><dd className="text-tx">{worker.pending}</dd></div>
          )}
        </dl>
      )}

      {missingNodes.length > 0 && (
        <details className="mt-2 text-[10px] text-mut">
          <summary className="cursor-pointer text-fail">
            Missing node classes ({missingNodes.length})
          </summary>
          <ul className="mt-1 list-inside list-disc break-all font-mono text-[10px] text-mut">
            {missingNodes.map((nodeClass) => <li key={nodeClass}>{nodeClass}</li>)}
          </ul>
        </details>
      )}
    </li>
  )
}

/** Read-only readiness surface for configured image and performance workers.
 *  The backend owns all endpoint/credential details; this component receives
 *  only the safe status projection declared in `GpuWorkersResponse`. */
interface Props {
  onImageWorker?: (worker: GpuWorkerStatus | null) => void
}

export function GpuWorkersSection({ onImageWorker }: Props = {}) {
  const [snapshot, setSnapshot] = useState<GpuWorkersResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const requestVersion = useRef(0)

  const load = useCallback(async () => {
    const version = ++requestVersion.current
    setLoading(true)
    setError(null)
    // A previous snapshot remains useful as last-known display data, but it is
    // not live selection authority while a refresh is pending or after it
    // fails. Only a newly validated response may re-enable the local backend.
    onImageWorker?.(null)

    const result = await apiGet<GpuWorkersResponse>(ENDPOINT)
    if (version !== requestVersion.current) return

    if (!result.ok) {
      setError(result.error)
      setLoading(false)
      return
    }
    if (!isGpuWorkersResponse(result.data)) {
      setError('GPU worker status returned an invalid response.')
      setLoading(false)
      return
    }

    setSnapshot(result.data)
    onImageWorker?.(
      result.data.workers.find((worker) => worker.role === 'image') ?? null,
    )
    setLoading(false)
  }, [onImageWorker])

  useEffect(() => {
    void load()
    return () => {
      requestVersion.current += 1
    }
  }, [load])

  return (
    <Section
      title="GPU workers"
      right={(
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          aria-label="Refresh GPU worker status"
          className="font-mono text-[10px] uppercase tracking-wide text-mut hover:text-tx disabled:cursor-wait disabled:opacity-50"
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      )}
    >
      <div aria-busy={loading}>
        <LiveRegion
          message={
            snapshot && !loading && !error
              ? statusAnnouncement(snapshot)
              : ''
          }
        />
        {!snapshot && loading && <LoadingState label="Checking GPU workers" size="sm" />}

        {snapshot && (
          <>
            {loading && <BusyState label="Refreshing GPU workers" className="mb-2" />}
            {snapshot.workers.length > 0 ? (
              <ul className="space-y-2" aria-label="GPU worker readiness">
                {snapshot.workers.map((worker) => (
                  <WorkerCard key={worker.role} worker={worker} />
                ))}
              </ul>
            ) : (
              <p role="status" className="text-[10px] text-mut">No GPU worker roles were returned.</p>
            )}
            <p className="mt-2 font-mono text-[10px] text-mut">
              Last checked <time dateTime={snapshot.checked_at}>{checkedAtLabel(snapshot.checked_at)}</time>
            </p>
          </>
        )}

        {error && (
          <p role="alert" className="mt-2 rounded border border-fail/50 bg-fail/[0.04] px-2 py-2 text-[10px] leading-4 text-fail">
            GPU worker status unavailable: {error}
          </p>
        )}
      </div>
    </Section>
  )
}
