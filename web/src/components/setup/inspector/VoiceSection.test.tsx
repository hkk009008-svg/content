import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { VoiceSection } from './VoiceSection'
import type { AppConfig } from '../../../types/project'

/**
 * Slice 9c (voice/language settings wiring). Covers:
 *  - the WPM hint no longer claiming the pacing control is unwired (it is —
 *    audio/dialogue.py's generate_dialogue_voiceover calls _apply_target_pace
 *    on both the dialogue-mode and per-line paths)
 *  - the lipsync-priority caption honestly disclosing it isn't read by the
 *    overlay/generation cascades yet (lip_sync.py hardcodes its own order)
 *  - language selection invoking the apply-language-defaults contract and
 *    surfacing which fields changed, exactly once per real change (never on
 *    mount)
 */

function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    text: vi.fn(async () => JSON.stringify(payload)),
  } as unknown as Response
}

function mockConfig(): AppConfig {
  return {
    api_registry: {
      ELEVENLABS_V3: { label: 'ElevenLabs v3', category: 'tts', description: '', modality: 'tts', status: 'live' },
      CARTESIA_SONIC_2: { label: 'Cartesia Sonic 2', category: 'tts', description: '', modality: 'tts', status: 'live' },
    },
    voice_pool: [{ id: 'v1', name: 'Eric', style: 'warm' }],
  } as unknown as AppConfig
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('VoiceSection', () => {
  it('renders the core voice/lipsync/pace controls without crashing', () => {
    render(<VoiceSection s={{}} config={mockConfig()} update={vi.fn()} />)

    expect(screen.getByText('Dialogue TTS provider')).toBeInTheDocument()
    expect(screen.getByText('Default male voice')).toBeInTheDocument()
    expect(screen.getByText('Default female voice')).toBeInTheDocument()
    expect(screen.getByText('Dialogue pace (target WPM)')).toBeInTheDocument()
  })

  it('the WPM hint states pacing IS applied, not merely staged for future wiring', () => {
    render(<VoiceSection s={{}} config={mockConfig()} update={vi.fn()} />)

    expect(screen.queryByText(/once wired/i)).toBeNull()
    expect(screen.getByText(/applied via an atempo post-process/i)).toBeInTheDocument()
  })

  it('discloses that lipsync engine priority is not yet read by the cascades', () => {
    render(<VoiceSection s={{}} config={mockConfig()} update={vi.fn()} />)

    expect(screen.getByText(/not yet read by the overlay\/generation cascades/i)).toBeInTheDocument()
  })

  it('does not call apply-language-defaults on initial mount', () => {
    const fetchMock = vi.fn(async () => response({}))
    vi.stubGlobal('fetch', fetchMock)

    render(
      <VoiceSection
        s={{ language: 'English' }}
        config={mockConfig()}
        update={vi.fn()}
        projectId="proj-1"
        onRefresh={vi.fn()}
      />,
    )

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('invokes apply-language-defaults when the language actually changes, and surfaces changed fields', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) =>
      response({
        language: 'Korean',
        changed_fields: ['tts_provider', 'lipsync_validation_threshold'],
        applied_defaults: {},
        recommended_voices: { male: 'm1', female: 'f1', available_count: 2 },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onRefresh = vi.fn()

    const { rerender } = render(
      <VoiceSection
        s={{ language: 'English' }}
        config={mockConfig()}
        update={vi.fn()}
        projectId="proj-1"
        onRefresh={onRefresh}
      />,
    )

    await act(async () => {
      rerender(
        <VoiceSection
          s={{ language: 'Korean' }}
          config={mockConfig()}
          update={vi.fn()}
          projectId="proj-1"
          onRefresh={onRefresh}
        />,
      )
    })

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/projects/proj-1/apply-language-defaults')
    expect(JSON.parse(init!.body as string)).toEqual({ language: 'Korean' })

    await waitFor(() =>
      expect(
        screen.getByText('Applied Korean voice/lipsync defaults — changed: tts_provider, lipsync_validation_threshold'),
      ).toBeInTheDocument(),
    )
    expect(onRefresh).toHaveBeenCalled()
  })

  it('shows a "nothing to change" notice when changed_fields is empty and does not refresh', async () => {
    const fetchMock = vi.fn(async () =>
      response({ language: 'Korean', changed_fields: [], applied_defaults: {}, recommended_voices: { available_count: 0 } }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const onRefresh = vi.fn()

    const { rerender } = render(
      <VoiceSection s={{ language: 'English' }} config={mockConfig()} update={vi.fn()} projectId="proj-1" onRefresh={onRefresh} />,
    )
    await act(async () => {
      rerender(
        <VoiceSection s={{ language: 'Korean' }} config={mockConfig()} update={vi.fn()} projectId="proj-1" onRefresh={onRefresh} />,
      )
    })

    await waitFor(() =>
      expect(screen.getByText('Korean defaults already match — nothing to change.')).toBeInTheDocument(),
    )
    expect(onRefresh).not.toHaveBeenCalled()
  })

  it('surfaces a network/HTTP failure as an alert instead of throwing', async () => {
    const fetchMock = vi.fn(async () => response({ error: 'Project not found' }, false, 404))
    vi.stubGlobal('fetch', fetchMock)

    const { rerender } = render(
      <VoiceSection s={{ language: 'English' }} config={mockConfig()} update={vi.fn()} projectId="proj-1" onRefresh={vi.fn()} />,
    )
    await act(async () => {
      rerender(
        <VoiceSection s={{ language: 'Korean' }} config={mockConfig()} update={vi.fn()} projectId="proj-1" onRefresh={vi.fn()} />,
      )
    })

    expect(await screen.findByRole('alert')).toHaveTextContent('Project not found')
  })

  it('never fires without a projectId (defensive -- nothing to call)', async () => {
    const fetchMock = vi.fn(async () => response({}))
    vi.stubGlobal('fetch', fetchMock)

    const { rerender } = render(
      <VoiceSection s={{ language: 'English' }} config={mockConfig()} update={vi.fn()} />,
    )
    await act(async () => {
      rerender(<VoiceSection s={{ language: 'Korean' }} config={mockConfig()} update={vi.fn()} />)
    })

    expect(fetchMock).not.toHaveBeenCalled()
  })
})
