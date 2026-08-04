import type { ApiResult } from './api'

export interface SettingsRevisionConflict {
  currentRevision: number
  globalSettings: Record<string, any>
}

/** Decode the shared optimistic-concurrency payload used by every settings
 * writer. Keeping this structural (instead of trusting HTTP 409 alone)
 * prevents an unrelated conflict response from being treated as a safe
 * settings snapshot. */
export function settingsRevisionConflict(
  result: ApiResult<unknown>,
): SettingsRevisionConflict | null {
  if (result.ok || result.status !== 409) return null
  if (!result.body || typeof result.body !== 'object' || Array.isArray(result.body)) return null
  const body = result.body as Record<string, unknown>
  if (body.code !== 'settings_revision_conflict') return null
  if (!Number.isInteger(body.current_revision)) return null
  if (
    !body.global_settings
    || typeof body.global_settings !== 'object'
    || Array.isArray(body.global_settings)
  ) {
    return null
  }
  return {
    currentRevision: body.current_revision as number,
    globalSettings: body.global_settings as Record<string, any>,
  }
}
