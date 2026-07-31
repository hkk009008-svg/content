import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ShotViewer from './ShotViewer'
import type { Shot } from '../../types/project'

/**
 * Slice 10 (2026-07-30 comprehensive-unification plan, plan slice 10) --
 * ShotViewer's center-stage media used to hand a raw `src` straight to
 * `<video>`/`<img>`; a take whose stored path can't be found rendered as a
 * blank/broken player with no explanation. It now routes through
 * MediaAsset. "No shot selected" / "No take yet" are pre-existing, distinct
 * business states left untouched -- these tests cover the NEW media-fetch
 * states layered on top of them.
 *
 * Slice 13c -- the transport bar's Previous/Next were purely decorative
 * (`aria-label` + `title` and nothing else); "Play" duplicated the video
 * element's own native `controls`. These tests cover: Previous/Next are
 * wired and keyboard-operable, they disable themselves with a stated reason
 * at either end of the shot order, and "Play" is gone rather than left
 * inert.
 */

function makeShot(overrides: Partial<Shot> = {}): Shot {
  return {
    id: 'sh1',
    prompt: 'A careful close shot',
    camera: '',
    visual_effect: '',
    target_api: 'veo_3',
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
    ...overrides,
  }
}

function okResponse(): Response {
  return {
    ok: true,
    status: 200,
    headers: { get: () => null },
    blob: async () => new Blob(['bytes']),
  } as unknown as Response
}

