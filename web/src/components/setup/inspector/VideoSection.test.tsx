import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { VideoSection } from './VideoSection'
import type { AppConfig, ApiInfo, VideoEngineRow } from '../../../types/project'

function api(overrides: Partial<ApiInfo> & Pick<ApiInfo, 'label'>): ApiInfo {
  return {
    category: 'native',
    description: '',
    modality: 'video',
    status: 'live',
    ...overrides,
  }
}

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

/**
 * Shape-based fixture: the server-provided selectable view drives
 * VideoSection directly. Includes AUTO (must be excluded — a routing
 * directive, not a togglable cascade engine), a non-configurable/not-in-use
 * row (must be excluded — never surfaces even though api_registry still
 * lists it as "live"), and a historical non-configurable-but-in-use row
 * (must still be excluded from THIS cascade-toggle list, unlike a
 * shot-level picker — a usage record isn't a live product-configuration
 * option). GEMINI_OMNI is included to exercise the Primary badge.
 */
function mockConfig(): AppConfig {
  return {
    api_registry: {
      GEMINI_OMNI: api({ label: 'Gemini Omni Flash' }),
      ENGINE_B: api({ label: 'Engine B' }),
      ENGINE_C: api({ label: 'Engine C' }),
      RETIRED_ENGINE: api({ label: 'Retired Engine' }), // still "live" in the legacy registry
    },
    video_engines: [
      row({ key: 'AUTO', label: 'Auto (Smart Routing)' }),
      row({ key: 'GEMINI_OMNI', label: 'Gemini Omni Flash' }),
      row({ key: 'ENGINE_B', label: 'Engine B' }),
      row({ key: 'ENGINE_C', label: 'Engine C' }),
      row({ key: 'RETIRED_ENGINE', label: 'Retired Engine', can_select: false, can_configure: false, reason: 'retired' }),
      row({
        key: 'HISTORICAL_ENGINE',
        label: 'Historical Engine',
        can_select: false,
        can_configure: false,
        reason: 'runtime_unavailable',
        in_use: true,
        historical: true,
      }),
    ],
    billing_providers: {
      RUNPOD_GPU: ['FLUX_DEV', 'HIDREAM_I1', 'SUPIR_V0Q'],
      GOOGLE_GEMINI_API: ['GEMINI_OMNI'],
    },
  } as unknown as AppConfig
}

