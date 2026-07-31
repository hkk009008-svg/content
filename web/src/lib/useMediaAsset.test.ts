import { cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useMediaAsset } from './useMediaAsset'

/**
 * Slice 10 (2026-07-30 comprehensive-unification plan, plan slice 10) --
 * portable media persistence + explicit media states. Covers the hook's
 * state machine: idle / loading / ready / migrated / missing, plus object
 * URL lifecycle (created once per successful fetch, revoked on url change
 * and on unmount).
 */

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

function fakeResponse(opts: { ok: boolean; migrated?: boolean; blobText?: string }): Response {
  const headers = new Map<string, string>()
  if (opts.migrated) headers.set('X-Media-Migrated', '1')
  return {
    ok: opts.ok,
    status: opts.ok ? 200 : 404,
    headers: { get: (key: string) => headers.get(key) ?? null },
    blob: async () => new Blob([opts.blobText ?? 'bytes']),
  } as unknown as Response
}

describe('useMediaAsset', () => {
  let createObjectURL: ReturnType<typeof vi.fn>
  let revokeObjectURL: ReturnType<typeof vi.fn>

  beforeEach(() => {
    let counter = 0
    createObjectURL = vi.fn(() => `blob:mock-${++counter}`)
    revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('idle: no url -> idle state, no fetch performed', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useMediaAsset(null))

    expect(result.current).toEqual({ state: 'idle', src: null })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('loading: fetch in flight -> loading state before it resolves', async () => {
    const { promise } = deferred<Response>()
    const fetchMock = vi.fn(() => promise)
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useMediaAsset('/api/projects/p1/file?path=x.jpg'))

    expect(result.current.state).toBe('loading')
    expect(fetchMock).toHaveBeenCalledWith('/api/projects/p1/file?path=x.jpg')
  })

  it('ready: 200 with no migration header -> ready state with an object-URL src', async () => {
    const fetchMock = vi.fn(async () => fakeResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useMediaAsset('/api/projects/p1/file?path=x.jpg'))

    await waitFor(() => expect(result.current.state).toBe('ready'))
    expect(result.current.src).toBe('blob:mock-1')
    expect(createObjectURL).toHaveBeenCalledTimes(1)
  })

  it('migrated: 200 with X-Media-Migrated header -> migrated state, media still resolves', async () => {
    const fetchMock = vi.fn(async () => fakeResponse({ ok: true, migrated: true }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useMediaAsset('/api/projects/p1/file?path=/old/root/p1/take.mp4'))

    await waitFor(() => expect(result.current.state).toBe('migrated'))
    expect(result.current.src).toBe('blob:mock-1')
  })

  it('missing: non-2xx response -> missing state, no object URL created', async () => {
    const fetchMock = vi.fn(async () => fakeResponse({ ok: false }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useMediaAsset('/api/projects/p1/file?path=gone.jpg'))

    await waitFor(() => expect(result.current.state).toBe('missing'))
    expect(result.current.src).toBeNull()
    expect(createObjectURL).not.toHaveBeenCalled()
  })

  it('missing: a network error (fetch rejects) -> missing state, not an unhandled rejection', async () => {
    const fetchMock = vi.fn(() => Promise.reject(new Error('offline')))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useMediaAsset('/api/projects/p1/file?path=x.jpg'))

    await waitFor(() => expect(result.current.state).toBe('missing'))
    expect(result.current.src).toBeNull()
  })

  it('revokes the previous object URL when the url prop changes', async () => {
    const fetchMock = vi.fn(async () => fakeResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    const { result, rerender } = renderHook(({ url }) => useMediaAsset(url), {
      initialProps: { url: '/api/projects/p1/file?path=a.jpg' as string | null },
    })
    await waitFor(() => expect(result.current.state).toBe('ready'))
    expect(result.current.src).toBe('blob:mock-1')

    rerender({ url: '/api/projects/p1/file?path=b.jpg' })
    await waitFor(() => expect(result.current.src).toBe('blob:mock-2'))

    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-1')
  })

  it('revokes the object URL on unmount', async () => {
    const fetchMock = vi.fn(async () => fakeResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    const { result, unmount } = renderHook(() => useMediaAsset('/api/projects/p1/file?path=a.jpg'))
    await waitFor(() => expect(result.current.state).toBe('ready'))

    unmount()

    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-1')
  })

  it('clearing the url back to null revokes the object URL and returns to idle', async () => {
    const fetchMock = vi.fn(async () => fakeResponse({ ok: true }))
    vi.stubGlobal('fetch', fetchMock)

    const { result, rerender } = renderHook(({ url }) => useMediaAsset(url), {
      initialProps: { url: '/api/projects/p1/file?path=a.jpg' as string | null },
    })
    await waitFor(() => expect(result.current.state).toBe('ready'))

    rerender({ url: null })

    expect(result.current).toEqual({ state: 'idle', src: null })
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-1')
  })
})
