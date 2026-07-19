import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { VideoSection } from './VideoSection'
import type { AppConfig, ApiInfo } from '../../../types/project'

function api(overrides: Partial<ApiInfo> & Pick<ApiInfo, 'label'>): ApiInfo {
  return {
    category: 'native',
    description: '',
    modality: 'video',
    status: 'live',
    ...overrides,
  }
}

/** Five live video engines in registry order (deliberately NOT Google-first,
 *  so the test proves VideoSection reorders via videoEngines) + the retired
 *  Sora/Runway keys, which must be filtered out. RUNPOD_GPU bills no cloud
 *  video engine, so all five surfaced rows read Cloud. */
function mockConfig(): AppConfig {
  return {
    api_registry: {
      LTX: api({ label: 'LTX Video 2.3' }),
      SORA_NATIVE: api({ label: 'Sora 2 Native' }),
      SEEDANCE: api({ label: 'Seedance 2.0' }),
      GEMINI_OMNI: api({ label: 'Gemini Omni Flash' }),
      RUNWAY_GEN4: api({ label: 'Runway Gen-4' }),
      KLING_3_0: api({ label: 'Kling v3 Pro' }),
      VEO_NATIVE: api({ label: 'Veo 3.1 Native' }),
    },
    billing_providers: {
      RUNPOD_GPU: ['FLUX_DEV', 'HIDREAM_I1', 'SUPIR_V0Q'],
      GOOGLE_GEMINI_API: ['GEMINI_OMNI'],
    },
  } as unknown as AppConfig
}

describe('VideoSection', () => {
  it('renders live video engines in Google-first order, excluding retired engines', () => {
    render(<VideoSection s={{}} config={mockConfig()} update={vi.fn()} />)

    const rows = screen.getAllByTestId('video-engine-row')
    expect(rows.map((r) => r.getAttribute('data-engine-key'))).toEqual([
      'GEMINI_OMNI',
      'VEO_NATIVE',
      'SEEDANCE',
      'KLING_3_0',
      'LTX',
    ])

    // Retired / sunset engines never surface.
    expect(screen.queryByText('Sora 2 Native')).toBeNull()
    expect(screen.queryByText('Runway Gen-4')).toBeNull()
  })

  it('marks GEMINI_OMNI Primary and every surfaced engine Cloud (none pod)', () => {
    render(<VideoSection s={{}} config={mockConfig()} update={vi.fn()} />)

    // Exactly one Primary badge, on the first (GEMINI_OMNI) row.
    const primaries = screen.getAllByText('Primary')
    expect(primaries).toHaveLength(1)
    const gemini = screen.getAllByTestId('video-engine-row')[0]
    expect(gemini.getAttribute('data-engine-key')).toBe('GEMINI_OMNI')
    expect(gemini.textContent).toContain('Primary')

    // All five surfaced engines are cloud — no pod badge / no ⚙ gear glyph.
    expect(screen.getAllByText('Cloud')).toHaveLength(5)
    expect(screen.queryByText('Pod')).toBeNull()
    expect(screen.queryByText('⚙')).toBeNull()
  })

  it('shows a ⚙ Pod badge when a surfaced video engine is pod-gated', () => {
    // Contrived "if surfaced anywhere" case: a live video-modality engine that
    // RUNPOD_GPU bills → isPodGated true → the row must carry the ⚙ Pod badge.
    const config = {
      api_registry: {
        GEMINI_OMNI: api({ label: 'Gemini Omni Flash' }),
        FLUX_DEV: api({ label: 'FLUX-Dev (pod video)' }),
      },
      billing_providers: { RUNPOD_GPU: ['FLUX_DEV'] },
    } as unknown as AppConfig

    render(<VideoSection s={{}} config={config} update={vi.fn()} />)

    const fluxRow = screen
      .getAllByTestId('video-engine-row')
      .find((r) => r.getAttribute('data-engine-key') === 'FLUX_DEV')!
    expect(fluxRow.textContent).toContain('Pod')
    expect(fluxRow.textContent).toContain('⚙')
  })
})
