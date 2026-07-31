import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsInspector from './SettingsInspector'
import type { AppConfig, Project } from '../../types/project'

/**
 * Rule #13 symmetric-endpoint follow-up to the ShotInspector truthfulness fix.
 * Two mutation sites here mishandled failure on endpoints ShotInspector also
 * writes:
 *
 *   `update(key, value)` (PUT /api/projects/{pid}) was a PARTIAL instance --
 *   it gated the refresh on `res.ok`, so it never clobbered state, but it
 *   swallowed the failure entirely: no error surfaced and the control kept
 *   rendering the old value with no explanation. That is a repeatable
 *   outcome, not a theoretical one -- the route fails closed with 409
 *   `settings_revision_conflict` on a stale `global_settings.revision`.
 *
 *   `generateStyleRules` (POST /api/projects/{pid}/style-rules) was the full
 *   defect: no `.ok` check and an unconditional `onRefresh()`.
 *
 * Both now run through the shared `runMutation`, so the contract below is the
 * same one ShotInspector pins: a non-2xx or network failure surfaces the
 * inline banner and does NOT refresh; a confirmed 2xx clears it and refreshes.
 */

function makeProject(globalSettings: Record<string, unknown> = {}): Project {
  return {
    id: 'proj-settings',
    name: 'Settings Project',
    characters: [],
    locations: [],
    objects: [],
    scenes: [],
    global_settings: {
      aspect_ratio: '16:9',
      language: 'English',
      music_mood: 'cinematic',
      color_palette: '',
      style_rules: {},
      ...globalSettings,
    },
  } as unknown as Project
}

const CONFIG: AppConfig = {
  aspect_ratios: ['16:9', '9:16'],
  music_moods: ['cinematic', 'tense'],
  voice_pool: [],
  api_registry: {},
} as unknown as AppConfig

/** `lib/api.ts`'s `apiRequest` reads the body via `res.text()` (never `.json()`). */
function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: '',
    text: vi.fn(async () => (payload === undefined ? '' : JSON.stringify(payload))),
  } as unknown as Response
}

/** The literal body `_settings_revision_conflict_payload` builds
 *  (web_server.py) and `api_update_project` returns with 409. Used verbatim so
 *  these tests pin the string an operator actually sees: `lib/api.ts` reads
 *  `body.error`, NOT `body.code`, so a payload that dropped the human-readable
 *  `error` would silently degrade the banner to a bare "HTTP 409". */
const REVISION_CONFLICT_BODY = {
  error: 'Project settings changed since last read',
  code: 'settings_revision_conflict',
  retryable: true,
  current_revision: 4,
  global_settings: {},
}

type MutationOutcome =
  | { ok?: boolean; status?: number; body?: unknown }
  | { throws: string }

