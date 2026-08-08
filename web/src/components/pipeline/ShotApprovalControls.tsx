import { useState } from 'react'
import type { ShotState } from '../../types/project'
import { apiPost } from '../../lib/api'

interface Props {
  shot: Partial<ShotState>
  shotId: string
  projectId: string
  onAction: () => void
}

export default function ShotApprovalControls({ shot, shotId, projectId, onAction }: Props) {
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The browser must not decide whether identity passed. It used to compare
  // `score < 0.7` and print "recommend reject" — a fourth threshold, ignoring
  // both the project's identity_strictness and the shot-typed table in
  // identity/types.py (wide standard is 0.55, not 0.70).
  //
  // Worse, ADR-092: the scorer INVERTS RANK on off-angle views. A real
  // photograph of the subject in profile scores 0.556 and "fails", while a
  // generated panel the subject confirmed is NOT him scored 0.570. Every shot
  // where a character turns lands in that band, so the old banner recommended
  // rejecting correct footage — and a rejection costs a re-render.
  //
  // The score is still worth SHOWING; it is a frontal-only signal and is
  // presented as one, with no recommended action. The server owns the verdict.
  const score = shot.identity_score
  const hasScore = score != null
  const belowFrontalBand = hasScore && (score as number) < 0.65

  const handleApprove = async () => {
    setLoading(true)
    setError(null)
    const result = await apiPost(`/api/projects/${projectId}/shots/${shotId}/plan/approve`)
    setLoading(false)
    if (!result.ok) setError(result.error)
    onAction() // refresh authoritative state either way
  }

  const handleReject = async () => {
    setLoading(true)
    setError(null)
    const result = await apiPost(`/api/projects/${projectId}/shots/${shotId}/plan/reject`, { reason })
    setLoading(false)
    // Slice 8 requirement 5: a non-2xx/network failure is an error, not
    // optimistic success -- keep the rejection editor (input + reason)
    // open with the operator's text intact instead of closing as if the
    // reject had landed.
    if (result.ok) {
      setRejecting(false)
    } else {
      setError(result.error)
    }
    onAction() // refresh authoritative state either way
  }

  return (
    <div className="flex flex-col gap-2 mt-2">
      {hasScore && (
        <div
          className={
            belowFrontalBand
              ? 'text-eyebrow text-warn bg-warn/10 px-2 py-1 rounded'
              : 'text-eyebrow text-mut bg-panel px-2 py-1 rounded'
          }
        >
          Identity similarity {Math.round((score as number) * 100)}%
          {belowFrontalBand && (
            <>
              {' — '}
              <span title={
                'Measured against the single frontal reference image. This scorer '
                + 'cannot resolve turned-away views: a real photograph of the '
                + 'subject in profile scores 0.556 and would read as a failure. '
                + 'Judge this take by eye.'
              }>
                cannot be judged for a turned pose
              </span>
            </>
          )}
        </div>
      )}

      {!rejecting ? (
        <div className="flex gap-2">
          <button
            onClick={handleApprove}
            disabled={loading}
            className="text-eyebrow-lg px-3 py-1 rounded border border-ok/50 text-ok
              hover:bg-ok/10 disabled:opacity-40"
          >
            {loading ? '...' : '✓ Approve'}
          </button>
          <button
            onClick={() => setRejecting(true)}
            disabled={loading}
            className="text-eyebrow-lg px-3 py-1 rounded border border-fail/50 text-fail
              hover:bg-fail/10 disabled:opacity-40"
          >
            ✕ Reject
          </button>
        </div>
      ) : (
        <div className="flex gap-2 items-end">
          <input
            type="text"
            value={reason}
            onChange={e => setReason(e.target.value)}
            placeholder="Rejection reason (optional)"
            className="text-eyebrow-lg bg-app border border-line rounded px-2 py-1 text-tx flex-1"
          />
          <button
            onClick={handleReject}
            disabled={loading}
            className="text-eyebrow-lg px-3 py-1 rounded bg-fail text-white disabled:opacity-40"
          >
            Reject
          </button>
          <button
            onClick={() => setRejecting(false)}
            className="text-eyebrow-lg px-2 py-1 text-mut"
          >
            Cancel
          </button>
        </div>
      )}

      {error && (
        <div role="alert" className="text-eyebrow text-fail bg-fail/10 px-2 py-1 rounded">
          {error}
        </div>
      )}
    </div>
  )
}
