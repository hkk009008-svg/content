import { useState } from 'react'
import type { ShotState } from '../../types/project'

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

  const score = shot.identity_score
  const lowScore = score != null && score < 0.7

  const handleApprove = async () => {
    setLoading(true)
    await fetch(`/api/projects/${projectId}/shots/${shotId}/plan/approve`, { method: 'POST' })
    setLoading(false)
    onAction()
  }

  const handleReject = async () => {
    setLoading(true)
    await fetch(`/api/projects/${projectId}/shots/${shotId}/plan/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
    setLoading(false)
    setRejecting(false)
    onAction()
  }

  return (
    <div className="flex flex-col gap-2 mt-2">
      {lowScore && (
        <div className="text-eyebrow text-fail bg-fail/10 px-2 py-1 rounded">
          Low identity similarity ({Math.round((score || 0) * 100)}%) — recommend reject
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
    </div>
  )
}