function stubFetch(outcome: MutationOutcome) {
  const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
    if ('throws' in outcome) throw new Error(outcome.throws)
    const { ok = true, status = ok ? 200 : 500, body = {} } = outcome
    return response(body, ok, status)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** The 9:16 aspect-ratio pill is the cheapest `update()` trigger on the page:
 *  one click, no typing, and its value comes straight from `global_settings`
 *  so a rejected write leaves the old pill selected. */
function clickPortraitAspectRatio() {
  fireEvent.click(screen.getByRole('button', { name: '9:16' }))
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('SettingsInspector -- truthful update()', () => {
  it('surfaces a non-2xx settings PUT instead of silently no-op-ing', async () => {
    stubFetch({ ok: false, status: 409, body: REVISION_CONFLICT_BODY })
    const onRefresh = vi.fn()

    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={onRefresh} />)
    clickPortraitAspectRatio()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Project settings changed since last read',
    )
    expect(onRefresh).not.toHaveBeenCalled()
    // Still showing the server's value -- now with a reason attached.
    expect(screen.getByRole('button', { name: '16:9' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '9:16' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('surfaces a network failure on the settings PUT', async () => {
    stubFetch({ throws: 'settings unreachable' })
    const onRefresh = vi.fn()

    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={onRefresh} />)
    clickPortraitAspectRatio()

    expect(await screen.findByRole('alert')).toHaveTextContent('settings unreachable')
    expect(onRefresh).not.toHaveBeenCalled()
  })

  it('falls back to a truthful message when the rejection body carries no error string', async () => {
    stubFetch({ ok: false, status: 503, body: undefined })
    const onRefresh = vi.fn()

    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={onRefresh} />)
    clickPortraitAspectRatio()

    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 503')
    expect(onRefresh).not.toHaveBeenCalled()
  })

  it('refreshes and shows no banner after a confirmed 2xx settings PUT', async () => {
    const fetchMock = stubFetch({ ok: true })
    const onRefresh = vi.fn()

    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={onRefresh} />)
    clickPortraitAspectRatio()

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).toBeNull()

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/projects/proj-settings')
    expect(init!.method).toBe('PUT')
    expect(JSON.parse(init!.body as string).global_settings.aspect_ratio).toBe('9:16')
  })

  it('clears a previous banner once a later write succeeds', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response(REVISION_CONFLICT_BODY, false, 409))
      .mockImplementationOnce(async () => response({}, true, 200))
    vi.stubGlobal('fetch', fetchMock)
    const onRefresh = vi.fn()

    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={onRefresh} />)
    clickPortraitAspectRatio()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Project settings changed since last read',
    )

    clickPortraitAspectRatio()
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('SettingsInspector -- truthful generateStyleRules()', () => {
  it('surfaces a non-2xx style-rules POST and does not refresh', async () => {
    stubFetch({ ok: false, status: 500, body: { error: 'style rule generation failed' } })
    const onRefresh = vi.fn()

    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={onRefresh} />)
    fireEvent.click(screen.getByRole('button', { name: '+ Generate' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('style rule generation failed')
    expect(onRefresh).not.toHaveBeenCalled()
  })

  it('surfaces a network failure on the style-rules POST and does not refresh', async () => {
    stubFetch({ throws: 'style-rules unreachable' })
    const onRefresh = vi.fn()

    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={onRefresh} />)
    fireEvent.click(screen.getByRole('button', { name: '+ Generate' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('style-rules unreachable')
    expect(onRefresh).not.toHaveBeenCalled()
  })

  it('re-enables the generate button after a failure so the operator can retry', async () => {
    stubFetch({ ok: false, status: 500, body: { error: 'style rule generation failed' } })

    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '+ Generate' }))

    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ Generate' })).not.toBeDisabled()
  })

  it('refreshes and shows no banner after a confirmed 2xx style-rules POST', async () => {
    const fetchMock = stubFetch({ ok: true })
    const onRefresh = vi.fn()

    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={onRefresh} />)
    fireEvent.click(screen.getByRole('button', { name: '+ Generate' }))

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).toBeNull()

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/projects/proj-settings/style-rules')
    expect(init!.method).toBe('POST')
  })
})

describe('SettingsInspector -- slice 13b busy/success feedback', () => {
  it('shows a BusyState pill while the settings PUT is in flight, and clears it once resolved', async () => {
    let resolveFetch: ((res: Response) => void) | undefined
    const fetchMock = vi.fn(() => new Promise<Response>((resolve) => { resolveFetch = resolve }))
    vi.stubGlobal('fetch', fetchMock)

    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={vi.fn()} />)
    clickPortraitAspectRatio()

    expect(await screen.findByText('Saving settings')).toBeInTheDocument()

    resolveFetch?.(response({}))
    await waitFor(() => expect(screen.queryByText('Saving settings')).toBeNull())
  })

  it('announces a saved confirmation via a polite live region, not a persistent visible card', async () => {
    stubFetch({ ok: true })

    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={vi.fn()} />)
    clickPortraitAspectRatio()

    const notice = await screen.findByText(/Saved aspect ratio/i)
    // A LiveRegion announcement (role="status", sr-only), not an ErrorState
    // -shaped dismissible card that would fire on every keystroke/drag tick.
    expect(notice).toHaveAttribute('role', 'status')
    expect(screen.queryByRole('button', { name: /Dismiss/i })).toBeNull()
  })
})
