import { useState } from 'react'

/** S17: Directorial iteration panel — CINEMA_DIRECTORIAL_ITERATION feature gate.
 *
 * Rendered as an inline drawer inside the keyframe take-card when the operator
 * clicks "Iterate" at KEYFRAME_REVIEW. Accepts freeform prose describing the
 * desired change; submits a POST to the iterate endpoint with a flat body
 * `{ prose, target_stage: "keyframe" }`.
 *
 * Design decisions (per S17 brief):
 * - Inline drawer (not a modal overlay) — less disruptive for a per-take action.
 * - Round-trip wait: panel shows a spinner during the ~5-15s LLM call, closes
 *   on success, stays open on error with an inline message.
 * - 404 (feature flag off) surfaces a sensible inline error — the Iterate button
 *   is shown regardless; we don't have client-side knowledge of the server flag.
 * - Palette: editorial-* only (no console-* classes).
 */

interface Props {
  shotId: string
  takeId: string
  onSubmit: (prose: string) => Promise<any>
  onCancel: () => void
}

export default function IterationPanel({ shotId: _shotId, takeId: _takeId, onSubmit, onCancel }: Props) {
  const [prose, setProse] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    const trimmed = prose.trim()
    if (!trimmed) return
    setSubmitting(true)
    setError(null)
    try {
      const result = await onSubmit(trimmed)
      // onSubmit resolves on success; the parent re-renders with new take data.
      // Check for explicit error shapes returned by the endpoint.
      if (result?.error) {
        setError(result.error)
        setSubmitting(false)
      }
      // On success the parent closes this panel via state update; no explicit
      // close needed here — but if onSubmit resolves without triggering a
      // close, guard against hanging in submitting state.
    } catch {
      setError('Something went wrong. Please try again.')
      setSubmitting(false)
    }
  }

  return (
    <div className="mt-2 space-y-2 rounded border border-editorial-brass/30 bg-editorial-ink-soft px-3 py-3">
      <div className="text-eyebrow-lg font-semibold uppercase tracking-wide text-editorial-brass">
        Directorial Iteration
      </div>
      <p className="text-eyebrow text-editorial-ivory-mute">
        Describe how you want this keyframe changed. A new take will be generated with your direction applied.
      </p>
      <textarea
        value={prose}
        onChange={(e) => setProse(e.target.value)}
        rows={3}
        placeholder="e.g. tighten the framing on the face, warmer lighting, less motion blur…"
        disabled={submitting}
        className="w-full rounded border border-editorial-rule bg-editorial-ink px-2 py-1.5 text-xs text-editorial-ivory placeholder-editorial-ivory-mute disabled:opacity-60"
      />
      {error && (
        <div className="rounded border border-editorial-curtain/40 bg-editorial-curtain/10 px-2 py-1.5 text-eyebrow text-editorial-curtain">
          {error}
        </div>
      )}
      <div className="flex gap-2">
        <button
          onClick={handleSubmit}
          disabled={submitting || !prose.trim()}
          className="rounded bg-editorial-brass px-3 py-1.5 text-xs font-semibold text-white hover:bg-editorial-brass/90 disabled:opacity-40"
        >
          {submitting ? 'Generating…' : 'Generate New Take'}
        </button>
        <button
          onClick={onCancel}
          disabled={submitting}
          className="rounded border border-editorial-rule px-3 py-1.5 text-xs text-editorial-ivory-mute hover:bg-editorial-ink-rise disabled:opacity-40"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
