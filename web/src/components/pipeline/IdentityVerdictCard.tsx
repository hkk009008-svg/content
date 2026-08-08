/**
 * What the identity gate actually established, and what it did not.
 *
 * The card this replaces was headed "Identity Remediation Advisory" and printed
 * the failure reason as a diagnosis. Three things make that dishonest:
 *
 * 1. ADR-092 — THE SCORER INVERTS RANK OFF-ANGLE. A real photograph of the
 *    subject in profile scored 0.556 and "failed" the 0.70 portrait gate, while
 *    a generated panel the subject confirmed was NOT him scored 0.570. Below
 *    roughly 0.65 the comparison carries no ordering, so a failure there is the
 *    instrument's floor and not a fact about the take. Acting on it costs a
 *    re-render of footage that was fine.
 *
 * 2. THE DETECTOR CANNOT FIND A TURNED FACE AT ALL. Measured this session: the
 *    largest detection on the subject's real profile photograph was 96x96 —
 *    0.076% of the frame. So on a genuinely turned shot the reason arrives as
 *    NO_FACE_DETECTED, which is a statement about the detector, not the actor.
 *
 * 3. POOR_LIGHTING IS THE ELSE-BRANCH. `IdentityValidator._classify_failure`
 *    returns it when no other test matched (identity/validator.py:1308,1341).
 *    Rendering "poor lighting" for "the classifier ran out of branches" asserts
 *    a measurement nobody made.
 *
 * The one pose signal that IS independent of similarity is the detection box's
 * width/height ratio (`_estimate_face_angle`, validator.py:1310-1322). It is
 * crude, and the card says so rather than presenting it as head-pose estimation.
 */

import type { ReactNode } from 'react'

export type IdentityFailureReason =
  | 'no_face_detected'
  | 'low_confidence_detection'
  | 'face_angle_extreme'
  | 'occlusion'
  | 'wrong_person'
  | 'multiple_faces_ambiguous'
  | 'small_face_region'
  | 'poor_lighting'
  | 'identity_unverified'
  | 'generated_image_missing'
  | 'video_zero_frames'
  | 'passed'

interface Verdict {
  /** What the headline may claim. `unjudged` means the gate produced no
   *  ordering, so the card must not imply the take is bad. */
  standing: 'unjudged' | 'suspect' | 'broken'
  headline: string
  detail: string
}

const VERDICTS: Record<string, Verdict> = {
  no_face_detected: {
    standing: 'unjudged',
    headline: 'The gate could not judge this take',
    detail:
      'No face was located to compare. The detector loses a face as it turns '
      + 'away or gets small — on this project the largest detection in a real '
      + 'profile photograph was 96x96 pixels, 0.076% of the frame. That is a '
      + 'fact about the detector, not about the shot.',
  },
  small_face_region: {
    standing: 'unjudged',
    headline: 'The gate could not judge this take',
    detail:
      'The face covers under 1% of the frame. For a wide or establishing shot '
      + 'that is correct framing, and there is not enough face for the '
      + 'comparison to mean anything either way.',
  },
  face_angle_extreme: {
    standing: 'unjudged',
    headline: 'The gate could not judge this pose',
    detail:
      'The detection box was wider-than-tall enough to read as turned — the '
      + 'only pose signal available here, and a crude one. The scorer floors '
      + 'and REVERSES on turned views: a real photograph of the subject in '
      + 'profile scored 0.556 while a generated stranger scored 0.570. A number '
      + 'from this comparison cannot rank the take.',
  },
  low_confidence_detection: {
    standing: 'unjudged',
    headline: 'The gate could not judge this take',
    detail:
      'The detector was under 40% confident it had found a face at all, so '
      + 'whatever it then compared may not have been the face.',
  },
  poor_lighting: {
    standing: 'unjudged',
    headline: 'The gate reported no specific cause',
    detail:
      'This is the classifier’s else-branch, not a lighting measurement: it '
      + 'is returned when no other test matched (identity/validator.py:1308). '
      + 'Nothing here has established a reason.',
  },
  occlusion: {
    standing: 'unjudged',
    headline: 'The gate could not judge this take',
    detail: 'Part of the face was covered, so the comparison saw an incomplete face.',
  },
  multiple_faces_ambiguous: {
    standing: 'suspect',
    headline: 'More than one face in frame',
    detail:
      'The gate could not tell which face to score. Check that the intended '
      + 'character is the one being measured before reading anything into it.',
  },
  wrong_person: {
    standing: 'suspect',
    headline: 'The face may not be this character',
    detail:
      'The best frame scored under 0.35 — well below the 0.53-0.58 band where '
      + 'this scorer is known to lose its ordering, so this one is worth '
      + 'looking at. Confirm by eye; the gate is not the authority.',
  },
  generated_image_missing: {
    standing: 'broken',
    headline: 'No image was produced',
    detail: 'The provider reported completion but no publishable image was found.',
  },
  video_zero_frames: {
    standing: 'broken',
    headline: 'The video has no frames',
    detail: 'Nothing could be sampled, so nothing was compared.',
  },
  identity_unverified: {
    standing: 'unjudged',
    headline: 'Identity was never checked',
    detail: 'No reference was available to compare against.',
  },
}

