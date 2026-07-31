/* Generic async-status announcer. The six feedback cards (LoadingState /
   EmptyState / ErrorState / OfflineState / BusyState / SuccessState) each
   carry their own live region already -- reach for this instead when a page
   needs to announce a transient async result that doesn't warrant a
   persistent visual banner (e.g. "3 of 5 shots regenerated"). Visually
   hidden by default (`sr-only`) since the announcement itself is the point;
   pass `visuallyHidden={false}` for a page that also wants it on-screen.

   `politeness="assertive"` renders `role="alert"` (implicit assertive, same
   convention ErrorState uses) instead of `role="status"` + `aria-live` --
   a screen reader announces role="alert" content immediately, so reserve
   assertive for something the user must not miss. */

interface Props {
  message: string
  politeness?: 'polite' | 'assertive'
  visuallyHidden?: boolean
  className?: string
}

export function LiveRegion({
  message,
  politeness = 'polite',
  visuallyHidden = true,
  className = '',
}: Props) {
  const role = politeness === 'assertive' ? 'alert' : 'status'
  return (
    <div
      role={role}
      aria-live={politeness}
      aria-atomic="true"
      className={[visuallyHidden ? 'sr-only' : '', className].filter(Boolean).join(' ')}
    >
      {message}
    </div>
  )
}
