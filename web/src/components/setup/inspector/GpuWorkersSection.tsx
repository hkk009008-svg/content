import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  GpuWorkerControlResponse,
  GpuWorkerControlState,
  GpuWorkerState,
  GpuWorkerStatus,
  GpuWorkersResponse,
} from '../../../types/project'
import { apiGet, apiRequest } from '../../../lib/api'
import { Badge, BusyState, LiveRegion, LoadingState, Section, type BadgeVariant } from '../../ui'

const ENDPOINT = '/api/runtime/gpu-workers'
const CONTROL_ENDPOINT = '/api/runtime/gpu-worker-control'
const LAUNCH_POLL_INTERVAL_MS = 5000
const LAUNCH_POLL_TIMEOUT_MS = 5 * 60 * 1000

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

const CONTROL_PRESENTATION: Record<
  GpuWorkerControlState,
  { label: string; badge: BadgeVariant }
> = {
  unavailable: { label: 'Launch unavailable', badge: 'fail' },
  stopped: { label: 'Windows worker stopped', badge: 'neutral' },
  starting: { label: 'Windows worker starting', badge: 'warn' },
  running: { label: 'Windows task running', badge: 'ok' },
  failed: { label: 'Launch failed', badge: 'fail' },
  unknown: { label: 'Task state unknown', badge: 'warn' },
}

const CONTROL_STATES = new Set<GpuWorkerControlState>(
  Object.keys(CONTROL_PRESENTATION) as GpuWorkerControlState[],
)

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

