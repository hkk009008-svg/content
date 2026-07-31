import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import EditPage from './EditPage'
import { PageProvider } from '../../context/PageContext'
import type { Project, Shot } from '../../types/project'

/**
 * Slice 13c -- EditPage now flattens every scene's shots into project shot
 * order (scenes sorted by `order`, same flattening Timeline/Filmstrip
 * already do) and feeds ShotViewer's transport bar a computed previous/next
 * shot, re-focusing the owning scene via the SAME `handleSelectShot` a
 * Timeline click already uses when the walk crosses a scene boundary.
 * ShotViewer's own button wiring/disabled-state/keyboard operability is
 * covered in ShotViewer.test.tsx; these tests cover the flattening/boundary
 * math itself, which previously had no test at all (EditPage had no test
 * file before this slice).
 *
 * Verified via `[data-shot-id]`/`aria-current` on Timeline's clips -- the
 * same technique Timeline.test.tsx already uses to assert the active shot,
 * since Timeline (unlike ShotBin) renders every scene's clips at once and so
 * unambiguously identifies which shot is active regardless of scene focus.
 */

function makeShot(id: string): Shot {
  return {
    id,
    prompt: '',
    camera: '',
    visual_effect: '',
    target_api: 'AUTO',
    scene_foley: '',
    characters_in_frame: [],
    primary_character: '',
    objects_in_frame: [],
    primary_object: '',
    action_context: '',
    generated_image: '',
    generated_video: '',
    plan_status: 'pending_review',
    keyframe_takes: [],
    approved_keyframe_take_id: '',
    motion_takes: [],
    approved_motion_take_id: '',
    postprocess_variants: [],
    approved_final_take_id: '',
    diagnostics: [],
    intent_notes: '',
    negative_constraints: '',
    continuity_constraints: '',
  }
}

function makeProject(): Project {
  return {
    id: 'proj1',
    name: 'Test Reel',
    characters: [],
    locations: [],
    objects: [],
    global_settings: { aspect_ratio: '16:9', music_mood: '', color_palette: '', style_rules: {} },
    scenes: [
      {
        id: 'sceneA',
        order: 0,
        title: 'Scene A',
        location_id: '',
        characters_present: [],
        action: '',
        dialogue: '',
        mood: '',
        camera_direction: '',
        duration_seconds: 8,
        num_shots: 2,
        shots: [makeShot('a1'), makeShot('a2')],
      },
      {
        id: 'sceneB',
        order: 1,
        title: 'Scene B',
        location_id: '',
        characters_present: [],
        action: '',
        dialogue: '',
        mood: '',
        camera_direction: '',
        duration_seconds: 8,
        num_shots: 2,
        shots: [makeShot('b1'), makeShot('b2')],
      },
    ],
  }
}

function renderEditPage() {
  return render(
    <PageProvider>
      <EditPage project={makeProject()} config={null} apiBase="/api" onRefreshProject={vi.fn()} shotStates={new Map()} />
    </PageProvider>,
  )
}

/** Timeline renders every scene's clips at once with `data-shot-id` +
 *  `aria-current` on whichever is active -- unambiguous regardless of which
 *  scene ShotBin currently has focused. */
function activeShotIdInTimeline(container: HTMLElement): string | null {
  return container.querySelector('[aria-current="true"][data-shot-id]')?.getAttribute('data-shot-id') ?? null
}

afterEach(cleanup)

describe('EditPage -- transport bar previous/next wiring (slice 13c)', () => {
  it('defaults to the first shot of the first scene: Previous disabled, Next enabled', () => {
    const { container } = renderEditPage()

    expect(activeShotIdInTimeline(container)).toBe('a1')
    expect(screen.getByRole('button', { name: 'Previous shot' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Next shot' })).toBeEnabled()
  })

  it('Next walks a1 -> a2 -> b1 -> b2 across the scene boundary, then disables itself', async () => {
    const { container } = renderEditPage()
    const next = screen.getByRole('button', { name: 'Next shot' })

    await userEvent.click(next)
    expect(activeShotIdInTimeline(container)).toBe('a2')

    await userEvent.click(next) // crosses from scene A into scene B
    expect(activeShotIdInTimeline(container)).toBe('b1')
    expect(screen.getByRole('button', { name: 'Previous shot' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Next shot' })).toBeEnabled()

    await userEvent.click(next)
    expect(activeShotIdInTimeline(container)).toBe('b2')
    expect(screen.getByRole('button', { name: 'Next shot' })).toBeDisabled()
  })

  it('clicking Next past the last shot is a no-op (button is disabled, not silently wrapping)', async () => {
    const { container } = renderEditPage()
    const next = screen.getByRole('button', { name: 'Next shot' })

    await userEvent.click(next) // a1 -> a2
    await userEvent.click(next) // a2 -> b1
    await userEvent.click(next) // b1 -> b2 (last)
    await userEvent.click(next) // disabled -- must not wrap to a1

    expect(activeShotIdInTimeline(container)).toBe('b2')
  })

  it('Previous walks back across the scene boundary, symmetric to Next', async () => {
    const { container } = renderEditPage()
    const next = screen.getByRole('button', { name: 'Next shot' })
    const prev = screen.getByRole('button', { name: 'Previous shot' })

    await userEvent.click(next) // a1 -> a2
    await userEvent.click(next) // a2 -> b1
    await userEvent.click(prev) // b1 -> a2, back across the boundary

    expect(activeShotIdInTimeline(container)).toBe('a2')
    expect(screen.getByRole('button', { name: 'Previous shot' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Next shot' })).toBeEnabled()
  })
})
