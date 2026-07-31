import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PreviewPanel from './PreviewPanel'
import type { Project } from '../types/project'

/**
 * Slice 10 (2026-07-30 comprehensive-unification plan, plan slice 10) --
 * PreviewPanel's Final Export and per-scene previews used to hand a raw
 * `src` straight to `<video>`: a missing export/preview rendered as a
 * silent blank/broken player (the "previews render blank with no
 * explanation" defect). Both now route through MediaAsset, which fetches
 * the URL and renders an explicit state. These tests prove the wiring, not
 * the state machine itself (see ui/MediaAsset.test.tsx for the full
 * idle/loading/ready/migrated/missing matrix).
 */

function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    id: 'proj1',
    name: 'Test Reel',
    characters: [],
    locations: [],
    objects: [],
    scenes: [],
    global_settings: {
      aspect_ratio: '9:16',
      music_mood: '',
      color_palette: '',
      style_rules: {},
    },
    ...overrides,
  }
}

describe('PreviewPanel', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:mock'), revokeObjectURL: vi.fn() })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('final export: no export generated yet -> explicit missing state, not a blank player', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, headers: { get: () => null } }) as unknown as Response))

    render(<PreviewPanel project={makeProject()} />)

    await waitFor(() => expect(screen.getByText('Media missing')).toBeInTheDocument())
    expect(screen.queryByRole('video')).not.toBeInTheDocument()
  })

  it('final export: a generated export renders through MediaAsset with the export URL', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      headers: { get: () => null },
      blob: async () => new Blob(['mp4 bytes']),
    }) as unknown as Response)
    vi.stubGlobal('fetch', fetchMock)

    render(<PreviewPanel project={makeProject()} />)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/projects/proj1/export'))
    const frame = document.querySelector('[data-media-state="ready"]')
    expect(frame).not.toBeNull()
  })

  it('renders one MediaAsset slot per scene, keyed off the preview endpoint', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, headers: { get: () => null } }) as unknown as Response))

    const project = makeProject({
      scenes: [
        {
          id: 'sc1', order: 0, title: 'Opening', location_id: '', characters_present: [],
          action: '', dialogue: '', mood: '', camera_direction: '', duration_seconds: 5,
          num_shots: 2, shots: [],
        },
        {
          id: 'sc2', order: 1, title: 'Climax', location_id: '', characters_present: [],
          action: '', dialogue: '', mood: '', camera_direction: '', duration_seconds: 8,
          num_shots: 3, shots: [],
        },
      ],
    })

    render(<PreviewPanel project={project} />)

    expect(screen.getByText('1. Opening')).toBeInTheDocument()
    expect(screen.getByText('2. Climax')).toBeInTheDocument()
    await waitFor(() => expect(screen.getAllByText('Media missing')).toHaveLength(3)) // export + 2 scenes
  })

  it('no scenes yet -> the empty-project message, no scene preview slots', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 404, headers: { get: () => null } }) as unknown as Response))

    render(<PreviewPanel project={makeProject()} />)

    expect(screen.getByText('Add scenes to preview generated footage.')).toBeInTheDocument()
    // Let the final-export MediaAsset's fetch settle so no state update lands
    // after this test's cleanup.
    await waitFor(() => expect(screen.getByText('Media missing')).toBeInTheDocument())
  })
})
