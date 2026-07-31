import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ShotRow from './ShotRow'
import type { Shot } from '../../types/project'

/**
 * Slice-8b-review fix (2026-07-30 comprehensive-unification plan) --
 * `updateShotApi` is a sibling of PromptEditor's `handleSave` PUT to the
 * SAME shots endpoint (`PUT /api/projects/{pid}/shots/{sid}`). Before this
 * change it used a raw `fetch` with no `.ok` check and then unconditionally
 * mutated `shot.target_api` as an "optimistic update" -- painting a
 * rejected (or network-failed) change as if it had landed. These tests pin
 * the fix: migrated onto `lib/api.ts`'s `apiPut`, a non-2xx/network failure
 * surfaces an inline error and leaves `shot.target_api` (and the rendered
 * select) at the last CONFIRMED value; a real success still applies it.
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

const CONFIG_PAYLOAD = {
  camera_motions: ['zoom_in_slow'],
  visual_effects: ['cinematic_glow'],
  video_engines: [
    { key: 'ENGINE_A', label: 'Engine A', can_select: true, reason: null, configured_enabled: true, can_configure: true, in_use: true, historical: false },
    { key: 'ENGINE_B', label: 'Engine B', can_select: true, reason: null, configured_enabled: true, can_configure: true, in_use: false, historical: false },
  ],
  api_registry: {},
}

/** ShotRow's OWN config load is a separate, still-raw `fetch(...).then(r =>
 *  r.json())` (module-cached per projectId; not one of this slice's named
 *  defects, left as-is) -- so the mock must satisfy both call shapes hit in
 *  these tests: that `.json()` GET, and the target_api PUT, now routed
 *  through `lib/api.ts`'s `apiRequest` (`.text()`). */
function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    text: vi.fn(async () => JSON.stringify(payload)),
    json: vi.fn(async () => payload),
  } as unknown as Response
}

function stubFetch(putOutcome: { ok: boolean; status?: number; body?: unknown }) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.includes('/api/config')) return response(CONFIG_PAYLOAD)
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

describe('ShotRow -- truthful target_api update (sibling of PromptEditor.handleSave)', () => {
  it('a non-2xx PUT does not mutate shot.target_api and surfaces an inline error', async () => {
    stubFetch({ ok: false, status: 404, body: { error: 'Shot not found' } })
    const shot = makeShot()

    render(
      <ShotRow shot={shot} shotState={undefined} shotIndex={0} sceneId="scene-1" projectId="proj-shotrow-1" />,
    )

    const select = await screen.findByRole('combobox')
    await waitFor(() => expect(select).toHaveValue('ENGINE_A'))

    fireEvent.change(select, { target: { value: 'ENGINE_B' } })

    expect(await screen.findByRole('alert')).toHaveTextContent('Shot not found')
    // The prop object was never mutated -- the rejected value never "lands".
    expect(shot.target_api).toBe('ENGINE_A')
    await waitFor(() => expect(select).toHaveValue('ENGINE_A'))
  })

  it('a network failure on the PUT does not mutate shot.target_api and surfaces a message instead of throwing', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.includes('/api/config')) return response(CONFIG_PAYLOAD)
      if (method === 'PUT') throw new Error('network down')
      return response({})
    })
    vi.stubGlobal('fetch', fetchMock)
    const shot = makeShot()

    render(
      <ShotRow shot={shot} shotState={undefined} shotIndex={0} sceneId="scene-1" projectId="proj-shotrow-2" />,
    )

    const select = await screen.findByRole('combobox')
    await waitFor(() => expect(select).toHaveValue('ENGINE_A'))

    fireEvent.change(select, { target: { value: 'ENGINE_B' } })

    expect(await screen.findByRole('alert')).toHaveTextContent('network down')
    expect(shot.target_api).toBe('ENGINE_A')
  })

  it('a successful PUT applies the new target_api and shows no error', async () => {
    stubFetch({ ok: true })
    const shot = makeShot()

    render(
      <ShotRow shot={shot} shotState={undefined} shotIndex={0} sceneId="scene-1" projectId="proj-shotrow-3" />,
    )

    const select = await screen.findByRole('combobox')
    await waitFor(() => expect(select).toHaveValue('ENGINE_A'))

    fireEvent.change(select, { target: { value: 'ENGINE_B' } })

    await waitFor(() => expect(shot.target_api).toBe('ENGINE_B'))
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
