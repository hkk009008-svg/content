import { MICRO_LABEL } from './index'

/* Inline "action in progress" indicator. Distinct from LoadingState:
   LoadingState marks a slot that has no content yet because the initial
   fetch hasn't resolved; BusyState marks a section that already has content
   but is running an in-place action (regenerating a shot, saving a setting)
   -- so it renders as a small inline pill next to existing content rather
   than replacing a whole slot. Mirrors Button's own inline spinner (same
   border-current-spin shape) for a single-control busy affordance; use this
   one for a section/panel-level "this area is busy" state instead. */

interface Props {
  label?: string
  className?: string
}

export function BusyState({ label = 'Working', className = '' }: Props) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-busy="true"
      className={`inline-flex items-center gap-2 ${className}`}
    >
      <span
        aria-hidden
        className="inline-block w-3 h-3 border border-acc border-t-transparent rounded-full animate-spin"
      />
      <span className={MICRO_LABEL}>{label}</span>
    </div>
  )
}
