import type { Shot } from '../types/project'

const DIALOGUE_PURPOSES = new Set(['dialogue_close_up', 'talking_head_full'])

/** Mirror the backend's shot-level lip-sync applicability fallback.
 *
 * Older takes may predate metadata.has_dialogue, while the durable shot still
 * carries dialogue or an optimizer purpose. The UI must treat those takes as
 * applicable/UNKNOWN instead of silently hiding the evidence gap.
 */
export function shotRequiresLipsync(shot: Shot): boolean {
  const dialogue = shot.dialogue
  if (typeof dialogue === 'string' && dialogue.trim().length > 0) return true
  if (Array.isArray(dialogue)) {
    const hasLine = dialogue.some((line) => {
      if (!line || typeof line !== 'object') return false
      const text = line.text ?? line.dialogue
      return typeof text === 'string' && text.trim().length > 0
    })
    if (hasLine) return true
  }

  const purpose = shot.optimizer_cache?.spec?.purpose
  return typeof purpose === 'string' && DIALOGUE_PURPOSES.has(purpose)
}
