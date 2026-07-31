import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

/**
 * The lipsync cascade is the one control here that survived a file deletion:
 * `LipsyncPriorityList` used to live in `settings/AudioSyncSection.tsx`, whose
 * section component was dead while this named export stayed mounted. These
 * assertions pin the wiring — that the list renders inside Voice, and that it
 * reads/writes the server-validated `lipsync_engine_priority` key.
 */
describe('VoiceSection lipsync cascade', () => {
  const DEFAULT_CASCADE = ['SYNC_SO_V3', 'MUSETALK', 'LATENTSYNC', 'OMNIHUMAN_V1_5', 'SYNC_V2']

  it('renders the default cascade in order when the setting is unset', () => {
    render(<VoiceSection s={{}} config={null} update={vi.fn()} />)

    expect(screen.getByText('Lipsync engine priority')).toBeInTheDocument()
    for (const key of DEFAULT_CASCADE) {
      expect(screen.getByText(key)).toBeInTheDocument()
    }
  })

  it('reads an explicit priority from settings rather than the default', () => {
    render(
      <VoiceSection
        s={{ lipsync_engine_priority: ['MUSETALK', 'SYNC_V2'] }}
        config={null}
        update={vi.fn()}
      />,
    )

    expect(screen.getByText('MUSETALK')).toBeInTheDocument()
    expect(screen.getByText('SYNC_V2')).toBeInTheDocument()
    expect(screen.queryByText('SYNC_SO_V3')).toBeNull()
  })

  it('writes the reordered list back to lipsync_engine_priority', async () => {
    const update = vi.fn()
    render(<VoiceSection s={{}} config={null} update={update} />)

    await userEvent.click(screen.getByRole('button', { name: 'Move SYNC_SO_V3 down' }))

    expect(update).toHaveBeenCalledWith('lipsync_engine_priority', [
      'MUSETALK',
      'SYNC_SO_V3',
      'LATENTSYNC',
      'OMNIHUMAN_V1_5',
      'SYNC_V2',
    ])
  })

  it('disables reordering past either end of the cascade', () => {
    render(<VoiceSection s={{}} config={null} update={vi.fn()} />)

    expect(screen.getByRole('button', { name: 'Move SYNC_SO_V3 up' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Move SYNC_V2 down' })).toBeDisabled()
  })
})
