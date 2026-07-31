import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ShotBin from './ShotBin'
import type { Scene, Shot } from '../../types/project'

/**
 * Slice 13c -- ShotBin gains "Move earlier"/"Move later" reorder controls.
 * They are real `<button>`s (keyboard-operable via Tab + Enter/Space from
 * the start, unlike `ScenePanel`'s drag-and-drop scene reorder), wired to
 * the same `PUT /api/projects/{pid}/scenes/{sid}` `{shots: [...]}` contract
 * `ScenePanel` already uses. These tests cover: the boundary buttons are
 * genuinely disabled with a stated reason (not just decorative), a keyboard
 * activation performs the reorder end to end, and a rejected PUT surfaces an
 * accessible alert instead of silently doing nothing or refreshing anyway.
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

function makeScene(shots: Shot[]): Scene {
  return {
    id: 'scene1',
    order: 0,
    title: 'Scene One',
    location_id: '',
    characters_present: [],
    action: '',
    dialogue: '',
    mood: '',
    camera_direction: '',
    duration_seconds: 10,
    num_shots: shots.length,
    shots,
  }
}

function okResponse(body: unknown = { id: 'scene1' }): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    text: vi.fn(async () => JSON.stringify(body)),
  } as unknown as Response
}

function failResponse(error: string, status = 409): Response {
  return {
    ok: false,
    status,
    statusText: 'Conflict',
    text: vi.fn(async () => JSON.stringify({ error })),
  } as unknown as Response
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('ShotBin', () => {
  it('renders the focused scene shots with a 1-based index', () => {
    const scene = makeScene([makeShot('a1'), makeShot('a2')])
    render(
      <ShotBin
        scene={scene}
        shotStates={new Map()}
        activeShotId={null}
        onSelectShot={vi.fn()}
        projectId="p1"
        onRefreshProject={vi.fn()}
      />,
    )

    expect(screen.getByText('01')).toBeInTheDocument()
    expect(screen.getByText('02')).toBeInTheDocument()
  })

  it('clicking a shot row calls onSelectShot with that shot id', async () => {
    const scene = makeScene([makeShot('a1'), makeShot('a2')])
    const onSelectShot = vi.fn()
    render(
      <ShotBin
        scene={scene}
        shotStates={new Map()}
        activeShotId={null}
        onSelectShot={onSelectShot}
        projectId="p1"
        onRefreshProject={vi.fn()}
      />,
    )

    await userEvent.click(screen.getByText('02'))

    expect(onSelectShot).toHaveBeenCalledWith('a2')
  })

  describe('inert-affordance enumeration -- reorder controls', () => {
    it('the first shot cannot move earlier and the last shot cannot move later, each disabled with a stated reason', () => {
      const scene = makeScene([makeShot('a1'), makeShot('a2'), makeShot('a3')])
      render(
        <ShotBin
          scene={scene}
          shotStates={new Map()}
          activeShotId={null}
          onSelectShot={vi.fn()}
          projectId="p1"
          onRefreshProject={vi.fn()}
        />,
      )

      const firstUp = screen.getByRole('button', { name: /Move shot 1 .* earlier/ })
      const lastDown = screen.getByRole('button', { name: /Move shot 3 .* later/ })

      expect(firstUp).toBeDisabled()
      expect(firstUp).toHaveAttribute('title', 'Already first in the scene')
      expect(lastDown).toBeDisabled()
      expect(lastDown).toHaveAttribute('title', 'Already last in the scene')
    })

    it('every other reorder control is enabled -- not permanently inert', () => {
      const scene = makeScene([makeShot('a1'), makeShot('a2'), makeShot('a3')])
      render(
        <ShotBin
          scene={scene}
          shotStates={new Map()}
          activeShotId={null}
          onSelectShot={vi.fn()}
          projectId="p1"
          onRefreshProject={vi.fn()}
        />,
      )

      expect(screen.getByRole('button', { name: /Move shot 1 .* later/ })).toBeEnabled()
      expect(screen.getByRole('button', { name: /Move shot 2 .* earlier/ })).toBeEnabled()
      expect(screen.getByRole('button', { name: /Move shot 2 .* later/ })).toBeEnabled()
      expect(screen.getByRole('button', { name: /Move shot 3 .* earlier/ })).toBeEnabled()
    })
  })

  describe('keyboard reorder', () => {
    it('focusing "move later" on shot 1 and pressing Enter PUTs the swapped shots array and refreshes', async () => {
      const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => okResponse())
      vi.stubGlobal('fetch', fetchMock)
      const scene = makeScene([makeShot('a1'), makeShot('a2'), makeShot('a3')])
      const onRefreshProject = vi.fn()

      render(
        <ShotBin
          scene={scene}
          shotStates={new Map()}
          activeShotId={null}
          onSelectShot={vi.fn()}
          projectId="p1"
          onRefreshProject={onRefreshProject}
        />,
      )

      const moveLater = screen.getByRole('button', { name: /Move shot 1 .* later/ })
      moveLater.focus()
      expect(moveLater).toHaveFocus()

      await userEvent.keyboard('{Enter}')

      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
      const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      expect(url).toBe('/api/projects/p1/scenes/scene1')
      expect(init.method).toBe('PUT')
      const body = JSON.parse(init.body as string)
      expect(body.shots.map((s: Shot) => s.id)).toEqual(['a2', 'a1', 'a3'])

      await waitFor(() => expect(onRefreshProject).toHaveBeenCalledTimes(1))
    })

    it('is reachable by Tab alone (no pointer input) before the keyboard activation', async () => {
      const fetchMock = vi.fn(async () => okResponse())
      vi.stubGlobal('fetch', fetchMock)
      const scene = makeScene([makeShot('a1'), makeShot('a2')])

      render(
        <ShotBin
          scene={scene}
          shotStates={new Map()}
          activeShotId={null}
          onSelectShot={vi.fn()}
          projectId="p1"
          onRefreshProject={vi.fn()}
        />,
      )

      // Tab order: shot-1 select, shot-1 move-later (move-earlier is disabled
      // and skipped), shot-2 select, shot-2 move-earlier.
      await userEvent.tab() // shot-1 select button
      await userEvent.tab() // shot-1 "move later"
      expect(screen.getByRole('button', { name: /Move shot 1 .* later/ })).toHaveFocus()

      await userEvent.keyboard(' ')
      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    })

    it('moving shot 2 earlier swaps it with shot 1', async () => {
      const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => okResponse())
      vi.stubGlobal('fetch', fetchMock)
      const scene = makeScene([makeShot('a1'), makeShot('a2'), makeShot('a3')])

      render(
        <ShotBin
          scene={scene}
          shotStates={new Map()}
          activeShotId={null}
          onSelectShot={vi.fn()}
          projectId="p1"
          onRefreshProject={vi.fn()}
        />,
      )

      const moveEarlier = screen.getByRole('button', { name: /Move shot 2 .* earlier/ })
      moveEarlier.focus()
      await userEvent.keyboard('{Enter}')

      await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
      const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
      const body = JSON.parse(init.body as string)
      expect(body.shots.map((s: Shot) => s.id)).toEqual(['a2', 'a1', 'a3'])
    })
  })

  describe('reorder errors', () => {
    it('a rejected PUT surfaces an accessible alert and does not call onRefreshProject', async () => {
      const fetchMock = vi.fn(async () => failResponse('scene is locked'))
      vi.stubGlobal('fetch', fetchMock)
      const scene = makeScene([makeShot('a1'), makeShot('a2')])
      const onRefreshProject = vi.fn()

      render(
        <ShotBin
          scene={scene}
          shotStates={new Map()}
          activeShotId={null}
          onSelectShot={vi.fn()}
          projectId="p1"
          onRefreshProject={onRefreshProject}
        />,
      )

      await userEvent.click(screen.getByRole('button', { name: /Move shot 1 .* later/ }))

      expect(await screen.findByRole('alert')).toHaveTextContent('Could not reorder: scene is locked')
      expect(onRefreshProject).not.toHaveBeenCalled()
    })

    it('a network failure does not throw and surfaces a message instead of failing silently', async () => {
      const fetchMock = vi.fn(async () => {
        throw new Error('network down')
      })
      vi.stubGlobal('fetch', fetchMock)
      const scene = makeScene([makeShot('a1'), makeShot('a2')])
      const onRefreshProject = vi.fn()

      render(
        <ShotBin
          scene={scene}
          shotStates={new Map()}
          activeShotId={null}
          onSelectShot={vi.fn()}
          projectId="p1"
          onRefreshProject={onRefreshProject}
        />,
      )

      await userEvent.click(screen.getByRole('button', { name: /Move shot 1 .* later/ }))

      expect(await screen.findByRole('alert')).toHaveTextContent('network down')
      expect(onRefreshProject).not.toHaveBeenCalled()
    })

    it('a subsequent successful reorder clears a previous error', async () => {
      const fetchMock = vi.fn(async () => failResponse('scene is locked'))
      vi.stubGlobal('fetch', fetchMock)
      const scene = makeScene([makeShot('a1'), makeShot('a2')])
      const onRefreshProject = vi.fn()

      render(
        <ShotBin
          scene={scene}
          shotStates={new Map()}
          activeShotId={null}
          onSelectShot={vi.fn()}
          projectId="p1"
          onRefreshProject={onRefreshProject}
        />,
      )

      await userEvent.click(screen.getByRole('button', { name: /Move shot 1 .* later/ }))
      expect(await screen.findByRole('alert')).toBeInTheDocument()

      fetchMock.mockImplementation(async () => okResponse())
      await userEvent.click(screen.getByRole('button', { name: /Move shot 1 .* later/ }))

      await waitFor(() => expect(onRefreshProject).toHaveBeenCalledTimes(1))
      expect(screen.queryByRole('alert')).toBeNull()
    })
  })
})
