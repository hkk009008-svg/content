import { useCallback, useEffect, useState } from 'react'
import type { CostLiveSnapshot, PaidAttempt, Project, ShotState } from '../../types/project'

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
  const [costSnapshot, setCostSnapshot] = useState<CostLiveSnapshot | null>(null)
  const [costStatus, setCostStatus] = useState('')
  const [cancelingAttemptId, setCancelingAttemptId] = useState<string | null>(null)

  const loadCostSnapshot = useCallback(async (signal?: AbortSignal) => {
    if (!projectId) return
    try {
      const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/cost-live`, { signal })
      if (!res.ok) throw new Error(`Cost query failed (${res.status})`)
      const data = await res.json() as CostLiveSnapshot
      if (typeof data?.total_usd !== 'number' || !Array.isArray(data?.attempts)) {
        throw new Error('Cost query returned an invalid response')
      }
      setCostSnapshot(data)
      setCostStatus('')
    } catch (error) {
      if ((error as { name?: string })?.name !== 'AbortError') {
        setCostStatus('Live cost is temporarily unavailable.')
      }
    }
  }, [projectId])

  // Cost and paid-job state remain useful after streaming stops, so keep a
  // slower idle refresh instead of making this surface disappear at run end.
  useEffect(() => {
    if (!projectId) {
      setCostSnapshot(null)
      setCostStatus('')
      return
    }
    const controller = new AbortController()
    loadCostSnapshot(controller.signal)
    const id = window.setInterval(
      () => loadCostSnapshot(),
      isStreaming ? 5000 : 15000,
    )
    return () => {
      controller.abort()
      window.clearInterval(id)
    }
  }, [isStreaming, loadCostSnapshot, projectId])

  const cancelAttempt = async (attempt: PaidAttempt) => {
    if (!projectId || cancelingAttemptId) return
    const confirmed = window.confirm(
      `Request cancellation of ${attempt.engine} job ${attempt.provider_job_id || attempt.attempt_id}? The reservation remains active until Runway confirms a terminal state.`,
    )
    if (!confirmed) return
    setCancelingAttemptId(attempt.attempt_id)
    setCostStatus('Requesting Runway cancellation…')
    try {
      const res = await fetch(
        `/api/projects/${encodeURIComponent(projectId)}/paid-attempts/${encodeURIComponent(attempt.attempt_id)}/cancel`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' },
      )
      const payload = await res.json() as CostLiveSnapshot & { cancellation?: PaidAttempt; error?: string }
      if (!res.ok) throw new Error(payload.error || `Cancellation failed (${res.status})`)
      setCostSnapshot(payload)
      setCostStatus(payload.cancellation?.state === 'accepted_unknown'
        ? 'Cancellation outcome is unknown. Reconcile the task in Runway; reserved budget remains held.'
        : 'Cancellation requested. Budget remains reserved until Runway confirms the final state.')
    } catch (error) {
      setCostStatus(error instanceof Error ? error.message : 'Cancellation request failed.')
    } finally {
      setCancelingAttemptId(null)
    }
  }

  const totalShots = project?.scenes?.reduce((sum, s) => sum + (s.shots?.length || 0), 0) || 0

  // Best-effort: find most-recent target_api
  let currentEngine: string | undefined
  for (const s of shotStates.values()) {
    if (s.target_api) currentEngine = s.target_api
  }

  const bins = buildHistogram(shotStates)
  const maxBin = Math.max(1, ...bins)
  const activeAttempts = costSnapshot?.attempts.filter((attempt) => attempt.active) || []
  const chargedUsd = costSnapshot?.charged_usd ?? costSnapshot?.total_usd

  return (
    <section className="px-4 py-6 bg-panel" aria-labelledby="telemetry-title">
      <h2 id="telemetry-title" className="text-eyebrow-lg uppercase tracking-wider text-dim mb-3 font-mono">
        Telemetry
      </h2>
      <dl className="space-y-4 text-xs">
        <div>
          <dt className="text-dim uppercase text-eyebrow-lg font-mono">Shots</dt>
          <dd className="mt-0.5 font-mono text-tx">
            {totalShots}
            {failedShots.length > 0 && (
              <span className="ml-2 text-acc font-normal">({failedShots.length} failed)</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-dim uppercase text-eyebrow-lg font-mono">Engine</dt>
          <dd className="mt-0.5 font-mono text-acc">{currentEngine || '—'}</dd>
        </div>
        <div>
          <dt className="text-dim uppercase text-eyebrow-lg mb-1 font-mono">Identity scores</dt>
          <dd className="flex items-end gap-1 h-10">
            {bins.map((count, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-0.5">
                <div
                  className="w-full rounded-sm bg-acc/60"
                  style={{ height: `${Math.round((count / maxBin) * 32) + 2}px` }}
                  title={`${SCORE_BINS[i]}: ${count}`}
                />
              </div>
            ))}
          </dd>
          <div className="flex justify-between text-dim mt-0.5 font-mono">
            <span>0</span><span>1</span>
          </div>
        </div>
        <div aria-live="polite">
          <dt className="text-dim uppercase text-eyebrow-lg font-mono">Spend authority</dt>
          <dd className="mt-1">
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-tx">
              <div>
                <dt className="text-dim">Charged</dt>
                <dd>{chargedUsd != null ? `$${chargedUsd.toFixed(4)}` : '—'}</dd>
              </div>
              <div>
                <dt className="text-dim">Reserved</dt>
                <dd>{costSnapshot ? `$${costSnapshot.active_reservation_usd.toFixed(4)}` : '—'}</dd>
              </div>
              <div>
                <dt className="text-dim">Exposure</dt>
                <dd>{costSnapshot ? `$${costSnapshot.committed_usd.toFixed(4)}` : '—'}</dd>
              </div>
              <div>
                <dt className="text-dim">Remaining</dt>
                <dd>{costSnapshot
                  ? costSnapshot.budget_status === 'invalid'
                    ? 'Invalid — blocked'
                    : costSnapshot.remaining_usd == null ? 'Unlimited' : `$${costSnapshot.remaining_usd.toFixed(4)}`
                  : '—'}</dd>
              </div>
            </dl>
          </dd>
        </div>
        {costSnapshot && (
          <div>
            <dt className="text-dim uppercase text-eyebrow-lg font-mono">Paid jobs</dt>
            <dd className="mt-1 space-y-2">
              {costSnapshot.accepted_unknown_count > 0 && (
                <p role="alert" className="rounded border border-warn/50 bg-warn/5 px-2 py-1.5 text-warn">
                  {costSnapshot.accepted_unknown_count} accepted job{costSnapshot.accepted_unknown_count === 1 ? '' : 's'} need provider reconciliation. Reserved budget remains held.
                </p>
              )}
              {(costSnapshot.billed_failure_count > 0 || costSnapshot.blocked_attempt_count > 0) && (
                <p className="text-mut">
                  {costSnapshot.billed_failure_count} billed failure{costSnapshot.billed_failure_count === 1 ? '' : 's'} · {costSnapshot.blocked_attempt_count} budget block{costSnapshot.blocked_attempt_count === 1 ? '' : 's'}
                </p>
              )}
              {activeAttempts.length === 0 ? (
                <p className="text-mut">No active paid jobs.</p>
              ) : (
                <ul className="space-y-2" aria-label="Active paid provider jobs">
                  {activeAttempts.map((attempt) => (
                    <li key={attempt.attempt_id} className="rounded border border-line bg-app px-2 py-2">
                      <div className="flex flex-wrap items-center justify-between gap-1">
                        <span className="font-mono text-tx">{attempt.engine}</span>
                        <span className="font-mono text-warn">{attempt.state.replace(/_/g, ' ')}</span>
                      </div>
                      <p className="mt-1 break-all font-mono text-dim">
                        {attempt.provider_job_id || 'Waiting for provider task ID'}
                      </p>
                      <p className="mt-1 text-mut">Reserved ${attempt.reserved_cost_usd.toFixed(4)}</p>
                      {attempt.provider === 'runway' && attempt.state !== 'cancel_requested' && (
                        <button
                          type="button"
                          onClick={() => cancelAttempt(attempt)}
                          disabled={cancelingAttemptId != null || !attempt.provider_job_id}
                          aria-busy={cancelingAttemptId === attempt.attempt_id}
                          className="mt-2 rounded border border-fail/50 px-2 py-1 text-eyebrow-lg text-fail hover:bg-fail/10 disabled:opacity-40"
                        >
                          {cancelingAttemptId === attempt.attempt_id ? 'Requesting…' : 'Request cancellation'}
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </dd>
          </div>
        )}
      </dl>
      {costStatus && <p role="status" className="mt-3 text-xs text-warn">{costStatus}</p>}
    </section>
  )
}
