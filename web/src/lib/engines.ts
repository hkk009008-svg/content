import type { AppConfig, ApiStatus, VideoEngineRow } from '../types/project'

export interface VideoEngineOption {
  key: string
  label: string
  /** Server-computed selectability (`VideoEngineRow.can_select`, as-is). */
  selectable: boolean
  /** Server-computed reason the engine isn't selectable right now (e.g.
   *  "retired", "runtime_unavailable", "aspect_incompatible"), or null when
   *  `selectable` is true. Surface as a disabled-option title/tooltip where
   *  the picker's idiom supports it. */
  reason: string | null
  status: ApiStatus
  primary: boolean
  cost?: number
  quality?: number
}

export interface CascadeEngineOption {
  key: string
  label: string
  /** Server-computed selectability (`VideoEngineRow.can_select`), for
   *  display/tooltip only — never used to decide whether the row appears. */
  selectable: boolean
  /** Server-computed non-selectability reason (e.g. "project_disabled",
   *  "retired"), or null when `selectable` is true. */
  reason: string | null
  /** Project-resolved enable/disable state (`VideoEngineRow.configured_enabled`)
   *  — the source of truth for the toggle when the caller has no pending
   *  local edit for this key yet. */
  configuredEnabled: boolean
  status: ApiStatus
  primary: boolean
  cost?: number
  quality?: number
}

/** Recommended/flagship engine badge — UI decoration only, not a
 *  selectability signal (that's `row.can_select`, from the server). */
const PRIMARY_ENGINE = 'GEMINI_OMNI'

/** `reason_snake_case` -> `reason snake case`, for tooltip/label display. */
export function humanizeEngineReason(reason: string | null): string {
  return reason ? reason.replace(/_/g, ' ') : ''
}

/**
 * Config-driven video engine picker options, reconciled entirely from the
 * server-provided selectable view (`config.video_engines`, built by
 * `web_server.py:_project_video_engine_rows`).
 *
 * The server already folds in catalog lifecycle, date-effective sunset
 * policy, per-project `api_engines` disable state, aspect-ratio
 * compatibility, and runtime availability — this function does not
 * re-derive any of that. It only shapes rows for picker consumption:
 *   - keeps a row if it is currently selectable OR currently in use by a
 *     persisted shot (so an existing override that just became
 *     non-selectable still surfaces — disabled, with its reason — rather
 *     than silently vanishing from the picker);
 *   - enriches with `api_registry` cost/quality/status where available,
 *     for display only (never for selectability).
 *
 * `AUTO` is included (server always marks it selectable) so every picker
 * gets the smart-routing option "for free" without its own fallback.
 *
 * Returns `[]` when `config` is null or lacks `video_engines` (i.e. the
 * config was fetched without a `project_id` — the rows are project-scoped).
 */
export function videoEngines(config: AppConfig | null): VideoEngineOption[] {
  const rows: VideoEngineRow[] | undefined = config?.video_engines
  if (!rows) return []

  const registry = config?.api_registry

  return rows
    .filter((row) => row.can_select || row.in_use)
    .map((row) => {
      const info = registry?.[row.key]
      return {
        key: row.key,
        label: row.label,
        selectable: row.can_select,
        reason: row.reason,
        status: info?.status ?? 'live',
        primary: row.key === PRIMARY_ENGINE,
        cost: info?.per_shot_cost,
        quality: info?.quality_score,
      }
    })
}

/**
 * Cascade-participation options for a project's engine-toggle list (e.g.
 * `VideoSection`) — distinct from `videoEngines()`, which is the
 * shot-level PICKER view.
 *
 * `videoEngines()` retains rows by `can_select || in_use` — correct for a
 * picker, but `can_select` itself folds in the project's own disable state
 * (`VideoPolicyReason.PROJECT_DISABLED`), so a cascade toggle list keyed on
 * it would make disabling a not-yet-`in_use` engine remove its row (and
 * therefore its toggle) entirely, with no way to re-enable it. This view
 * instead retains a row whenever the server marks it `can_configure`
 * (product-configurable for this project's `api_engines`, independent of
 * whether it's currently selectable) so a project-disabled engine keeps its
 * row, rendered off via `configuredEnabled`, until the user turns it back
 * on. `AUTO` is always excluded — a routing directive, not a togglable
 * engine.
 *
 * Returns `[]` when `config` is null or lacks `video_engines`.
 */
export function cascadeEngineOptions(config: AppConfig | null): CascadeEngineOption[] {
  const rows: VideoEngineRow[] | undefined = config?.video_engines
  if (!rows) return []

  const registry = config?.api_registry

  return rows
    .filter((row) => row.key !== 'AUTO' && row.can_configure)
    .map((row) => {
      const info = registry?.[row.key]
      return {
        key: row.key,
        label: row.label,
        selectable: row.can_select,
        reason: row.reason,
        configuredEnabled: row.configured_enabled,
        status: info?.status ?? 'live',
        primary: row.key === PRIMARY_ENGINE,
        cost: info?.per_shot_cost,
        quality: info?.quality_score,
      }
    })
}
