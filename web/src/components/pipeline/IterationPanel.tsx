import { useState } from 'react'

/** S17 + S18: Directorial iteration panel — CINEMA_DIRECTORIAL_ITERATION feature gate.
 *
 * Rendered as an inline drawer inside a take-card (keyframe / performance / final)
 * when the operator clicks "Iterate" at the matching review gate. Accepts freeform
 * prose AND (S18) an optional structured verb + params; submits a POST to the
 * iterate endpoint with a flat body `{ prose, target_stage, verb?, params? }`.
 *
 * Design decisions:
 * - Inline drawer (not a modal overlay) — less disruptive for a per-take action.
 * - Round-trip wait: panel shows a spinner during the ~5-15s LLM call, closes
 *   on success, stays open on error with an inline message.
 * - 404 (feature flag off) surfaces a sensible inline error — the Iterate button
 *   is shown regardless; we don't have client-side knowledge of the server flag.
 * - Palette: editorial-* only (no console-* classes).
 *
 * S18 verb-picker UX:
 * - Default state mirrors S17 exactly (freeform-only). An "Add structured verb"
 *   button reveals the picker so operators who don't need verbs see no extra UI.
 * - Three verbs: tighten_framing / match_shot / shift_emotion (see llm/director.py
 *   KNOWN_VERBS). Unknown verbs degrade to freeform server-side; we never send
 *   one from the picker.
 * - Param widgets render below the verb dropdown when a verb is selected.
 */

type Verb = 'tighten_framing' | 'match_shot' | 'shift_emotion'

interface Props {
  /** S18: parent receives (prose, verb?, params?). target_stage is bound by the
   *  caller's closure (varies by which card the panel is rendered inside). */
  onSubmit: (prose: string, verb?: Verb, params?: Record<string, unknown>) => Promise<any>
  onCancel: () => void
}

const TIGHTEN_DEGREES: Array<{ id: 'subtle' | 'moderate' | 'strong'; label: string }> = [
  { id: 'subtle', label: 'Subtle' },
  { id: 'moderate', label: 'Moderate' },
  { id: 'strong', label: 'Strong' },
]

const SHIFT_DIRECTIONS: Array<{ id: 'soften' | 'intensify'; label: string }> = [
  { id: 'soften', label: 'Soften' },
  { id: 'intensify', label: 'Intensify' },
]

const SHIFT_TARGETS: Array<{ id: 'subtle' | 'noticeable'; label: string }> = [
  { id: 'subtle', label: 'Subtle' },
  { id: 'noticeable', label: 'Noticeable' },
]

const MATCH_ATTRS: Array<'lighting' | 'mood' | 'composition'> = [
  'lighting',
  'mood',
  'composition',
]

