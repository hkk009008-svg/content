import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TakeStrip from './TakeStrip'

/**
 * Slice 10 (2026-07-30 comprehensive-unification plan, plan slice 10) --
 * TakeStrip used to build its own `/file?path=` URL and hand it straight to
 * `<img>`/`<video>`. It now shares `lib/mediaUrl.ts`'s `fileUrl` (removing a
 * private duplicate) and renders through MediaAsset, so a stale/moved take
 * path shows an explicit state instead of a blank pane. The full
 * idle/loading/ready/migrated/missing matrix is covered once in
 * ui/MediaAsset.test.tsx; these tests prove TakeStrip's own wiring
 * (URL construction with a default apiBase, per-pane rendering).
 */

function okResponse(): Response {
  return {
    ok: true,
    status: 200,
    headers: { get: () => null },
    blob: async () => new Blob(['bytes']),
  } as unknown as Response
}

describe('TakeStrip', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', { ...URL, createObjectURL: vi.fn(() => 'blob:mock'), revokeObjectURL: vi.fn() })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('renders nothing when no pane has a URL', () => {
    vi.stubGlobal('fetch', vi.fn())
    const { container } = render(<TakeStrip projectId="p1" />)
    expect(container).toBeEmptyDOMElement()
  })

  it('resolves each pane through the DEFAULT apiBase ("/api"), not a malformed base', async () => {
    // Regression guard: TakeStrip previously defaulted its own `apiBase` prop
    // to '' before building the URL string itself; naively delegating that
    // default straight to fileUrl (which falls back via `??`, not `||`)
    // would keep '' instead of '/api'. No `apiBase` prop is passed here --
    // the common case for every real caller.
    const fetchMock = vi.fn(async () => okResponse())
    vi.stubGlobal('fetch', fetchMock)

    render(<TakeStrip projectId="p1" keyframeUrl="shots/sh1/outputs/kf.jpg" />)

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/projects/p1/file?path=' + encodeURIComponent('shots/sh1/outputs/kf.jpg'),
      ),
    )
  })

  it('renders a labeled pane per non-empty URL prop, each through MediaAsset', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okResponse()))

    render(
      <TakeStrip
        projectId="p1"
        keyframeUrl="kf.jpg"
        drivingUrl="driving.mp4"
        performanceUrl="perf.mp4"
        motionUrl="motion.mp4"
      />,
    )

    expect(screen.getByText('Keyframe')).toBeInTheDocument()
    expect(screen.getByText('Driving reference')).toBeInTheDocument()
    expect(screen.getByText('Captured performance')).toBeInTheDocument()
    expect(screen.getByText('Motion render')).toBeInTheDocument()

    await waitFor(() =>
      expect(document.querySelectorAll('[data-media-state="ready"]')).toHaveLength(4),
    )
  })

  it('a moved/missing take shows an explicit missing pane instead of a blank image', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 403, headers: { get: () => null } }) as unknown as Response),
    )

    render(<TakeStrip projectId="p1" keyframeUrl="shots/sh1/outputs/kf.jpg" />)

    await waitFor(() => expect(screen.getByText('Media missing')).toBeInTheDocument())
  })

  it('without a projectId, resolve() falls back to the raw path (best-effort, matches fileUrl contract)', async () => {
    const fetchMock = vi.fn(async () => okResponse())
    vi.stubGlobal('fetch', fetchMock)

    render(<TakeStrip keyframeUrl="/already/resolved/kf.jpg" />)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/already/resolved/kf.jpg'))
  })

  it.each(['PASS', 'FAIL', 'UNKNOWN'] as const)(
    'renders the persisted lip-sync validation state %s explicitly',
    async (state) => {
      vi.stubGlobal('fetch', vi.fn(async () => okResponse()))

      render(
        <TakeStrip
          projectId="p1"
          motionUrl="motion.mp4"
          lipsyncValidationState={state}
          lipsyncCascadeMetadata={{
            engine: 'SYNC_SO_V3',
            score: state === 'UNKNOWN' ? null : state === 'PASS' ? 0.8 : 0.4,
            threshold: 0.65,
            validation_state: state,
          }}
        />,
      )

      expect(
        screen.getByRole('status', { name: `Lip-sync validation: ${state}` }),
      ).toBeInTheDocument()
      await waitFor(() =>
        expect(document.querySelectorAll('[data-media-state="ready"]')).toHaveLength(1),
      )
    },
  )

  it('treats provider-native dialogue audio without measured sync evidence as UNKNOWN, never PASS', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okResponse()))

    render(
      <TakeStrip
        projectId="p1"
        motionUrl="native-dialogue.mp4"
        hasDialogue={true}
        cascadeMetadata={{ engine: 'VEO_NATIVE', native_audio_generated: true }}
      />,
    )

    expect(screen.getByText('Native audio')).toBeInTheDocument()
    expect(
      screen.getByRole('status', { name: 'Lip-sync validation: UNKNOWN' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Manual review required')).toBeInTheDocument()
    expect(screen.queryByText('Lip-sync PASS')).toBeNull()
    await waitFor(() =>
      expect(document.querySelectorAll('[data-media-state="ready"]')).toHaveLength(1),
    )
  })

  it('treats dialogue with no lip-sync metadata at all as UNKNOWN', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okResponse()))

    render(
      <TakeStrip
        projectId="p1"
        motionUrl="dialogue-without-evidence.mp4"
        hasDialogue={true}
      />,
    )

    expect(
      screen.getByRole('status', { name: 'Lip-sync validation: UNKNOWN' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Manual review required')).toBeInTheDocument()
    await waitFor(() =>
      expect(document.querySelectorAll('[data-media-state="ready"]')).toHaveLength(1),
    )
  })

  it('normalizes an unrecognized future validation value to fail-closed UNKNOWN', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okResponse()))

    render(
      <TakeStrip
        projectId="p1"
        motionUrl="motion.mp4"
        lipsyncValidationState="UNAVAILABLE"
      />,
    )

    expect(
      screen.getByRole('status', { name: 'Lip-sync validation: UNKNOWN' }),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(document.querySelectorAll('[data-media-state="ready"]')).toHaveLength(1),
    )
  })
})
