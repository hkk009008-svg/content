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
 * Uses the shared Dialog primitive for initial focus, trapped keyboard focus,
 * Escape/overlay dismissal, scroll locking, and opener-focus restoration.
 */

import { useId, useRef, useState } from 'react'
import { Dialog } from '../ui'

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
  const reasonId = useId()
  const reasonRef = useRef<HTMLTextAreaElement>(null)

  if (!isOpen) return null

  const handleSubmit = async () => {
    const trimmed = reason.trim()
    if (!trimmed) return
    setSubmitting(true)
    setError(null)
    try {
      const res = await fetch(`${apiBase}/projects/${encodeURIComponent(projectId)}/shots/${encodeURIComponent(shotId)}/reject-auto-approve`, {
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
    } catch {
      setError('Network error — please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      closeOnEscape={!submitting}
      closeOnOverlayClick={!submitting}
      aria-label={`Reject auto-approve decision for ${GATE_LABELS[gate] ?? gate} gate`}
      initialFocusRef={reasonRef}
      className="max-w-md"
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

      <form
        onSubmit={(event) => {
          event.preventDefault()
          void handleSubmit()
        }}
      >
        {/* Reason textarea */}
        <div className="mb-4">
          <label
            htmlFor={reasonId}
            className="block text-xs font-semibold uppercase tracking-wide text-mut mb-2"
          >
            Reason <span className="text-fail">*</span>
          </label>
          <textarea
            ref={reasonRef}
            id={reasonId}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={4}
            required
            aria-required="true"
            placeholder="Describe why this auto-approve decision should be rejected…"
            className="w-full rounded border border-line bg-panel px-3 py-2 text-sm text-tx placeholder:text-mut focus:border-acc focus:outline-none"
          />
        </div>

        {error && (
          <div role="alert" className="mb-4 rounded border border-fail/40 bg-fail/10 px-3 py-2 text-sm text-fail">
            {error}
          </div>
        )}

        {/* Action buttons */}
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded border border-line px-4 py-2 text-sm text-mut hover:bg-panel disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!reason.trim() || submitting}
            className="rounded border border-fail/50 bg-fail/10 px-4 py-2 text-sm text-fail hover:bg-fail/20 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? 'Submitting…' : 'Reject Decision'}
          </button>
        </div>
      </form>
    </Dialog>
  )
}

export default RejectAutoApproveModal
