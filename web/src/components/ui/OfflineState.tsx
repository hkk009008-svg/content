import { Button } from './Button'
import { MICRO_LABEL } from './index'

/* Editorial offline/connectivity card. Distinct from ErrorState: ErrorState
   is for a request the server actively rejected (a validated non-2xx
   response); OfflineState is for `lib/api.ts`'s `status === 0` case -- the
   request never reached the server at all (network failure, CORS, aborted,
   or the machine is genuinely offline). Pages should branch on
   `result.status === 0` to choose OfflineState over ErrorState so the
   message matches what actually happened.

   Uses `warn` tokens (not `fail`) and a `status`/polite live region (not
   `alert`/assertive) deliberately: connectivity loss is often transient and
   self-resolving (see `hooks/useSSE.ts`'s own reconnect backoff), so it
   should inform without interrupting the way a hard failure does. */

interface Props {
  title?: string
  message?: string
  hint?: string
  onRetry?: () => void
  retryLabel?: string
  className?: string
}

export function OfflineState({
  title = 'Connection lost',
  message = "Can't reach the server. Check your connection and try again.",
  hint,
  onRetry,
  retryLabel = 'Retry',
  className = '',
}: Props) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`border border-warn/50 bg-warn/[0.06] px-8 py-7 ${className}`}
    >
      <span className={MICRO_LABEL.replace('text-mut', 'text-warn')}>Offline</span>

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

      {onRetry && (
        <div className="flex items-center gap-3 mt-6">
          <Button variant="brass-outline" size="md" onClick={onRetry}>
            {retryLabel}
          </Button>
        </div>
      )}
    </div>
  )
}
