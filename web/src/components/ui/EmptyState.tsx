import { Button } from './Button'
import { MICRO_LABEL } from './index'

/* Editorial empty-state card. Used at page/section level when a list, panel,
   or slot has legitimately nothing in it yet (no scenes, no takes, no
   history) -- as opposed to LoadingState (still fetching) or ErrorState
   (fetch/action failed). Shares ErrorState's card grammar (micro-label +
   serif heading + message + optional hint/action) so the whole feedback
   family reads as one system; tokens are neutral (line/head/mut) instead of
   fail, and the live region is `status`/polite since an empty result is
   informational, never urgent. */

interface Props {
  title?: string
  message: string
  hint?: string
  action?: { label: string; onClick: () => void }
  className?: string
}

export function EmptyState({
  title = 'Nothing here yet',
  message,
  hint,
  action,
  className = '',
}: Props) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`border border-line bg-head/30 px-8 py-7 ${className}`}
    >
      <span className={MICRO_LABEL}>Empty</span>

      <h3
        className="font-display italic text-tx text-3xl leading-tight mt-3 mb-3"
        style={{ fontVariationSettings: '"opsz" 60, "SOFT" 60, "WONK" 1, "wght" 380' }}
      >
        {title}
      </h3>

      <p className="font-sans text-tx text-sm leading-relaxed mb-2">
        {message}
      </p>

      {hint && (
        <p className="font-mono text-eyebrow-lg text-mut tracking-wide-eyebrow uppercase mt-4">
          {hint}
        </p>
      )}

      {action && (
        <div className="flex items-center gap-3 mt-6">
          <Button variant="brass-outline" size="md" onClick={action.onClick}>
            {action.label}
          </Button>
        </div>
      )}
    </div>
  )
}
