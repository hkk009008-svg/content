import { describe, it, expect } from 'vitest'
import { videoEngines, humanizeEngineReason } from './engines'
import type { AppConfig, ApiInfo, VideoEngineRow } from '../types/project'

/**
 * Shape-based fixtures. Deliberately fake engine keys (not the real
 * GEMINI_OMNI/VEO_NATIVE/... roster) — `videoEngines` must derive its output
 * purely from the shape of `config.video_engines`, never from which real
 * engines happen to be live at any given moment (slice 3 concurrently
 * changes GEMINI_OMNI's real catalog state).
 */
function row(overrides: Partial<VideoEngineRow> & Pick<VideoEngineRow, 'key' | 'label'>): VideoEngineRow {
  return {
    can_select: true,
    reason: null,
    configured_enabled: true,
    can_configure: true,
    in_use: false,
    historical: false,
    ...overrides,
  }
}

function api(overrides: Partial<ApiInfo> & Pick<ApiInfo, 'label'>): ApiInfo {
  return {
    category: 'native',
    description: '',
    modality: 'video',
    status: 'live',
    ...overrides,
  }
}

function config(video_engines: VideoEngineRow[], api_registry: Record<string, ApiInfo> = {}): AppConfig {
  return { video_engines, api_registry } as unknown as AppConfig
}

describe('videoEngines', () => {
  it('returns [] for a null config', () => {
    expect(videoEngines(null)).toEqual([])
  })

  it('returns [] when config has no video_engines (no project_id on /api/config)', () => {
    // Only api_registry present — proves there is no client-side fallback
    // that re-derives options from the registry when the server view is
    // absent (that was the old EXCLUDED_VIDEO_ENGINES defect).
    const c = { api_registry: { FAKE_ENGINE: api({ label: 'Fake Engine' }) } } as unknown as AppConfig
    expect(videoEngines(c)).toEqual([])
  })

  it('maps a selectable server row straight through, preserving server order', () => {
    const c = config([
      row({ key: 'ENGINE_B', label: 'Engine B' }),
      row({ key: 'ENGINE_A', label: 'Engine A' }),
    ])

    const result = videoEngines(c)

    expect(result.map((e) => e.key)).toEqual(['ENGINE_B', 'ENGINE_A'])
    expect(result[0]).toMatchObject({ key: 'ENGINE_B', label: 'Engine B', selectable: true, reason: null })
  })

  it('a server-marked non-selectable, not-in-use engine cannot appear as an option — even when present in api_registry', () => {
    const c = config(
      [
        row({ key: 'LIVE_ENGINE', label: 'Live Engine', can_select: true }),
        row({ key: 'RETIRED_ENGINE', label: 'Retired Engine', can_select: false, reason: 'retired', in_use: false }),
      ],
      {
        LIVE_ENGINE: api({ label: 'Live Engine' }),
        // Still "live" in the legacy registry — this is exactly the drift
        // the old client-side hidden-list was vulnerable to. The server row
        // (can_select: false, in_use: false) must win.
        RETIRED_ENGINE: api({ label: 'Retired Engine', status: 'live' }),
      },
    )

    const result = videoEngines(c)

    expect(result.map((e) => e.key)).toEqual(['LIVE_ENGINE'])
    expect(result.some((e) => e.key === 'RETIRED_ENGINE')).toBe(false)
  })

  it('keeps a non-selectable engine that is in_use (a historical shot override), carrying its reason', () => {
    const c = config([
      row({
        key: 'HISTORICAL_ENGINE',
        label: 'Historical Engine',
        can_select: false,
        reason: 'runtime_unavailable',
        in_use: true,
        historical: true,
      }),
    ])

    const result = videoEngines(c)

    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      key: 'HISTORICAL_ENGINE',
      selectable: false,
      reason: 'runtime_unavailable',
    })
  })

  it('includes AUTO when the server marks it selectable (server truth, not a client exclusion)', () => {
    const c = config([
      row({ key: 'AUTO', label: 'Auto (Smart Routing)', can_select: true }),
      row({ key: 'ENGINE_A', label: 'Engine A' }),
    ])

    const result = videoEngines(c)

    expect(result.map((e) => e.key)).toEqual(['AUTO', 'ENGINE_A'])
  })

  it('marks exactly the GEMINI_OMNI row primary when present, and nothing else', () => {
    const c = config([
      row({ key: 'GEMINI_OMNI', label: 'Gemini Omni Flash' }),
      row({ key: 'ENGINE_A', label: 'Engine A' }),
    ])

    const result = videoEngines(c)

    expect(result.find((e) => e.key === 'GEMINI_OMNI')?.primary).toBe(true)
    expect(result.filter((e) => e.primary)).toHaveLength(1)
  })

  it('enriches cost/quality/status from api_registry by key, defaulting status to live when absent', () => {
    const c = config(
      [row({ key: 'ENGINE_A', label: 'Engine A' }), row({ key: 'ENGINE_B', label: 'Engine B' })],
      { ENGINE_A: api({ label: 'Engine A', per_shot_cost: 0.42, quality_score: 0.9, status: 'beta' }) },
    )

    const result = videoEngines(c)

    const a = result.find((e) => e.key === 'ENGINE_A')!
    expect(a.cost).toBe(0.42)
    expect(a.quality).toBe(0.9)
    expect(a.status).toBe('beta')

    const b = result.find((e) => e.key === 'ENGINE_B')!
    expect(b.cost).toBeUndefined()
    expect(b.quality).toBeUndefined()
    expect(b.status).toBe('live')
  })
})

describe('humanizeEngineReason', () => {
  it('replaces underscores with spaces', () => {
    expect(humanizeEngineReason('runtime_unavailable')).toBe('runtime unavailable')
  })

  it('returns an empty string for null', () => {
    expect(humanizeEngineReason(null)).toBe('')
  })
})
