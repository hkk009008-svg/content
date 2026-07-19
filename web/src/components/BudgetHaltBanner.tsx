import type { ProgressEvent } from '../types/project'

/** Budget-halt banner — sticky surface for BUDGET_EXCEEDED (P1-3).
 *
 *  Owned by App.tsx state, NOT keyed on `latest`: the motion-phase abort
 *  emits MOTION_HALTED immediately after the halt event, which would flash a
 *  latest-keyed banner away. Historically rendered in BOTH the old
 *  `pipeline/PipelineLayout` (where the operator actually is when the
 *  per-take gate fires mid-run) and the old `EditorialShell` (setup mode) —
 *  the wf_9877b1d1 review found the original shell-only placement unreachable
 *  in the primary flow because starting a run unmounted the shell. Since
 *  Task 13's `AppShell` (a single persistent shell that never unmounts across
 *  page switches), it renders once, in AppShell's always-mounted top region —
 *  both predecessor components are deleted. */
export default function BudgetHaltBanner({
  event,
  onDismiss,
}: {
  event: ProgressEvent
  onDismiss: () => void
}) {
  const amounts =
    typeof event.spent === 'number' && typeof event.budget === 'number'
      ? ` — spent $${event.spent.toFixed(2)} of $${event.budget.toFixed(2)}`
      : ''
  return (
    <div
      role="alert"
      className="border-y border-fail/60 bg-fail/10 px-10 py-3 flex items-center justify-between gap-4"
    >
      <div className="font-mono text-eyebrow-lg text-fail tracking-wide-eyebrow uppercase">
        Budget cap reached{amounts}. Motion halted — raise the budget in
        Settings and regenerate.
      </div>
      <button
        onClick={onDismiss}
        className="font-mono text-eyebrow text-mut hover:text-tx uppercase shrink-0"
      >
        Dismiss
      </button>
    </div>
  )
}
