import { describe, it, expect } from 'vitest'
import { videoEngines } from './engines'
import type { AppConfig, ApiInfo } from '../types/project'

function api(overrides: Partial<ApiInfo> & Pick<ApiInfo, 'label'>): ApiInfo {
  return {
    category: 'native',
    description: '',
    modality: 'video',
    status: 'live',
    ...overrides,
  }
}

function mockConfig(api_registry: Record<string, ApiInfo>): Pick<AppConfig, 'api_registry'> {
  return { api_registry }
}

describe('videoEngines', () => {
  it('orders the Google-first cascade, marks GEMINI_OMNI primary, and excludes retired engines', () => {
    const config = mockConfig({
      GEMINI_OMNI: api({ label: 'Gemini Omni Flash' }),
      VEO_NATIVE: api({ label: 'Veo 3.1 Native' }),
      SEEDANCE: api({ label: 'Seedance 2.0' }),
      KLING_3_0: api({ label: 'Kling v3 Pro' }),
      LTX: api({ label: 'LTX Video 2.3' }),
      SORA_NATIVE: api({ label: 'Sora 2 Native' }),
      RUNWAY_GEN4: api({ label: 'Runway Gen-4' }),
    })

    const result = videoEngines(config as AppConfig)

    expect(result.map((e) => e.key)).toEqual([
      'GEMINI_OMNI',
      'VEO_NATIVE',
      'SEEDANCE',
      'KLING_3_0',
      'LTX',
    ])
    expect(result.find((e) => e.key === 'GEMINI_OMNI')?.primary).toBe(true)
    expect(result.some((e) => e.key === 'SORA_NATIVE')).toBe(false)
    expect(result.some((e) => e.key === 'RUNWAY_GEN4')).toBe(false)
    // only GEMINI_OMNI is primary
    expect(result.filter((e) => e.primary)).toHaveLength(1)
  })

  it('excludes the full retired/sunset/legacy-proxy set', () => {
    const retired = ['SORA_NATIVE', 'SORA_2', 'RUNWAY_GEN4', 'RUNWAY', 'HEDRA_C3', 'KLING_NATIVE', 'VEO']
    const registry: Record<string, ApiInfo> = { GEMINI_OMNI: api({ label: 'Gemini Omni Flash' }) }
    for (const key of retired) registry[key] = api({ label: key })

    const result = videoEngines(mockConfig(registry) as AppConfig)

    expect(result.map((e) => e.key)).toEqual(['GEMINI_OMNI'])
  })

  it('appends a live video engine outside the canonical order/exclude lists, after the ordered set', () => {
    const config = mockConfig({
      GEMINI_OMNI: api({ label: 'Gemini Omni Flash' }),
      LTX: api({ label: 'LTX Video 2.3' }),
      NEW_ENGINE: api({ label: 'Some New Engine' }),
    })

    const result = videoEngines(config as AppConfig)

    expect(result.map((e) => e.key)).toEqual(['GEMINI_OMNI', 'LTX', 'NEW_ENGINE'])
    expect(result.find((e) => e.key === 'NEW_ENGINE')?.primary).toBe(false)
  })

  it('filters out non-video modalities', () => {
    const config = mockConfig({
      GEMINI_OMNI: api({ label: 'Gemini Omni Flash' }),
      ELEVENLABS_V3: api({ label: 'ElevenLabs v3', modality: 'tts', category: 'tts' }),
      FLUX_DEV: api({ label: 'FLUX-Dev', modality: 'image', category: 'image_gen' }),
    })

    const result = videoEngines(config as AppConfig)

    expect(result.map((e) => e.key)).toEqual(['GEMINI_OMNI'])
  })

  it('carries cost/quality through and returns [] for a null config', () => {
    const config = mockConfig({
      GEMINI_OMNI: api({ label: 'Gemini Omni Flash', per_shot_cost: 0.56, quality_score: 0.85 }),
    })

    const result = videoEngines(config as AppConfig)
    expect(result[0].cost).toBe(0.56)
    expect(result[0].quality).toBe(0.85)
    expect(result[0].status).toBe('live')

    expect(videoEngines(null)).toEqual([])
  })
})
