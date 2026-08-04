import type { DirectorReview } from '../../types/project'

interface Props {
  review: DirectorReview | null
}

export default function DirectorReviewCard({ review }: Props) {
  if (!review) return null

  const decisionStyles = {
    APPROVED: { bg: 'bg-ok/10', border: 'border-ok/30', text: 'text-ok', icon: '✓' },
    MODIFIED: { bg: 'bg-warn/10', border: 'border-warn/30', text: 'text-warn', icon: '✎' },
    REJECTED: { bg: 'bg-fail/10', border: 'border-fail/30', text: 'text-fail', icon: '✕' },
    REVIEW_REQUIRED: { bg: 'bg-warn/10', border: 'border-warn/40', text: 'text-warn', icon: '!' },
  } as const

  const rawDecision = typeof review.decision === 'string' && review.decision.trim()
    ? review.decision.trim().toUpperCase()
    : 'UNKNOWN'
  const isKnownDecision = Object.prototype.hasOwnProperty.call(decisionStyles, rawDecision)
  const decision = isKnownDecision
    ? rawDecision as keyof typeof decisionStyles
    : 'REVIEW_REQUIRED'
  const style = decisionStyles[decision]
  const requiresManualReview = decision === 'REVIEW_REQUIRED'
  const violations = Array.isArray(review.violations)
    ? review.violations.filter((violation): violation is string => typeof violation === 'string' && violation.length > 0)
    : []
  const reasoning = typeof review.reasoning === 'string' && review.reasoning.trim()
    ? review.reasoning.trim()
    : null
  const hasQualityScore = typeof review.quality_score === 'number' && Number.isFinite(review.quality_score)

  return (
    <div
      className={`${style.bg} border ${style.border} rounded-lg px-4 py-3 mb-3`}
      role={requiresManualReview ? 'alert' : 'status'}
      data-review-state={requiresManualReview ? 'manual-required' : decision.toLowerCase()}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg" aria-hidden="true">{style.icon}</span>
          <span className={`font-bold text-sm ${style.text}`}>
            Chief Director: {isKnownDecision ? rawDecision : `UNRECOGNIZED (${rawDecision})`}
          </span>
          {hasQualityScore && (
            <span className="text-eyebrow text-mut bg-app px-2 py-0.5 rounded">
              Quality: {Math.round(review.quality_score! * 100)}%
            </span>
          )}
        </div>
      </div>
      {requiresManualReview && (
        <p className="mt-2 text-xs font-semibold text-warn">
          {isKnownDecision
            ? 'No valid approval decision was produced. Manual review is required.'
            : 'This decision is not recognized and is being treated as review required.'}
        </p>
      )}
      {reasoning && (
        <p className="text-xs text-tx/70 mt-2">{reasoning}</p>
      )}
      {violations.length > 0 && (
        <div className="mt-2 space-y-0.5">
          {violations.map((v, i) => (
            <p key={i} className="text-eyebrow text-fail/80 font-mono">• {v}</p>
          ))}
        </div>
      )}
    </div>
  )
}
