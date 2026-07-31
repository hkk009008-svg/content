import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ShotInspector from './ShotInspector'
import type { AppConfig, Project, Scene, Shot } from '../../types/project'

/**
 * Slice-8b-review fix (2026-07-30 comprehensive-unification plan) --
 * `persistShot` is a sibling of PromptEditor's `handleSave` PUT to the SAME
 * shots endpoint (`PUT /api/projects/{pid}/shots/{sid}`). Before this
 * change it used a raw `fetch` with no `.ok` check and unconditionally
 * called `onRefreshProject()` regardless of outcome, while `updateField`
 * had already painted the new value into `form` before the network call
 * even started -- a rejected change still looked saved. These tests pin
 * the fix: migrated onto `lib/api.ts`'s `apiPut`; a non-2xx/network failure
 * surfaces an inline error, does NOT call `onRefreshProject`, and reverts
 * an instant-commit field (the Primary API pill) back to its last
 * confirmed value; a real success still applies + refreshes. Free-text
 * fields (e.g. Negative constraints) keep the operator's unsaved keystrokes
 * on a failure instead -- the same "don't discard on failure" behavior as
 * PromptEditor's modal staying open with edits intact.
 */

function makeShot(overrides: Partial<Shot> = {}): Shot {
  return {
    id: 'shot-1',
    prompt: '[SHOT] a lone figure\n[SCENE] a rain-soaked street',
    camera: 'zoom_in_slow',
    visual_effect: 'cinematic_glow',
    target_api: 'ENGINE_A',
    scene_foley: '',
    characters_in_frame: [],
    primary_character: '',
    objects_in_frame: [],
    primary_object: '',
    action_context: '',
    generated_image: '',
    generated_video: '',
    plan_status: 'approved',
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
    ...overrides,
  }
}

function makeScene(shot: Shot): Scene {
  return {
    id: 'scene-1',
    order: 0,
    title: 'Scene 1',
    location_id: '',
    characters_present: [],
    action: '',
    dialogue: 'Hello there.',
    mood: '',
    camera_direction: '',
    duration_seconds: 4,
    num_shots: 1,
    shots: [shot],
  }
}

function makeProject(scene: Scene): Project {
  return {
    id: 'proj-1',
    name: 'Project 1',
    characters: [],
    locations: [],
    objects: [],
    scenes: [scene],
    global_settings: { aspect_ratio: '16:9', music_mood: '', color_palette: '', style_rules: {} },
  }
}

const CONFIG: AppConfig = {
  camera_motions: ['zoom_in_slow'],
  visual_effects: ['cinematic_glow'],
  video_engines: [
    { key: 'ENGINE_A', label: 'Engine A', can_select: true, reason: null, configured_enabled: true, can_configure: true, in_use: true, historical: false },
    { key: 'ENGINE_B', label: 'Engine B', can_select: true, reason: null, configured_enabled: true, can_configure: true, in_use: false, historical: false },
  ],
  api_registry: {},
} as unknown as AppConfig

/** `lib/api.ts`'s `apiRequest` reads the body via `res.text()` (never `.json()`). */
function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    text: vi.fn(async () => JSON.stringify(payload)),
  } as unknown as Response
}

function stubFetch(putOutcome: { ok: boolean; status?: number; body?: unknown }) {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    if (method === 'PUT') {
      return response(putOutcome.body ?? (putOutcome.ok ? { success: true } : { error: 'boom' }), putOutcome.ok, putOutcome.status)
    }
    return response({})
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('ShotInspector -- truthful persistShot (sibling of PromptEditor.handleSave)', () => {
  it('a non-2xx PUT does not call onRefreshProject, surfaces an error, and reverts the Primary API pill', async () => {
    stubFetch({ ok: false, status: 404, body: { error: 'Shot not found' } })
    const shot = makeShot()
    const scene = makeScene(shot)
    const project = makeProject(scene)
    const onRefreshProject = vi.fn()

    render(
      <ShotInspector project={project} config={CONFIG} scene={scene} shot={shot} shotState={undefined} onRefreshProject={onRefreshProject} />,
    )

    const apiPill = screen.getByRole('combobox', { name: 'Primary API' })
    expect(apiPill).toHaveValue('ENGINE_A')

    fireEvent.change(apiPill, { target: { value: 'ENGINE_B' } })

    expect(await screen.findByRole('alert')).toHaveTextContent('Shot not found')
    expect(onRefreshProject).not.toHaveBeenCalled()
    // The rejected pick must not sit there looking saved.
    await waitFor(() => expect(apiPill).toHaveValue('ENGINE_A'))
  })

  it('a network failure on the PUT does not throw, surfaces a message, and reverts the pill', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      if (method === 'PUT') throw new Error('network down')
      return response({})
    })
    vi.stubGlobal('fetch', fetchMock)
    const shot = makeShot()
    const scene = makeScene(shot)
    const project = makeProject(scene)
    const onRefreshProject = vi.fn()

    render(
      <ShotInspector project={project} config={CONFIG} scene={scene} shot={shot} shotState={undefined} onRefreshProject={onRefreshProject} />,
    )

    const apiPill = screen.getByRole('combobox', { name: 'Primary API' })
    fireEvent.change(apiPill, { target: { value: 'ENGINE_B' } })

    expect(await screen.findByRole('alert')).toHaveTextContent('network down')
    expect(onRefreshProject).not.toHaveBeenCalled()
    await waitFor(() => expect(apiPill).toHaveValue('ENGINE_A'))
  })

  it('a successful PUT applies the pill value and refreshes the authoritative project, with no error', async () => {
    stubFetch({ ok: true })
    const shot = makeShot()
    const scene = makeScene(shot)
    const project = makeProject(scene)
    const onRefreshProject = vi.fn()

    render(
      <ShotInspector project={project} config={CONFIG} scene={scene} shot={shot} shotState={undefined} onRefreshProject={onRefreshProject} />,
    )

    const apiPill = screen.getByRole('combobox', { name: 'Primary API' })
    fireEvent.change(apiPill, { target: { value: 'ENGINE_B' } })

    await waitFor(() => expect(onRefreshProject).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(apiPill).toHaveValue('ENGINE_B')
  })

  it('a rejected free-text commit surfaces an error but keeps the operator\'s unsaved keystrokes', async () => {
    stubFetch({ ok: false, status: 500, body: { error: 'save failed' } })
    const shot = makeShot()
    const scene = makeScene(shot)
    const project = makeProject(scene)
    const onRefreshProject = vi.fn()

    render(
      <ShotInspector project={project} config={CONFIG} scene={scene} shot={shot} shotState={undefined} onRefreshProject={onRefreshProject} />,
    )

    const negativeField = screen.getByPlaceholderText('What must never happen in this shot')
    fireEvent.change(negativeField, { target: { value: 'no extra limbs' } })
    fireEvent.blur(negativeField)

    expect(await screen.findByRole('alert')).toHaveTextContent('save failed')
    expect(onRefreshProject).not.toHaveBeenCalled()
    // Unlike the instant-commit pill, free text is NOT discarded on failure.
    expect(negativeField).toHaveValue('no extra limbs')
  })
})
