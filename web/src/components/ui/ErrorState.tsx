import { Button } from './Button'
import { MICRO_LABEL } from './index'

/* Editorial failure card. Used at page/section level when a pipeline
   phase, request, or operation fails. The curtain accent signals the
   "alert" semantic without screaming. */

interface Props {
  title?: string
  message: string
  hint?: string
  onRetry?: () => void
  onDismiss?: () => void
  retryLabel?: string
  dismissLabel?: string
  className?: string
}

export function ErrorState({
  title = 'Something stopped the print',
  message,
  hint,
  onRetry,
  onDismiss,
  retryLabel = 'Retry',
  dismissLabel = 'Dismiss',
  className = '',
}: Props) {
  return (
    <div
      role="alert"
      aria-live="assertive"
      className={`border border-fail/50 bg-fail/[0.04]
                  px-8 py-7 ${className}`}
    >
      <span className={`${MICRO_LABEL.replace('text-mut', 'text-fail')} mb-3 block`}>Error</span>

      <h3
        className="font-display italic text-tx text-3xl leading-tight mb-3"
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

      {(onRetry || onDismiss) && (
        <div className="flex items-center gap-3 mt-6">
          {onRetry && (
            <Button variant="curtain" size="md" onClick={onRetry}>
              {retryLabel}
            </Button>
          )}
          {onDismiss && (
            <Button variant="ivory-ghost" size="md" onClick={onDismiss}>
              {dismissLabel}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
