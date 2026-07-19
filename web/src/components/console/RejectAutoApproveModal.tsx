/**
 * RejectAutoApproveModal — required-reason form for overriding an auto-approve decision.
 *
 * On submit: POSTs to POST /api/projects/<projectId>/shots/<shotId>/reject-auto-approve
 * with {gate, reason}. Backend records the rejection as an audit entry with
 * auto_approved=false, rule_names=["user_override"], vetoes=[reason] — no separate
 * storage required.
 *
 * Route includes projectId per cycle-6 Lane V F1 fix: shot_id alone is not globally
 * unique (deterministic `shot_{scene}_{i}` collides across projects); pid-scoped
 * route mirrors the rest of the shot-mutation API surface.
 *
 * Submit is disabled until the reason textarea is non-empty.
 *
 * Follows the existing modal pattern in the project (no shared Modal component exists;
 * the inline overlay approach mirrors GenerationPanel and other overlay surfaces).
 */

import { useState } from 'react'

interface Props {
  projectId: string
  shotId: string
  gate: 'plan' | 'image' | 'motion' | 'final'
  isOpen: boolean
  onClose: () => void
  /** Called with the reason string after a successful POST — lets parent refresh. */
  onSubmit: (reason: string) => void
  apiBase?: string
}

const GATE_LABELS: Record<string, string> = {
  plan: 'Plan',
  image: 'Image',
  motion: 'Motion',
  final: 'Final',
}

export function RejectAutoApproveModal({
  projectId,
  shotId,
  gate,
  isOpen,
  onClose,
  onSubmit,
  apiBase = '/api',
}: Props) {
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isOpen) return null

  const handleSubmit = async () => {
    const trimmed = reason.trim()
    if (!trimmed) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch(`${apiBase}/projects/${projectId}/shots/${shotId}/reject-auto-approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gate, reason: trimmed }),
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        setError(data.error || `Server error ${res.status}`)
        return
      }
      onSubmit(trimmed)
      setReason('')
      onClose()
    } catch (err) {
      setError('Network error — please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onClose()
  }

  return (
    /* Overlay */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={onClose}
      onKeyDown={handleKeyDown}
      role="dialog"
      aria-modal="true"
      aria-label={`Reject auto-approve decision for ${GATE_LABELS[gate] ?? gate} gate`}
    >
      {/* Dialog panel — stops click from bubbling to overlay */}
      <div
        className="relative w-full max-w-md rounded-lg border border-line bg-app p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="mb-5">
          <div className="text-xs font-semibold uppercase tracking-wide text-mut mb-1">
            Override Auto-Approve
          </div>
          <h2 className="text-lg font-semibold text-tx">
            Reject {GATE_LABELS[gate] ?? gate} Gate Decision
          </h2>
          <p className="mt-2 text-sm text-mut">
            Provide a reason for overriding the auto-approve decision. This will be
            recorded in the shot's audit log as a user override.
          </p>
        </div>

        {/* Reason textarea */}
        <div className="mb-4">
          <label className="block text-xs font-semibold uppercase tracking-wide text-mut mb-2">
            Reason <span className="text-fail">*</span>
          </label>
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={4}
            placeholder="Describe why this auto-approve decision should be rejected…"
            className="w-full rounded border border-line bg-panel px-3 py-2 text-sm text-tx placeholder:text-mut focus:border-acc focus:outline-none"
            autoFocus
          />
        </div>

        {error && (
          <div className="mb-4 rounded border border-fail/40 bg-fail/10 px-3 py-2 text-sm text-fail">
            {error}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={submitting}
            className="rounded border border-line px-4 py-2 text-sm text-mut hover:bg-panel disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!reason.trim() || submitting}
            className="rounded border border-fail/50 bg-fail/10 px-4 py-2 text-sm text-fail hover:bg-fail/20 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? 'Submitting…' : 'Reject Decision'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default RejectAutoApproveModal
