import type { DirectorReview } from '../../types/project'

interface Props {
  review: DirectorReview | null
}

export default function DirectorReviewCard({ review }: Props) {
  if (!review) return null

  const decisionStyles = {
    APPROVED: { bg: 'bg-editorial-ready/10', border: 'border-editorial-ready/30', text: 'text-editorial-ready', icon: '✓' },
    MODIFIED: { bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', text: 'text-yellow-400', icon: '✎' },
    REJECTED: { bg: 'bg-editorial-curtain/10', border: 'border-editorial-curtain/30', text: 'text-editorial-curtain', icon: '✕' },
  }

  const style = decisionStyles[review.decision] || decisionStyles.APPROVED

  return (
    <div className={`${style.bg} border ${style.border} rounded-lg px-4 py-3 mb-3`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">{style.icon}</span>
          <span className={`font-bold text-sm ${style.text}`}>
            Chief Director: {review.decision}
          </span>
          {review.quality_score > 0 && (
            <span className="text-eyebrow text-editorial-ivory-mute bg-editorial-ink px-2 py-0.5 rounded">
              Quality: {Math.round(review.quality_score * 100)}%
            </span>
          )}
        </div>
      </div>
      {review.reasoning && (
        <p className="text-xs text-editorial-ivory/70 mt-2">{review.reasoning}</p>
      )}
      {review.violations.length > 0 && (
        <div className="mt-2 space-y-0.5">
          {review.violations.map((v, i) => (
            <p key={i} className="text-eyebrow text-editorial-curtain/80 font-mono">• {v}</p>
          ))}
        </div>
      )}
    </div>
  )
}
