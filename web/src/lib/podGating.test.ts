import { describe, it, expect } from 'vitest'
import { isPodGated, POD_FEATURES } from './podGating'
import type { AppConfig } from '../types/project'

// billing_providers ships from the backend PROVIDER-keyed (each provider
// bucket lists the engine keys it bills) — verified against
// domain/scene_decomposer.py:154 BILLING_PROVIDERS, e.g.
//   { RUNPOD_GPU: ['FLUX_DEV', 'HIDREAM_I1', 'SD3_5_LARGE', 'SUPIR_V0Q', 'CCSR'], ... }
// NOT engine-keyed. isPodGated below reflects the real shape.
function mockConfig(billing_providers: Record<string, string[]>): Pick<AppConfig, 'billing_providers'> {
  return { billing_providers }
}

describe('isPodGated', () => {
  it('returns true for an engine in the RUNPOD_GPU provider bucket', () => {
    const config = mockConfig({
      RUNPOD_GPU: ['FLUX_DEV', 'HIDREAM_I1', 'SD3_5_LARGE', 'SUPIR_V0Q', 'CCSR'],
    })
    expect(isPodGated('FLUX_DEV', config as AppConfig)).toBe(true)
  })

  it('returns false for an engine billed by a non-pod provider', () => {
    const config = mockConfig({
      GOOGLE_GEMINI_API: ['GEMINI_OMNI'],
      RUNPOD_GPU: ['FLUX_DEV', 'HIDREAM_I1', 'SD3_5_LARGE', 'SUPIR_V0Q', 'CCSR'],
    })
    expect(isPodGated('GEMINI_OMNI', config as AppConfig)).toBe(false)
  })

  it('returns false when billing_providers is missing', () => {
    expect(isPodGated('FLUX_DEV', null)).toBe(false)
    expect(isPodGated('FLUX_DEV', {} as AppConfig)).toBe(false)
  })

  it('exposes the two non-engine pod feature gates', () => {
    expect(POD_FEATURES).toEqual(['lora_training', 'comfyui_keyframe'])
  })
})
