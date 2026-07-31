import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import PromptEditor from './PromptEditor'
import type { Shot } from '../../types/project'

/**
 * Slice 8b (2026-07-30 comprehensive-unification plan, plan slice 8) --
 * PromptEditor is the concrete "editor" this slice's brief refers to
 * (literally titled "Edit Shot Prompt"): before this change, `handleSave`
 * called `onSaved()` (which the only caller, ShotRow.tsx, wires to close
 * the modal) unconditionally, regardless of whether the PUT actually
 * succeeded. These tests pin the fix: a non-2xx/network failure surfaces
 * an inline error and does NOT call onSaved/onClose, so the modal stays
 * open with the operator's edits intact; a real success still closes it.
 */

function makeShot(overrides: Partial<Shot> = {}): Shot {
  return {
    id: 'shot-1',
    prompt: '[SHOT] a lone figure\n[SCENE] a rain-soaked street',
    camera: 'zoom_in_slow',
    visual_effect: 'cinematic_glow',
    target_api: 'AUTO',
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

/** Supports both call shapes hit during these tests: PromptEditor's own
 *  inline config GET (`.json()`) and the save PUT, now routed through
 *  `lib/api.ts`'s `apiRequest` (`.text()`). */
function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    text: vi.fn(async () => JSON.stringify(payload)),
    json: vi.fn(async () => payload),
  } as unknown as Response
}

const CONFIG_PAYLOAD = { camera_motions: ['zoom_in_slow'], visual_effects: ['cinematic_glow'], video_engines: [], api_registry: {} }

/** Routes by URL: the config GET always succeeds (display-only, unrelated
 *  to this test's concern); the shot PUT resolves however the test wants. */
function stubFetch(saveOutcome: { ok: boolean; status?: number; body?: unknown }) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/config')) return response(CONFIG_PAYLOAD)
    return response(saveOutcome.body ?? (saveOutcome.ok ? { success: true } : { error: 'boom' }), saveOutcome.ok, saveOutcome.status)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('PromptEditor -- truthful save (Slice 8b requirement 5)', () => {
  it('a non-2xx save does NOT close the editor and surfaces the error', async () => {
    stubFetch({ ok: false, status: 404, body: { error: 'Shot not found' } })
    const onClose = vi.fn()
    const onSaved = vi.fn()

    render(
      <PromptEditor
        shot={makeShot()}
        shotId="shot-1"
        projectId="proj-1"
        currentPrompt={makeShot().prompt}
        onClose={onClose}
        onSaved={onSaved}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /save & regenerate/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Shot not found')
    expect(onSaved).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
    // The modal itself is still rendered (the parent never unmounted it).
    expect(screen.getByText('Edit Shot Prompt')).toBeInTheDocument()
  })

  it('a network failure on save does NOT close the editor and surfaces a message instead of throwing', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/config')) return response(CONFIG_PAYLOAD)
      throw new Error('network down')
    })
    vi.stubGlobal('fetch', fetchMock)
    const onClose = vi.fn()
    const onSaved = vi.fn()

    render(
      <PromptEditor
        shot={makeShot()}
        shotId="shot-1"
        projectId="proj-1"
        currentPrompt={makeShot().prompt}
        onClose={onClose}
        onSaved={onSaved}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /save & regenerate/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('network down')
    expect(onSaved).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('a successful save DOES close the editor (onSaved called) and shows no error', async () => {
    stubFetch({ ok: true })
    const onClose = vi.fn()
    const onSaved = vi.fn()

    render(
      <PromptEditor
        shot={makeShot()}
        shotId="shot-1"
        projectId="proj-1"
        currentPrompt={makeShot().prompt}
        onClose={onClose}
        onSaved={onSaved}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /save & regenerate/i }))

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('a retried save after a failure can still succeed (the modal was never torn down)', async () => {
    let call = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/config')) return response(CONFIG_PAYLOAD)
      call += 1
      return call === 1 ? response({ error: 'boom' }, false, 500) : response({ success: true })
    })
    vi.stubGlobal('fetch', fetchMock)
    const onSaved = vi.fn()

    render(
      <PromptEditor
        shot={makeShot()}
        shotId="shot-1"
        projectId="proj-1"
        currentPrompt={makeShot().prompt}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    )

    const saveButton = screen.getByRole('button', { name: /save & regenerate/i })
    fireEvent.click(saveButton)
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(onSaved).not.toHaveBeenCalled()

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /save & regenerate/i }))
      await Promise.resolve()
    })

    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1))
  })
})