describe('ShotViewer', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:mock'), revokeObjectURL: vi.fn() })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('no shot selected -> the pre-existing placeholder, no media fetch at all', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<ShotViewer projectId="p1" shot={null} scene={null} shotState={undefined} />)

    expect(screen.getByText('No shot selected')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shot selected but no generated media yet -> the pre-existing placeholder, no fetch', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    render(<ShotViewer projectId="p1" shot={makeShot()} scene={null} shotState={undefined} />)

    expect(screen.getByText('No take yet')).toBeInTheDocument()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('resolves generated_video through the DEFAULT apiBase ("/api")', async () => {
    // Regression guard: mirrors TakeStrip's identical `''` vs `??` note --
    // no apiBase prop is passed here, the common case for every real caller.
    const fetchMock = vi.fn(async () => okResponse())
    vi.stubGlobal('fetch', fetchMock)

    render(
      <ShotViewer
        projectId="p1"
        shot={makeShot({ generated_video: 'shots/sh1/outputs/motion.mp4' })}
        scene={null}
        shotState={undefined}
      />,
    )

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/projects/p1/file?path=' + encodeURIComponent('shots/sh1/outputs/motion.mp4'),
      ),
    )
  })

  it('a generated take that resolves renders through MediaAsset (video preferred over image)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okResponse()))

    render(
      <ShotViewer
        projectId="p1"
        shot={makeShot({ generated_image: 'kf.jpg', generated_video: 'motion.mp4' })}
        scene={null}
        shotState={undefined}
      />,
    )

    await waitFor(() => expect(document.querySelector('[data-media-state="ready"]')).not.toBeNull())
    expect(document.querySelector('video')).not.toBeNull()
    expect(document.querySelector('img')).toBeNull()
  })

  it('a take whose file cannot be found shows an explicit missing state, not a blank player', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 404, headers: { get: () => null } }) as unknown as Response),
    )

    render(
      <ShotViewer
        projectId="p1"
        shot={makeShot({ generated_image: 'kf.jpg' })}
        scene={null}
        shotState={undefined}
      />,
    )

    await waitFor(() => expect(screen.getByText('Media missing')).toBeInTheDocument())
  })

  it('a migrated (moved-project) take renders the media and discloses relocation', async () => {
    const headers = new Map([['X-Media-Migrated', '1']])
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        status: 200,
        headers: { get: (k: string) => headers.get(k) ?? null },
        blob: async () => new Blob(['bytes']),
      }) as unknown as Response),
    )

    render(
      <ShotViewer
        projectId="p1"
        shot={makeShot({ generated_image: '/old/root/p1/shots/sh1/outputs/kf.jpg' })}
        scene={null}
        shotState={undefined}
      />,
    )

    await waitFor(() => expect(screen.getByText(/relocated/i)).toBeInTheDocument())
  })

  it('shotState overrides the shot-level generated media (live pipeline state wins)', async () => {
    const fetchMock = vi.fn(async () => okResponse())
    vi.stubGlobal('fetch', fetchMock)

    render(
      <ShotViewer
        projectId="p1"
        shot={makeShot({ generated_video: 'stale.mp4' })}
        scene={null}
        shotState={{ generated_video: 'live.mp4' }}
      />,
    )

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith('/api/projects/p1/file?path=' + encodeURIComponent('live.mp4')),
    )
  })

  describe('transport bar (slice 13c)', () => {
    it('no longer renders a "Play" affordance -- native <video controls> owns playback', () => {
      render(<ShotViewer projectId="p1" shot={makeShot()} scene={null} shotState={undefined} />)

      expect(screen.queryByRole('button', { name: 'Play' })).toBeNull()
    })

    it('inert-affordance enumeration: every transport button is either wired or disabled with a stated reason', () => {
      const onPrevShot = vi.fn()
      const onNextShot = vi.fn()
      render(
        <ShotViewer
          projectId="p1"
          shot={makeShot()}
          scene={null}
          shotState={undefined}
          onPrevShot={onPrevShot}
          onNextShot={onNextShot}
          hasPrevShot={false}
          hasNextShot={true}
        />,
      )

      const prev = screen.getByRole('button', { name: 'Previous shot' })
      const next = screen.getByRole('button', { name: 'Next shot' })

      // Disabled control states its reason rather than looking clickable.
      expect(prev).toBeDisabled()
      expect(prev).toHaveAttribute('title', 'Already at the first shot')

      // Enabled control actually invokes its callback -- not a dead click.
      expect(next).toBeEnabled()
      fireClick(next)
      expect(onNextShot).toHaveBeenCalledTimes(1)
      expect(onPrevShot).not.toHaveBeenCalled()
    })

    it('with no navigation wired at all, Previous/Next default to disabled instead of silently doing nothing', () => {
      render(<ShotViewer projectId="p1" shot={makeShot()} scene={null} shotState={undefined} />)

      expect(screen.getByRole('button', { name: 'Previous shot' })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Next shot' })).toBeDisabled()
    })

    it('"Next shot" is keyboard-operable: Tab to it and press Enter, no pointer input', async () => {
      const onNextShot = vi.fn()
      render(
        <ShotViewer
          projectId="p1"
          shot={makeShot()}
          scene={null}
          shotState={undefined}
          onNextShot={onNextShot}
          hasNextShot={true}
        />,
      )

      const next = screen.getByRole('button', { name: 'Next shot' })
      next.focus()
      expect(next).toHaveFocus()

      await userEvent.keyboard('{Enter}')

      expect(onNextShot).toHaveBeenCalledTimes(1)
    })

    it('"Previous shot" is keyboard-operable via Space', async () => {
      const onPrevShot = vi.fn()
      render(
        <ShotViewer
          projectId="p1"
          shot={makeShot()}
          scene={null}
          shotState={undefined}
          onPrevShot={onPrevShot}
          hasPrevShot={true}
        />,
      )

      const prev = screen.getByRole('button', { name: 'Previous shot' })
      prev.focus()

      await userEvent.keyboard(' ')

      expect(onPrevShot).toHaveBeenCalledTimes(1)
    })
  })
})

/** Plain DOM click -- distinct from `userEvent` so the keyboard-only tests
 *  above are unambiguously exercising keyboard activation, not a shared
 *  click helper. */
function fireClick(el: HTMLElement) {
  el.click()
}
