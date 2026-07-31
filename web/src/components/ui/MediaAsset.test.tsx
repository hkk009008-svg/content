import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MediaAsset from './MediaAsset'

/**
 * Slice 10 (2026-07-30 comprehensive-unification plan, plan slice 10) --
 * one UI test per explicit media state (idle / loading / ready / migrated /
 * missing), proving the defect fix: a blank box with no explanation is no
 * longer possible for any of these outcomes.
 */

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

function fakeResponse(opts: { ok: boolean; migrated?: boolean }): Response {
  const headers = new Map<string, string>()
  if (opts.migrated) headers.set('X-Media-Migrated', '1')
  return {
    ok: opts.ok,
    status: opts.ok ? 200 : 404,
    headers: { get: (key: string) => headers.get(key) ?? null },
    blob: async () => new Blob(['bytes']),
  } as unknown as Response
}

describe('MediaAsset', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL: vi.fn(() => 'blob:mock-1'),
      revokeObjectURL: vi.fn(),
    })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('idle: no url shows the neutral empty-state label, not a blank box', () => {
    vi.stubGlobal('fetch', vi.fn())
    render(<MediaAsset kind="image" url={null} emptyLabel="No take yet" />)

    expect(screen.getByText('No take yet')).toBeInTheDocument()
    const frame = screen.getByText('No take yet').closest('[data-media-state]')
    expect(frame).toHaveAttribute('data-media-state', 'idle')
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })

  it('loading: fetch in flight shows the loading indicator, not a blank box', async () => {
    const { promise } = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(() => promise))

    render(<MediaAsset kind="image" url="/api/projects/p1/file?path=x.jpg" />)

    expect(screen.getByText('Loading')).toBeInTheDocument()
    const frame = screen.getByText('Loading').closest('[data-media-state]')
    expect(frame).toHaveAttribute('data-media-state', 'loading')
  })

  it('ready: a successful fetch renders the image with the object-URL src', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => fakeResponse({ ok: true })))

    render(<MediaAsset kind="image" url="/api/projects/p1/file?path=x.jpg" alt="a keyframe" />)

    const img = await screen.findByAltText('a keyframe')
    expect(img).toHaveAttribute('src', 'blob:mock-1')
    expect(img.closest('[data-media-state]')).toHaveAttribute('data-media-state', 'ready')
    expect(screen.queryByText(/relocated/i)).not.toBeInTheDocument()
  })

  it('migrated: a successful fetch with X-Media-Migrated renders the media AND discloses relocation', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => fakeResponse({ ok: true, migrated: true })))

    render(<MediaAsset kind="video" url="/api/projects/p1/file?path=/old/root/p1/take.mp4" />)

    await waitFor(() => expect(screen.getByText(/relocated/i)).toBeInTheDocument())
    const frame = screen.getByText(/relocated/i).closest('[data-media-state]')
    expect(frame).toHaveAttribute('data-media-state', 'migrated')
    // The <video> element is present and sourced -- media still plays.
    const video = frame!.querySelector('video')
    expect(video).toHaveAttribute('src', 'blob:mock-1')
  })

  it('missing: a 404 response shows an explicit "media missing" message, not blank media', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => fakeResponse({ ok: false })))

    render(<MediaAsset kind="image" url="/api/projects/p1/file?path=gone.jpg" />)

    await waitFor(() => expect(screen.getByText('Media missing')).toBeInTheDocument())
    const frame = screen.getByText('Media missing').closest('[data-media-state]')
    expect(frame).toHaveAttribute('data-media-state', 'missing')
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
