import type { AppConfig, ApiInfo, ApiStatus } from '../types/project'

export interface VideoEngineOption {
  key: string
  label: string
  status: ApiStatus
  primary: boolean
  cost?: number
  quality?: number
}

/**
 * Retired / sunset / legacy-proxy engines hidden from the video picker, plus
 * 'AUTO' — a smart-routing meta-value (domain/scene_decomposer.py:38,
 * modality:'video', status:'live'), not a concrete engine the UI can select.
 */
const EXCLUDED_VIDEO_ENGINES = new Set([
  'SORA_NATIVE',
  'SORA_2',
  'RUNWAY_GEN4',
  'RUNWAY',
  'HEDRA_C3',
  'KLING_NATIVE',
  'VEO',
  'AUTO',
])

/** Canonical Google-first order (mirrors DEFAULT_VIDEO_CASCADE in phase_c_ffmpeg.py). */
const CANONICAL_VIDEO_ORDER = ['GEMINI_OMNI', 'VEO_NATIVE', 'SEEDANCE', 'KLING_3_0', 'LTX']

const PRIMARY_ENGINE = 'GEMINI_OMNI'

function toOption(key: string, info: ApiInfo): VideoEngineOption {
  return {
    key,
    label: info.label,
    status: info.status ?? 'live',
    primary: key === PRIMARY_ENGINE,
    cost: info.per_shot_cost,
    quality: info.quality_score,
  }
}

/**
 * Config-driven, reconciled list of video engines for the UI picker.
 *
 * Filters `config.api_registry` to live video-modality engines, excludes the
 * retired/sunset/legacy-proxy set, orders the canonical Google-first cascade
 * first (GEMINI_OMNI marked primary), then appends any other live video
 * engine not in either list — so a newly-added engine surfaces automatically
 * without a picker code change.
 */
export function videoEngines(config: AppConfig | null): VideoEngineOption[] {
  const registry = config?.api_registry
  if (!registry) return []

  const eligible = new Map(
    Object.entries(registry).filter(
      ([key, info]) => info.modality === 'video' && info.status === 'live' && !EXCLUDED_VIDEO_ENGINES.has(key),
    ),
  )

  const ordered: VideoEngineOption[] = []
  for (const key of CANONICAL_VIDEO_ORDER) {
    const info = eligible.get(key)
    if (!info) continue
    ordered.push(toOption(key, info))
    eligible.delete(key)
  }
  for (const [key, info] of eligible) {
    ordered.push(toOption(key, info))
  }
  return ordered
}
