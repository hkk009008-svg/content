import { useEffect, useRef, useState } from 'react'

/**
 * useMediaAsset — fetches a project media URL (typically the
 * `/api/projects/<pid>/file?path=...` endpoint, but works for any
 * same-origin media URL) and classifies the result into an explicit state
 * the UI can render, instead of leaving an `<img>`/`<video>` to fail
 * silently blank when the underlying file can't be found.
 *
 * Slice 10 (2026-07-30 comprehensive-unification plan): persisted take/shot
 * paths are project-relative now (Product invariant #6), and a project that
 * was relocated to a new repo root resolves its OLD absolute-path takes via
 * a safe suffix migration on the backend (`/file`'s `X-Media-Migrated`
 * response header signals when that happened). The UI needs to tell the
 * operator apart:
 *
 *   'idle'     -- no url given (nothing generated yet for this slot; the
 *                 caller decides whether to show a neutral placeholder).
 *   'loading'  -- the fetch is in flight.
 *   'ready'    -- 200, served directly -- no migration was needed.
 *   'migrated' -- 200, but the backend had to re-root a legacy absolute
 *                 path -- the project was relocated since this take was
 *                 generated. Media still plays; the UI can disclose this.
 *   'missing'  -- a non-2xx response (403/404/...), or the fetch itself
 *                 failed (offline, network error) -- there is nothing to
 *                 show, and the UI must say so rather than render blank.
 *
 * One fetch per url drives both the state classification AND the actual
 * media: the response body becomes an object URL for the caller to use
 * directly as `<img>`/`<video>` `src`, so there is no separate HEAD probe
 * plus a second load. The object URL is revoked on url change and unmount.
 */
export type MediaAssetState = 'idle' | 'loading' | 'ready' | 'migrated' | 'missing'

export interface MediaAssetResult {
  state: MediaAssetState
  /** Object URL for the fetched blob. Only set for 'ready' / 'migrated'. */
  src: string | null
}

const IDLE_RESULT: MediaAssetResult = { state: 'idle', src: null }

export function useMediaAsset(url: string | null | undefined): MediaAssetResult {
  const [result, setResult] = useState<MediaAssetResult>(url ? { state: 'loading', src: null } : IDLE_RESULT)
  const objectUrlRef = useRef<string | null>(null)

  useEffect(() => {
    const revokePrevious = () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current)
        objectUrlRef.current = null
      }
    }

    if (!url) {
      revokePrevious()
      setResult(IDLE_RESULT)
      return
    }

    let cancelled = false
    setResult({ state: 'loading', src: null })

    fetch(url)
      .then(async (res) => {
        if (cancelled) return
        if (!res.ok) {
          setResult({ state: 'missing', src: null })
          return
        }
        const blob = await res.blob()
        if (cancelled) return
        revokePrevious()
        const objectUrl = URL.createObjectURL(blob)
        objectUrlRef.current = objectUrl
        setResult({
          state: res.headers.get('X-Media-Migrated') ? 'migrated' : 'ready',
          src: objectUrl,
        })
      })
      .catch(() => {
        if (!cancelled) setResult({ state: 'missing', src: null })
      })

    return () => {
      cancelled = true
    }
  }, [url])

  // Final cleanup on unmount -- the per-url effect above already revokes the
  // PREVIOUS object URL on every url change; this catches the LAST one.
  useEffect(() => {
    return () => {
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current)
        objectUrlRef.current = null
      }
    }
  }, [])

  return result
}
