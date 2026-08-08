/**
 * Whether the previous shot actually travelled with this one.
 *
 * `continuity_reference` — the approved keyframe of shot N-1 in the same scene
 * — reached NO hosted provider until 2026-08-08. The name appeared three times
 * in `phase_c_assembly.py` and fed only the local FLUX.2 worker, while the
 * default backend is `gemini_multiref`. Every shot after the first re-invented
 * the room's lighting and set dressing from prose.
 *
 * Now that it IS delivered, the case worth surfacing is when it was not. The
 * anchor can be dropped WITHOUT failing the call: a crowded multi-character
 * shot spends its whole reference budget on faces, an upload can fail, and the
 * text-to-image routes take no references at all. A scene that drifts is then
 * indistinguishable from one where the anchor was silently missing — which is
 * the difference between "regenerate this shot" and "this shot was never told".
 *
 * Success is deliberately silent. A banner on every correct shot is noise, and
 * noise is what makes the one meaningful banner invisible.
 */

interface Props {
  /** The anchor the shot HAD, if any. Empty on every scene's first shot, where
   *  there is no predecessor and nothing to report. */
  continuityReference?: string | null
  /** Whether it reached the provider. */
  delivered?: boolean
}

export default function ContinuityDeliveryNote({
  continuityReference,
  delivered,
}: Props) {
  if (!continuityReference) return null
  if (delivered) return null
  return (
    <div className="mt-3 rounded border border-line bg-panel px-3 py-2 text-xs leading-relaxed text-mut">
      <span className="text-tx">The previous shot was not sent with this one.</span>{' '}
      This scene&rsquo;s established lighting, palette and set dressing reached the
      model as words only. A crowded multi-character shot spends its whole
      reference budget on faces, and the text-to-image routes take no references
      at all — so if this frame does not match the shot before it, that is why,
      and it is not a generation fault.
    </div>
  )
}