function isGpuWorkerControlResponse(
  value: unknown,
  requireToken = false,
): value is GpuWorkerControlResponse {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  const control = value as Partial<GpuWorkerControlResponse>
  const optionalNumber = (candidate: unknown) => (
    candidate === undefined || (typeof candidate === 'number' && Number.isInteger(candidate))
  )
  return (
    control.schema_version === 1
    && typeof control.state === 'string'
    && CONTROL_STATES.has(control.state as GpuWorkerControlState)
    && typeof control.can_start === 'boolean'
    && typeof control.gpu_busy === 'boolean'
    && typeof control.message === 'string'
    && typeof control.checked_at === 'string'
    && (!requireToken || (typeof control.control_token === 'string' && control.control_token.length >= 32))
    && (control.control_token === undefined || typeof control.control_token === 'string')
    && optionalNumber(control.gpu_used_mib)
    && optionalNumber(control.gpu_utilization_percent)
    && optionalNumber(control.last_task_result)
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

function readinessAnnouncement(
  snapshot: GpuWorkersResponse | null,
  workerError: string | null,
  control: GpuWorkerControlResponse | null,
  controlError: string | null,
): string {
  const messages: string[] = []
  if (snapshot && !workerError) {
    messages.push(statusAnnouncement(snapshot))
  } else if (workerError) {
    messages.push(`GPU worker status unavailable. ${workerError}`)
  }
  if (control) {
    messages.push(
      `Windows launch control: ${CONTROL_PRESENTATION[control.state].label}. ${control.message}`,
    )
  } else if (controlError) {
    messages.push(`Windows launch control: Launch unavailable. ${controlError}`)
  }
  return messages.join(' ')
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

/** Readiness plus a narrow start-only control for the shared Windows worker.
 *  The backend owns all endpoint/credential/SSH details; this component sees
 *  only safe status projections and a process-local request token. */
interface Props {
  onImageWorker?: (worker: GpuWorkerStatus | null) => void
}

export function GpuWorkersSection({ onImageWorker }: Props = {}) {
  const [snapshot, setSnapshot] = useState<GpuWorkersResponse | null>(null)
  const [control, setControl] = useState<GpuWorkerControlResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [controlError, setControlError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [launching, setLaunching] = useState(false)
  const [launchNotice, setLaunchNotice] = useState('')
  const requestVersion = useRef(0)
  const refreshTimer = useRef<number | null>(null)
  const refreshButton = useRef<HTMLButtonElement | null>(null)
  const mounted = useRef(false)

  const load = useCallback(async ({ preserveLaunchNotice = false } = {}) => {
    const version = ++requestVersion.current
    setLoading(true)
    setError(null)
    setControlError(null)
    if (!preserveLaunchNotice) setLaunchNotice('')
    // A previous snapshot remains useful as last-known display data, but it is
    // not live selection authority while a refresh is pending or after it
    // fails. Only a newly validated response may re-enable the local backend.
    onImageWorker?.(null)

    const [result, controlResult] = await Promise.all([
      apiGet<GpuWorkersResponse>(ENDPOINT),
      apiGet<GpuWorkerControlResponse>(CONTROL_ENDPOINT),
    ])
    if (version !== requestVersion.current || !mounted.current) return null

    let validatedControl: GpuWorkerControlResponse | null = null

    if (!controlResult.ok) {
      setControl(null)
      setControlError(controlResult.error)
    } else if (!isGpuWorkerControlResponse(controlResult.data, true)) {
      setControl(null)
      setControlError('Windows worker launch control returned an invalid response.')
    } else {
      validatedControl = controlResult.data
      setControl(controlResult.data)
    }

    if (!result.ok) {
      setError(result.error)
      setLoading(false)
      return { control: validatedControl, snapshot: null }
    }
    if (!isGpuWorkersResponse(result.data)) {
      setError('GPU worker status returned an invalid response.')
      setLoading(false)
      return { control: validatedControl, snapshot: null }
    }

    setSnapshot(result.data)
    onImageWorker?.(
      result.data.workers.find((worker) => worker.role === 'image') ?? null,
    )
    setLoading(false)
    return { control: validatedControl, snapshot: result.data }
  }, [onImageWorker])

  useEffect(() => {
    mounted.current = true
    void load()
    return () => {
      mounted.current = false
      requestVersion.current += 1
      if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current)
    }
  }, [load])

  const beginLaunchPolling = useCallback(() => {
    const deadline = Date.now() + LAUNCH_POLL_TIMEOUT_MS
    const poll = async () => {
      if (!mounted.current) return
      const result = await load({ preserveLaunchNotice: true })
      if (!mounted.current) return
      const performanceReady = result?.snapshot?.workers.some(
        (worker) => worker.role === 'performance' && worker.state === 'ready',
      ) ?? false
      if (performanceReady) {
        setLaunchNotice('Windows performance worker is ready.')
        return
      }
      const controlState = result?.control?.state
      if (controlState && !['starting', 'running'].includes(controlState)) {
        setLaunchNotice(result?.control?.message ?? 'Windows worker did not become ready.')
        return
      }
      if (Date.now() >= deadline) {
        setLaunchNotice('Windows worker is still not ready. Refresh to check its latest status.')
        return
      }
      refreshTimer.current = window.setTimeout(() => {
        refreshTimer.current = null
        void poll()
      }, LAUNCH_POLL_INTERVAL_MS)
    }
    if (refreshTimer.current !== null) window.clearTimeout(refreshTimer.current)
    refreshTimer.current = window.setTimeout(() => {
      refreshTimer.current = null
      void poll()
    }, LAUNCH_POLL_INTERVAL_MS)
  }, [load])

  const startWindowsWorker = useCallback(async () => {
    if (!control?.control_token || !control.can_start || loading || launching) return
    setLaunching(true)
    setControlError(null)
    setLaunchNotice('Requesting Windows worker launch.')
    onImageWorker?.(null)
    const result = await apiRequest<GpuWorkerControlResponse>(
      `${CONTROL_ENDPOINT}/start`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Content-Control-Token': control.control_token,
        },
        body: '{}',
      },
    )
    if (!mounted.current) return
    if (!result.ok) {
      setControlError(result.error)
      setLaunchNotice(`Windows worker was not launched. ${result.error}`)
      setLaunching(false)
      return
    }
    if (!isGpuWorkerControlResponse(result.data)) {
      setControlError('Windows worker launch returned an invalid response.')
      setLaunchNotice('Windows worker launch response was invalid.')
      setLaunching(false)
      return
    }
    setControl({ ...result.data, control_token: control.control_token })
    setLaunchNotice(result.data.message)
    setLaunching(false)
    refreshButton.current?.focus()
    beginLaunchPolling()
  }, [beginLaunchPolling, control, loading, launching, onImageWorker])

  return (
    <Section
      title="GPU workers"
      right={(
        <button
          ref={refreshButton}
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
      <div aria-busy={loading || launching}>
        <LiveRegion
          message={
            launchNotice || (!loading
              ? readinessAnnouncement(snapshot, error, control, controlError)
              : '')
          }
        />
        {!snapshot && loading && <LoadingState label="Checking GPU workers" size="sm" />}

        {control && (
          <div className="mb-2 rounded border border-line bg-panel px-2 py-2">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-[11px] font-medium text-tx">Windows GPU worker</p>
                <p id="windows-worker-launch-description" className="mt-1 text-[10px] leading-4 text-mut">
                  {control.message}
                </p>
              </div>
              <Badge variant={CONTROL_PRESENTATION[control.state].badge}>
                {CONTROL_PRESENTATION[control.state].label}
              </Badge>
            </div>
            {(typeof control.gpu_used_mib === 'number' || typeof control.gpu_utilization_percent === 'number') && (
              <p className="mt-2 font-mono text-[10px] text-mut">
                {typeof control.gpu_used_mib === 'number' ? `${control.gpu_used_mib} MiB GPU memory` : 'GPU memory unknown'}
                {typeof control.gpu_utilization_percent === 'number' ? ` · ${control.gpu_utilization_percent}% utilization` : ''}
              </p>
            )}
            {control.state === 'stopped' && (
              <button
                type="button"
                onClick={() => void startWindowsWorker()}
                disabled={loading || launching || !control.can_start || control.gpu_busy}
                aria-describedby="windows-worker-launch-description"
                className="mt-2 rounded border border-accent/60 bg-accent/10 px-2 py-1.5 text-[10px] font-medium text-tx hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {launching ? 'Starting Windows worker…' : 'Start Windows worker'}
              </button>
            )}
          </div>
        )}

        {launching && <BusyState label="Starting Windows worker" className="mb-2" />}

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
        {controlError && (
          <p role="alert" className="mt-2 rounded border border-fail/50 bg-fail/[0.04] px-2 py-2 text-[10px] leading-4 text-fail">
            Windows worker launch unavailable: {controlError}
          </p>
        )}
      </div>
    </Section>
  )
}