export default function IterationPanel({ onSubmit, onCancel }: Props) {
  const [prose, setProse] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // S18 verb picker — collapsed by default to preserve S17 UX.
  const [verbPickerOpen, setVerbPickerOpen] = useState(false)
  const [verb, setVerb] = useState<Verb | ''>('')

  // Per-verb param state (independent so toggling verbs preserves prior picks)
  const [tightenDegree, setTightenDegree] = useState<'subtle' | 'moderate' | 'strong'>('moderate')
  const [matchRefShotId, setMatchRefShotId] = useState('')
  const [matchAttrs, setMatchAttrs] = useState<Set<'lighting' | 'mood' | 'composition'>>(
    new Set(['lighting'])
  )
  const [shiftDirection, setShiftDirection] = useState<'soften' | 'intensify'>('soften')
  const [shiftTarget, setShiftTarget] = useState<'subtle' | 'noticeable'>('subtle')

  const buildParams = (): Record<string, unknown> => {
    if (verb === 'tighten_framing') return { degree: tightenDegree }
    if (verb === 'match_shot') {
      return {
        ref_shot_id: matchRefShotId.trim(),
        attributes: Array.from(matchAttrs),
      }
    }
    if (verb === 'shift_emotion') return { direction: shiftDirection, target: shiftTarget }
    return {}
  }

  // Verb-specific submit gates — match_shot requires a ref id, the rest don't.
  const verbReady = verb === '' || verb !== 'match_shot' || matchRefShotId.trim().length > 0

  const handleSubmit = async () => {
    const trimmed = prose.trim()
    if (!trimmed || !verbReady) return
    setSubmitting(true)
    setError(null)
    try {
      const result = verb === ''
        ? await onSubmit(trimmed)
        : await onSubmit(trimmed, verb, buildParams())
      if (result?.error) {
        setError(result.error)
      }
      setSubmitting(false)
    } catch {
      setError('Something went wrong. Please try again.')
      setSubmitting(false)
    }
  }

  const toggleMatchAttr = (attr: 'lighting' | 'mood' | 'composition') => {
    setMatchAttrs((prev) => {
      const next = new Set(prev)
      if (next.has(attr)) {
        if (next.size > 1) next.delete(attr) // never empty the set
      } else {
        next.add(attr)
      }
      return next
    })
  }

  return (
    <div className="mt-2 space-y-2 rounded border border-editorial-brass/30 bg-editorial-ink-soft px-3 py-3">
      <div className="text-eyebrow-lg font-semibold uppercase tracking-wide text-editorial-brass">
        Directorial Iteration
      </div>
      <p className="text-eyebrow text-editorial-ivory-mute">
        Describe how you want this take changed. A new take will be generated with your direction applied.
      </p>
      <textarea
        value={prose}
        onChange={(e) => setProse(e.target.value)}
        rows={3}
        placeholder="e.g. tighten the framing on the face, warmer lighting, less motion blur…"
        disabled={submitting}
        aria-label="Directorial iteration prose"
        className="w-full rounded border border-editorial-rule bg-editorial-ink px-2 py-1.5 text-xs text-editorial-ivory placeholder-editorial-ivory-mute disabled:opacity-60"
      />

      {/* S18: optional structured verb picker. Hidden until operator opts in. */}
      {!verbPickerOpen ? (
        <button
          type="button"
          onClick={() => setVerbPickerOpen(true)}
          disabled={submitting}
          className="text-eyebrow text-editorial-brass hover:text-editorial-brass-deep disabled:opacity-40"
        >
          + Add structured verb (optional)
        </button>
      ) : (
        <div className="space-y-2 rounded border border-editorial-rule bg-editorial-ink px-2 py-2">
          <div className="flex items-center gap-2">
            <label htmlFor="iterate-verb" className="text-eyebrow text-editorial-ivory-mute">
              Verb
            </label>
            <select
              id="iterate-verb"
              value={verb}
              onChange={(e) => setVerb(e.target.value as Verb | '')}
              disabled={submitting}
              className="rounded border border-editorial-rule bg-editorial-ink-soft px-2 py-1 text-xs text-editorial-ivory disabled:opacity-60"
            >
              <option value="">Freeform (no verb)</option>
              <option value="tighten_framing">Tighten framing</option>
              <option value="match_shot">Match shot</option>
              <option value="shift_emotion">Shift emotion</option>
            </select>
            <button
              type="button"
              onClick={() => { setVerb(''); setVerbPickerOpen(false) }}
              disabled={submitting}
              className="ml-auto text-eyebrow text-editorial-ivory-mute hover:text-editorial-ivory disabled:opacity-40"
            >
              Hide
            </button>
          </div>

          {verb === 'tighten_framing' && (
            <div className="flex items-center gap-2">
              <span className="text-eyebrow text-editorial-ivory-mute">Degree</span>
              <div className="inline-flex rounded border border-editorial-rule">
                {TIGHTEN_DEGREES.map((d, i) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => setTightenDegree(d.id)}
                    disabled={submitting}
                    aria-pressed={tightenDegree === d.id}
                    className={`px-2 py-1 text-eyebrow ${
                      tightenDegree === d.id
                        ? 'bg-editorial-brass/30 text-editorial-brass'
                        : 'text-editorial-ivory-mute hover:bg-editorial-ink-rise'
                    } ${i > 0 ? 'border-l border-editorial-rule' : ''} disabled:opacity-40`}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {verb === 'match_shot' && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <label htmlFor="iterate-match-ref" className="text-eyebrow text-editorial-ivory-mute whitespace-nowrap">
                  Ref shot id
                </label>
                <input
                  id="iterate-match-ref"
                  value={matchRefShotId}
                  onChange={(e) => setMatchRefShotId(e.target.value)}
                  placeholder="e.g. shot_1_2"
                  disabled={submitting}
                  className="flex-1 rounded border border-editorial-rule bg-editorial-ink-soft px-2 py-1 text-xs text-editorial-ivory font-mono disabled:opacity-60"
                />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-eyebrow text-editorial-ivory-mute">Match</span>
                <div className="flex gap-2">
                  {MATCH_ATTRS.map((attr) => (
                    <label key={attr} className="flex items-center gap-1 text-eyebrow text-editorial-ivory cursor-pointer">
                      <input
                        type="checkbox"
                        checked={matchAttrs.has(attr)}
                        onChange={() => toggleMatchAttr(attr)}
                        disabled={submitting}
                        className="h-3 w-3"
                      />
                      {attr}
                    </label>
                  ))}
                </div>
              </div>
              {matchRefShotId.trim() === '' && (
                <div className="text-eyebrow text-editorial-warn">
                  Ref shot id is required for the match_shot verb.
                </div>
              )}
            </div>
          )}

          {verb === 'shift_emotion' && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-2">
                <span className="text-eyebrow text-editorial-ivory-mute">Direction</span>
                <div className="inline-flex rounded border border-editorial-rule">
                  {SHIFT_DIRECTIONS.map((d, i) => (
                    <button
                      key={d.id}
                      type="button"
                      onClick={() => setShiftDirection(d.id)}
                      disabled={submitting}
                      aria-pressed={shiftDirection === d.id}
                      className={`px-2 py-1 text-eyebrow ${
                        shiftDirection === d.id
                          ? 'bg-editorial-brass/30 text-editorial-brass'
                          : 'text-editorial-ivory-mute hover:bg-editorial-ink-rise'
                      } ${i > 0 ? 'border-l border-editorial-rule' : ''} disabled:opacity-40`}
                    >
                      {d.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-eyebrow text-editorial-ivory-mute">Target</span>
                <div className="inline-flex rounded border border-editorial-rule">
                  {SHIFT_TARGETS.map((t, i) => (
                    <button
                      key={t.id}
                      type="button"
                      onClick={() => setShiftTarget(t.id)}
                      disabled={submitting}
                      aria-pressed={shiftTarget === t.id}
                      className={`px-2 py-1 text-eyebrow ${
                        shiftTarget === t.id
                          ? 'bg-editorial-brass/30 text-editorial-brass'
                          : 'text-editorial-ivory-mute hover:bg-editorial-ink-rise'
                      } ${i > 0 ? 'border-l border-editorial-rule' : ''} disabled:opacity-40`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="rounded border border-editorial-curtain/40 bg-editorial-curtain/10 px-2 py-1.5 text-eyebrow text-editorial-curtain">
          {error}
        </div>
      )}
      <div className="flex gap-2">
        <button
          onClick={handleSubmit}
          disabled={submitting || !prose.trim() || !verbReady}
          className="rounded bg-editorial-brass px-3 py-1.5 text-xs font-semibold text-white hover:bg-editorial-brass/90 disabled:opacity-40"
        >
          {submitting ? 'Generating…' : 'Generate New Take'}
        </button>
        <button
          onClick={onCancel}
          disabled={submitting}
          className="rounded border border-editorial-rule px-3 py-1.5 text-xs text-editorial-ivory-mute hover:bg-editorial-ink-rise disabled:opacity-40"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