const FALLBACK: Verdict = {
  standing: 'unjudged',
  headline: 'The gate could not judge this take',
  detail: 'The reason it reported is not one this card recognises.',
}

export function verdictFor(reason: string | null | undefined): Verdict {
  if (!reason) return FALLBACK
  return VERDICTS[reason] ?? FALLBACK
}

interface Props {
  failureReason: string | null | undefined
  /** The reference the gate actually compared against — usually ONE frontal
   *  image, which is the whole reason a turned take cannot be judged. */
  comparedAgainst?: string | null
  /** Open the reference sheet. A gate that cannot judge a pose is usually
   *  telling you the SET lacks that pose, which is the fixable half. */
  onOpenReferenceSheet?: () => void
  /** Priced, and last. Regenerating on an unjudgeable verdict spends money to
   *  replace footage nothing established was wrong. */
  onRegenerate?: () => void
  regenerateCostUsd?: number | null
  children?: ReactNode
}

const TONE: Record<Verdict['standing'], string> = {
  unjudged: 'border-line bg-panel',
  suspect: 'border-warn/30 bg-warn/5',
  broken: 'border-fail/30 bg-fail/5',
}

export default function IdentityVerdictCard({
  failureReason,
  comparedAgainst,
  onOpenReferenceSheet,
  onRegenerate,
  regenerateCostUsd,
  children,
}: Props) {
  if (!failureReason || failureReason === 'passed') return null
  const verdict = verdictFor(failureReason)
  const basename = comparedAgainst ? comparedAgainst.split('/').pop() : null

  return (
    <div className={`mt-3 space-y-2 rounded border px-3 py-3 text-xs ${TONE[verdict.standing]}`}>
      <div className="text-eyebrow-lg font-semibold uppercase tracking-wide text-tx">
        {verdict.headline}
      </div>
      <p className="leading-relaxed text-mut">{verdict.detail}</p>

      <p className="text-mut">
        Compared against{' '}
        {basename ? <code className="text-tx">{basename}</code> : 'the character’s canonical reference'}
        {' '}— a single image. Every reference the character has is listed on the
        Reference sheet, along with which ones each provider actually receives.
      </p>

      {verdict.standing === 'unjudged' && (
        <p className="leading-relaxed text-mut">
          <strong className="text-tx">Nothing here says the take is bad.</strong>{' '}
          Judge it by eye. If it looks right, keep it.
        </p>
      )}

      {children}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        {onOpenReferenceSheet && (
          <button
            onClick={onOpenReferenceSheet}
            className="rounded border border-line px-2 py-1 text-eyebrow uppercase tracking-wide text-mut hover:text-tx"
          >
            Open reference sheet
          </button>
        )}
        {onRegenerate && (
          <button
            onClick={onRegenerate}
            className="rounded border border-line px-2 py-1 text-eyebrow uppercase tracking-wide text-mut hover:text-tx"
          >
            Regenerate
            {typeof regenerateCostUsd === 'number' && (
              <span className="ml-1 text-warn">${regenerateCostUsd.toFixed(2)}</span>
            )}
          </button>
        )}
      </div>
    </div>
  )
}
