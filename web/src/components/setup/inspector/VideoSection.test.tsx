import { render, screen, fireEvent } from '@testing-library/react'
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
    workflow_templates: {
      portrait: { target_api: 'GEMINI_OMNI' },
    },
    billing_providers: {
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
    expect(update).toHaveBeenCalledWith('api_engines', expect.any(Function))
    const queuedUpdate = update.mock.calls[0][1]
    expect(queuedUpdate(undefined)).toEqual({ ENGINE_X: { enabled: true } })

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

  it('keeps a runtime-unavailable engine configured on and displays the server reason', () => {
    const config = {
      api_registry: { ENGINE_Y: api({ label: 'Engine Y' }) },
      video_engines: [
        row({
          key: 'ENGINE_Y',
          label: 'Engine Y',
          can_select: false,
          reason: 'runtime_unavailable',
          configured_enabled: true,
          can_configure: true,
        }),
      ],
    } as unknown as AppConfig

    render(<VideoSection s={{}} config={config} update={vi.fn()} />)

    expect(screen.getByRole('switch', { name: 'Enable Engine Y' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('runtime unavailable')).toBeInTheDocument()
  })

  it('marks GEMINI_OMNI Primary and every surfaced engine Cloud', () => {
    render(<VideoSection s={{}} config={mockConfig()} update={vi.fn()} />)

    // Exactly one Primary badge, on the first (GEMINI_OMNI) row.
    const primaries = screen.getAllByText('Primary')
    expect(primaries).toHaveLength(1)
    const gemini = screen.getAllByTestId('video-engine-row')[0]
    expect(gemini.getAttribute('data-engine-key')).toBe('GEMINI_OMNI')
    expect(gemini.textContent).toContain('Primary')

    // Every supported video engine is hosted.
    expect(screen.getAllByText('Cloud')).toHaveLength(3)
    expect(screen.queryByText('Pod')).toBeNull()
    expect(screen.queryByText('⚙')).toBeNull()
  })

  it('shows "No video engines available" when config has no server-selectable view', () => {
    const config = { api_registry: {} } as unknown as AppConfig

    render(<VideoSection s={{}} config={config} update={vi.fn()} />)

    expect(screen.queryAllByTestId('video-engine-row')).toHaveLength(0)
    expect(screen.getByText('No video engines available.')).toBeTruthy()
  })
})

/**
 * Slice 9b — video/spend settings reconciliation. Each test below pins BOTH
 * halves of the reciprocal contract for one exposed setting: (a) the
 * displayed default equals the runtime default it will be read against
 * (cited file:line in each test), and (b) writing through the UI contract
 * (`update(key, value)`) uses the exact key the runtime reader consumes.
 * `config={null}` throughout — none of these settings depend on server
 * config, only on the `s` (draft settings) prop.
 */
describe('settings reconciliation (slice 9b — video/spend defaults)', () => {
  it('cascade retry limit: displayed default (1) matches phase_c_ffmpeg.py MAX_CASCADE_RETRIES (line ~487), not the previous UI default of 2', () => {
    const update = vi.fn()
    render(<VideoSection s={{}} config={null} update={update} />)

    const slider = screen.getByRole('slider', { name: 'Cascade retry limit' })
    expect(slider).toHaveValue('1')

    fireEvent.change(slider, { target: { value: '3' } })
    expect(update).toHaveBeenCalledWith('cascade_retry_limit', 3)
  })

  it('native dialogue audio: displayed default (overlay/off) matches controller.py _dialogue_voice_mode\'s default ("overlay"), and toggling writes overlay<->native', async () => {
    const update = vi.fn()
    const { rerender } = render(<VideoSection s={{}} config={null} update={update} />)

    const toggle = screen.getByRole('switch', { name: 'Native dialogue audio' })
    expect(toggle.getAttribute('aria-checked')).toBe('false')
    expect(screen.getByText(/Veo runs through Vertex AI with ADC/i)).toBeInTheDocument()
    expect(screen.getByText(/Veo Developer API and other routes use the F1b/i)).toBeInTheDocument()
    expect(screen.getByText(/UNKNOWN and requires review/i)).toBeInTheDocument()

    await userEvent.click(toggle)
    expect(update).toHaveBeenCalledWith('dialogue_voice_mode', 'native')

    rerender(<VideoSection s={{ dialogue_voice_mode: 'native' }} config={null} update={update} />)
    const toggleAfter = screen.getByRole('switch', { name: 'Native dialogue audio' })
    expect(toggleAfter.getAttribute('aria-checked')).toBe('true')

    await userEvent.click(toggleAfter)
    expect(update).toHaveBeenCalledWith('dialogue_voice_mode', 'overlay')
  })

  it('face swap: displayed default (off) now matches controller.py apply_correction\'s fail-closed default (False, fixed in slice 9b — was True)', async () => {
    const update = vi.fn()
    render(<VideoSection s={{}} config={null} update={update} />)

    const toggle = screen.getByRole('switch', { name: 'Face swap' })
    expect(toggle.getAttribute('aria-checked')).toBe('false')

    await userEvent.click(toggle)
    expect(update).toHaveBeenCalledWith('face_swap_enabled', true)
  })

  it('motion quality gate: displayed default (0.50) ties to performance/motion_gate.py DEFAULT_MOTION_FLOOR (the true per-shot-type default when unset is 0.42-0.65 and cannot be a single number — see hint)', () => {
    const update = vi.fn()
    render(<VideoSection s={{}} config={null} update={update} />)

    const slider = screen.getByRole('slider', { name: 'Motion quality gate' })
    expect(slider).toHaveValue('0.5')

    fireEvent.change(slider, { target: { value: '0.6' } })
    expect(update).toHaveBeenCalledWith('motion_quality_threshold', 0.6)
  })

  it('coherence analysis: displayed default (on) matches controller.py diagnose_clip\'s default (True) — already agreed before this slice', async () => {
    const update = vi.fn()
    render(<VideoSection s={{}} config={null} update={update} />)

    const toggle = screen.getByRole('switch', { name: 'Coherence analysis' })
    expect(toggle.getAttribute('aria-checked')).toBe('true')

    await userEvent.click(toggle)
    expect(update).toHaveBeenCalledWith('coherence_check_enabled', false)
  })

  it('color drift sensitivity: displayed default (0.30) matches controller.py diagnose_clip\'s default (0.3) — already agreed before this slice', () => {
    const update = vi.fn()
    render(<VideoSection s={{}} config={null} update={update} />)

    const slider = screen.getByRole('slider', { name: 'Color drift sensitivity' })
    expect(slider).toHaveValue('0.3')

    fireEvent.change(slider, { target: { value: '0.2' } })
    expect(update).toHaveBeenCalledWith('color_drift_sensitivity', 0.2)
  })

  it('scene transitions + duration: displayed defaults (off / 0.5s) match cinema_pipeline.py\'s defaults — already agreed before this slice', () => {
    const update = vi.fn()
    const { rerender } = render(<VideoSection s={{}} config={null} update={update} />)

    const toggle = screen.getByRole('switch', { name: 'Scene transitions' })
    expect(toggle.getAttribute('aria-checked')).toBe('false')
    expect(screen.queryByRole('slider', { name: 'Transition duration (s)' })).toBeNull()

    rerender(<VideoSection s={{ scene_transitions: true }} config={null} update={update} />)
    const durationSlider = screen.getByRole('slider', { name: 'Transition duration (s)' })
    expect(durationSlider).toHaveValue('0.5')

    fireEvent.change(durationSlider, { target: { value: '1' } })
    expect(update).toHaveBeenCalledWith('transition_duration', 1)
  })

  it('color grade preset: displayed default (warm_cinema) matches the manual per-clip correction default in controller.py (final-assembly auto-grading ignores this value — see hint)', () => {
    const update = vi.fn()
    render(<VideoSection s={{}} config={null} update={update} />)

    const select = screen.getByRole('combobox', { name: 'Color grade' })
    expect(select).toHaveValue('warm_cinema')

    fireEvent.change(select, { target: { value: 'cool_noir' } })
    expect(update).toHaveBeenCalledWith('color_grade_preset', 'cool_noir')
  })
})
