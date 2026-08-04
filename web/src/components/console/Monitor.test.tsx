import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Project, ShotState } from '../../types/project'
import Monitor from './Monitor'

function okResponse(): Response {
  return {
    ok: true,
    status: 200,
    headers: { get: () => null },
    blob: async () => new Blob(['bytes']),
  } as unknown as Response
}

function projectWithNativeDialogueTake(): Project {
  return {
    id: 'p1',
    name: 'Review truth',
    characters: [],
    locations: [],
    objects: [],
    global_settings: { aspect_ratio: '16:9', music_mood: '', color_palette: '', style_rules: {} },
    scenes: [{
      id: 'scene-1',
      order: 0,
      title: 'Scene',
      location_id: '',
      characters_present: [],
      action: '',
      dialogue: 'Hello',
      mood: '',
      camera_direction: '',
      duration_seconds: 4,
      num_shots: 1,
      shots: [{
        id: 'shot-1',
        keyframe_takes: [],
        motion_takes: [{
          id: 'take-1',
          kind: 'motion',
          path: 'native.mp4',
          metadata: { has_dialogue: true, lipsync_validation_state: 'UNKNOWN' },
          cascade_metadata: { engine: 'VEO_NATIVE', native_audio_generated: true },
        }],
        performance_takes: [],
        postprocess_variants: [],
      }],
    }],
  } as unknown as Project
}

describe('Monitor review evidence', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => okResponse()))
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:mock'), revokeObjectURL: vi.fn() })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('wires active-take native audio and metadata validation state into the live strip', async () => {
    const shotStates = new Map<string, Partial<ShotState>>([
      ['shot-1', { take_id: 'take-1', take_kind: 'motion', generated_video: 'native.mp4' }],
    ])

    render(
      <Monitor
        project={projectWithNativeDialogueTake()}
        activeShotId="shot-1"
        shotStates={shotStates}
        projectId="p1"
        directorReview={null}
      />,
    )

    expect(screen.getByText('Native audio')).toBeInTheDocument()
    expect(screen.getByRole('status', { name: 'Lip-sync validation: UNKNOWN' })).toBeInTheDocument()
    expect(screen.queryByText('Lip-sync PASS')).toBeNull()
    await waitFor(() =>
      expect(document.querySelectorAll('[data-media-state="ready"]')).toHaveLength(1),
    )
  })

  it('uses the same fail-closed Chief Director presentation in the monitor', () => {
    render(
      <Monitor
        project={projectWithNativeDialogueTake()}
        activeShotId={null}
        shotStates={new Map()}
        directorReview={{ decision: 'UNEXPECTED' }}
      />,
    )

    expect(screen.getByRole('alert')).toHaveAttribute('data-review-state', 'manual-required')
    expect(screen.getByText(/UNRECOGNIZED \(UNEXPECTED\)/)).toBeInTheDocument()
  })

  it('derives UNKNOWN from legacy shot dialogue when take metadata is absent', async () => {
    const project = projectWithNativeDialogueTake()
    const shot = project.scenes[0].shots[0]
    shot.dialogue = 'This line predates take-level metadata.'
    shot.motion_takes[0].metadata = {}
    shot.motion_takes[0].cascade_metadata = { engine: 'VEO_NATIVE' }
    const shotStates = new Map<string, Partial<ShotState>>([
      ['shot-1', { take_id: 'take-1', take_kind: 'motion', generated_video: 'native.mp4' }],
    ])

    render(
      <Monitor
        project={project}
        activeShotId="shot-1"
        shotStates={shotStates}
        projectId="p1"
        directorReview={null}
      />,
    )

    expect(screen.getByRole('status', { name: 'Lip-sync validation: UNKNOWN' })).toBeInTheDocument()
    await waitFor(() =>
      expect(document.querySelectorAll('[data-media-state="ready"]')).toHaveLength(1),
    )
  })
})
