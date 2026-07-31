import { Button } from './Button'
import { MICRO_LABEL } from './index'

/* Editorial success/confirmation card. Positive-outcome sibling of
   ErrorState/OfflineState/EmptyState -- same card grammar, `ok` tokens,
   `status`/polite live region (a confirmation is informational, never
   urgent enough to interrupt). */

interface Props {
  title?: string
  message: string
  hint?: string
  onDismiss?: () => void
  dismissLabel?: string
  className?: string
}

export function SuccessState({
  title = 'Done',
  message,
  hint,
  onDismiss,
  dismissLabel = 'Dismiss',
  className = '',
}: Props) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`border border-ok/50 bg-ok/[0.06] px-8 py-7 ${className}`}
    >
      <span className={MICRO_LABEL.replace('text-mut', 'text-ok')}>Success</span>

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

      {onDismiss && (
        <div className="flex items-center gap-3 mt-6">
          <Button variant="ivory-ghost" size="md" onClick={onDismiss}>
            {dismissLabel}
          </Button>
        </div>
      )}
    </div>
  )
}
