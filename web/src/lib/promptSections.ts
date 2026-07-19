/**
 * Structured `[TAG] text` prompt sections — parse/assemble helpers shared by
 * every editor that reads or writes a shot's `prompt` string.
 *
 * Extracted from `pipeline/PromptEditor.tsx`'s original `parseStructured` /
 * `assembleSections` (the section-tag regex is copied verbatim) so
 * `PromptEditor`, `ShotRow`, and the new `edit/ShotInspector` share one
 * implementation instead of three drifting copies.
 */

export const PROMPT_SECTION_TAGS = ['SHOT', 'SCENE', 'ACTION', 'OUTFIT', 'QUALITY'] as const
export type PromptSectionTag = (typeof PROMPT_SECTION_TAGS)[number]

/**
 * Parse `[SHOT][SCENE][ACTION][OUTFIT][QUALITY]` sections out of a shot
 * prompt string.
 *
 * `fallbackToScene` (default false): when true and no bracketed section was
 * found, the entire prompt is placed under `SCENE` — this was
 * `PromptEditor`'s original behavior (it always renders 5 section
 * textareas, so an unstructured legacy prompt needs a home). Callers that
 * render their own "no structured sections" fallback (e.g. `ShotRow`'s raw
 * truncated-prompt line) should leave this false to preserve that branch.
 */
export function parsePromptSections(prompt: string, fallbackToScene = false): Record<string, string> {
  const sections: Record<string, string> = {}
  for (const tag of PROMPT_SECTION_TAGS) {
    const match = prompt.match(
      new RegExp(`\\[${tag}\\]\\s*(.+?)(?=\\[(?:${PROMPT_SECTION_TAGS.join('|')})\\]|$)`, 's'),
    )
    if (match) sections[tag] = match[1].trim()
  }
  if (fallbackToScene && Object.keys(sections).length === 0) {
    sections['SCENE'] = prompt
  }
  return sections
}

/** Re-assemble parsed sections back into a single `[TAG] text [TAG] text …`
 *  prompt string, dropping empty sections. */
export function assemblePromptSections(sections: Record<string, string>): string {
  return Object.entries(sections)
    .filter(([, v]) => v.trim())
    .map(([k, v]) => `[${k}] ${v}`)
    .join(' ')
}

/** Per-tag display metadata (label, legacy accent color, placeholder copy)
 *  used by `PromptEditor`'s modal. Kept here alongside the parser so the two
 *  stay in sync; new token-styled UIs (e.g. `edit/ShotInspector`) should NOT
 *  reuse `color` (it's a legacy non-token Tailwind palette class) — style
 *  section labels with `MICRO_LABEL`/tokens instead. */
export const SECTION_LABELS: Record<PromptSectionTag, { label: string; color: string; placeholder: string }> = {
  SHOT: { label: 'Camera', color: 'text-cyan-400', placeholder: 'e.g. Medium shot, 85mm f/1.4 lens, shallow DoF' },
  SCENE: { label: 'Scene', color: 'text-indigo-400', placeholder: 'e.g. Snowy park with bare trees, overcast sky, 4500K' },
  ACTION: { label: 'Action', color: 'text-amber-400', placeholder: 'e.g. Walking toward camera, looking directly at camera' },
  OUTFIT: { label: 'Outfit', color: 'text-pink-400', placeholder: 'e.g. Red wool coat over white turtleneck' },
  QUALITY: { label: 'Quality', color: 'text-gray-400', placeholder: 'e.g. Shot on Arri Alexa, 4K RAW, photorealistic' },
}
