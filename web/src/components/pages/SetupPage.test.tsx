import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, afterEach } from 'vitest'
import SetupPage from './SetupPage'
import type { Project, AppConfig } from '../../types/project'

/**
 * Slice 13b — Setup page polish. Composition-level coverage for SetupPage's
 * OWN responsibilities (the 3-column shell, wiring the cue sheet's Edit
 * jump, and the "no inert control" audit) rather than re-testing the six
 * pre-existing CRUD panels ProjectTree mounts (CharacterPanel.test.tsx,
 * ObjectPanel.test.tsx, PreviewPanel.test.tsx, ... already cover those) or
 * the inspector sections (VideoSection.test.tsx, VoiceSection.test.tsx,
 * IdentitySection.test.tsx, SettingsInspector.test.tsx already cover those
 * in detail). The six panels are mocked to inert placeholders so this
 * suite's interactive-element sweep stays scoped to code this slice owns.
 */

vi.mock('../CharacterPanel', () => ({ default: () => <div data-testid="mock-character-panel" /> }))
vi.mock('../LocationPanel', () => ({ default: () => <div data-testid="mock-location-panel" /> }))
vi.mock('../ObjectPanel', () => ({ default: () => <div data-testid="mock-object-panel" /> }))
vi.mock('../ScenePanel', () => ({ default: () => <div data-testid="mock-scene-panel" /> }))
vi.mock('../GenerationPanel', () => ({ default: () => <div data-testid="mock-generation-panel" /> }))
vi.mock('../PreviewPanel', () => ({ default: () => <div data-testid="mock-preview-panel" /> }))

const setPage = vi.fn()
const setFocusScene = vi.fn()
vi.mock('../../context/PageContext', () => ({
  usePage: () => ({ page: 'setup', setPage, focusScene: null, setFocusScene }),
}))

function makeProject(): Project {
  return {
    id: 'proj-setup',
    name: 'Test Reel',
    characters: [{ id: 'c1' } as any],
    locations: [{ id: 'loc1', name: 'Warehouse' } as any],
    objects: [],
    scenes: [
      {
        id: 'scene1',
        order: 0,
        title: 'Opening',
        location_id: 'loc1',
        characters_present: [],
        action: '',
        dialogue: '',
        mood: 'cinematic',
        camera_direction: '',
        duration_seconds: 5,
        num_shots: 2,
        shots: [],
      },
    ],
    global_settings: {
      aspect_ratio: '16:9',
      music_mood: 'cinematic',
      color_palette: '',
      style_rules: {},
    },
  } as unknown as Project
}

const CONFIG: AppConfig = {
  camera_motions: [],
  visual_effects: [],
  target_apis: [],
  api_registry: {},
  music_moods: ['cinematic', 'tense'],
  voice_pool: [],
  aspect_ratios: ['16:9', '9:16'],
  pacing_options: [],
  mood_options: ['cinematic'],
  post_processing: {},
  continuity_options: {},
} as unknown as AppConfig

function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    text: vi.fn(async () => JSON.stringify(payload)),
  } as unknown as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
  setPage.mockClear()
  setFocusScene.mockClear()
})

describe('SetupPage', () => {
  it('renders the tree, cue sheet, and inspector columns together', () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({})))
    render(
      <SetupPage
        project={makeProject()}
        config={CONFIG}
        events={[]}
        latest={null}
        isGenerating={false}
        onRefreshProject={vi.fn()}
      />,
    )

    expect(screen.getByTestId('mock-character-panel')).toBeInTheDocument()
    expect(screen.getByText('Opening')).toBeInTheDocument() // SceneCueSheet row
    expect(screen.getByText('Dialogue TTS provider')).toBeInTheDocument() // VoiceSection
  })

  it('double-clicking a scene row still jumps to Edit through the composed page', () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({})))
    render(
      <SetupPage
        project={makeProject()}
        config={CONFIG}
        events={[]}
        latest={null}
        isGenerating={false}
        onRefreshProject={vi.fn()}
      />,
    )

    fireEvent.doubleClick(screen.getByText('Opening'))
    expect(setFocusScene).toHaveBeenCalledWith('scene1')
    expect(setPage).toHaveBeenCalledWith('edit')
  })

  it('an enabled control is genuinely wired -- clicking an aspect ratio pill PUTs the setting', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => response({}))
    vi.stubGlobal('fetch', fetchMock)
    render(
      <SetupPage
        project={makeProject()}
        config={CONFIG}
        events={[]}
        latest={null}
        isGenerating={false}
        onRefreshProject={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '9:16' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/projects/proj-setup')
    expect(JSON.parse((init as RequestInit).body as string).global_settings.aspect_ratio).toBe('9:16')
  })

  it('no inert control: any disabled button on the page discloses a reason', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({})))
    render(
      <SetupPage
        project={makeProject()}
        config={CONFIG}
        events={[]}
        latest={null}
        isGenerating={false}
        onRefreshProject={vi.fn()}
      />,
    )

    const buttons = screen.getAllByRole('button')
    // Sanity: the composed page renders a substantial set of real controls
    // (aspect ratio pills, section disclosures, and generate button), not
    // just the mocked panel placeholders.
    expect(buttons.length).toBeGreaterThan(5)

    const disabled = buttons.filter((b) => (b as HTMLButtonElement).disabled)
    for (const button of disabled) {
      const reason = button.getAttribute('title') || button.getAttribute('aria-label') || button.textContent?.trim()
      expect(reason, `disabled button has no discoverable reason: ${button.outerHTML}`).toBeTruthy()
    }
  })

  it('no inert control: the Generate style rules button discloses its busy reason while disabled', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        await new Promise((resolve) => setTimeout(resolve, 10))
        return response({})
      }),
    )
    render(
      <SetupPage
        project={makeProject()}
        config={CONFIG}
        events={[]}
        latest={null}
        isGenerating={false}
        onRefreshProject={vi.fn()}
      />,
    )

    const generateButton = screen.getByRole('button', { name: '+ Generate' })
    fireEvent.click(generateButton)

    expect(generateButton).toBeDisabled()
    expect(generateButton.textContent).toMatch(/Generating/i)

    await waitFor(() => expect(generateButton).not.toBeDisabled())
  })
})