describe('VideoSection', () => {
  it('renders configurable engines in server order, excluding AUTO and non-configurable/historical rows', () => {
    render(<VideoSection s={{}} config={mockConfig()} update={vi.fn()} />)

    const rows = screen.getAllByTestId('video-engine-row')
    expect(rows.map((r) => r.getAttribute('data-engine-key'))).toEqual(['GEMINI_OMNI', 'ENGINE_B', 'ENGINE_C'])

    // AUTO is a routing directive, not a dispatchable cascade engine.
    expect(screen.queryByText('Auto (Smart Routing)')).toBeNull()
    // Non-configurable rows never surface here, even the "live"-in-registry
    // one and the in-use historical one.
    expect(screen.queryByText('Retired Engine')).toBeNull()
    expect(screen.queryByText('Historical Engine')).toBeNull()
  })

  it('keeps a project-DISABLED, not-in-use engine visible with its toggle off, and lets it be re-enabled', async () => {
    const config = {
      api_registry: { ENGINE_X: api({ label: 'Engine X' }) },
      video_engines: [
        row({
          key: 'ENGINE_X',
          label: 'Engine X',
          can_select: false, // project-disabled -> not currently selectable...
          reason: 'project_disabled',
          configured_enabled: false,
          can_configure: true, // ...but still product-configurable, so it must stay listed.
          in_use: false,
        }),
      ],
    } as unknown as AppConfig

    const update = vi.fn()
    const { rerender } = render(<VideoSection s={{}} config={config} update={update} />)

    // The row survives being turned off, with the toggle rendered off.
    const rows = screen.getAllByTestId('video-engine-row')
    expect(rows.map((r) => r.getAttribute('data-engine-key'))).toEqual(['ENGINE_X'])
    const toggle = screen.getByRole('switch', { name: 'Enable Engine X' })
    expect(toggle.getAttribute('aria-checked')).toBe('false')

    // Re-enabling writes enabled:true through the settings-write contract.
    await userEvent.click(toggle)
    expect(update).toHaveBeenCalledWith('api_engines', { ENGINE_X: { enabled: true } })

    // Simulate the write landing in draft state (`s.api_engines`): the row
    // must still be present and now render its toggle on.
    rerender(<VideoSection s={{ api_engines: { ENGINE_X: { enabled: true } } }} config={config} update={update} />)
    const rowsAfter = screen.getAllByTestId('video-engine-row')
    expect(rowsAfter.map((r) => r.getAttribute('data-engine-key'))).toEqual(['ENGINE_X'])
    const toggleAfter = screen.getByRole('switch', { name: 'Enable Engine X' })
    expect(toggleAfter.getAttribute('aria-checked')).toBe('true')
  })

  it('shows a configurable, currently-enabled engine with its toggle on', () => {
    const config = {
      api_registry: { ENGINE_Y: api({ label: 'Engine Y' }) },
      video_engines: [
        row({
          key: 'ENGINE_Y',
          label: 'Engine Y',
          can_select: true,
          configured_enabled: true,
          can_configure: true,
        }),
      ],
    } as unknown as AppConfig

    render(<VideoSection s={{}} config={config} update={vi.fn()} />)

    expect(screen.getAllByTestId('video-engine-row').map((r) => r.getAttribute('data-engine-key'))).toEqual([
      'ENGINE_Y',
    ])
    const toggle = screen.getByRole('switch', { name: 'Enable Engine Y' })
    expect(toggle.getAttribute('aria-checked')).toBe('true')
  })

  it('marks GEMINI_OMNI Primary and every surfaced engine Cloud (none pod)', () => {
    render(<VideoSection s={{}} config={mockConfig()} update={vi.fn()} />)

    // Exactly one Primary badge, on the first (GEMINI_OMNI) row.
    const primaries = screen.getAllByText('Primary')
    expect(primaries).toHaveLength(1)
    const gemini = screen.getAllByTestId('video-engine-row')[0]
    expect(gemini.getAttribute('data-engine-key')).toBe('GEMINI_OMNI')
    expect(gemini.textContent).toContain('Primary')

    // All three surfaced engines are cloud — RUNPOD_GPU doesn't bill any of them.
    expect(screen.getAllByText('Cloud')).toHaveLength(3)
    expect(screen.queryByText('Pod')).toBeNull()
    expect(screen.queryByText('⚙')).toBeNull()
  })

  it('shows a ⚙ Pod badge when a surfaced video engine is pod-gated', () => {
    // Contrived "if surfaced anywhere" case: a selectable video-modality
    // engine that RUNPOD_GPU bills → isPodGated true → the row must carry
    // the ⚙ Pod badge.
    const config = {
      api_registry: {
        GEMINI_OMNI: api({ label: 'Gemini Omni Flash' }),
        FLUX_DEV: api({ label: 'FLUX-Dev (pod video)' }),
      },
      video_engines: [
        row({ key: 'GEMINI_OMNI', label: 'Gemini Omni Flash' }),
        row({ key: 'FLUX_DEV', label: 'FLUX-Dev (pod video)' }),
      ],
      billing_providers: { RUNPOD_GPU: ['FLUX_DEV'] },
    } as unknown as AppConfig

    render(<VideoSection s={{}} config={config} update={vi.fn()} />)

    const fluxRow = screen
      .getAllByTestId('video-engine-row')
      .find((r) => r.getAttribute('data-engine-key') === 'FLUX_DEV')!
    expect(fluxRow.textContent).toContain('Pod')
    expect(fluxRow.textContent).toContain('⚙')
  })

  it('shows "No video engines available" when config has no server-selectable view', () => {
    const config = { api_registry: {} } as unknown as AppConfig

    render(<VideoSection s={{}} config={config} update={vi.fn()} />)

    expect(screen.queryAllByTestId('video-engine-row')).toHaveLength(0)
    expect(screen.getByText('No video engines available.')).toBeTruthy()
  })
})
