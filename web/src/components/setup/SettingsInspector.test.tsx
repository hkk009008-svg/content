import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsInspector from './SettingsInspector'
import type { AppConfig, Project } from '../../types/project'

// GPU worker readiness owns its asynchronous request contract in
// GpuWorkersSection.test.tsx. Keep these settings-mutation tests isolated so
// their one-shot fetch fixtures continue to describe only the PATCH/POST
// under test; the placeholder still proves SettingsInspector mounts the new
// section in its composition.
vi.mock('./inspector/GpuWorkersSection', () => ({
  GpuWorkersSection: () => <div data-testid="gpu-workers-section" />,
}))

/**
 * Rule #13 symmetric-endpoint follow-up to the ShotInspector truthfulness fix.
 * Two mutation sites here mishandled failure on endpoints ShotInspector also
 * writes:
 *
 *   `update(key, value)` (formerly PUT /api/projects/{pid}) was a PARTIAL instance --
 *   it gated the refresh on `res.ok`, so it never clobbered state, but it
 *   swallowed the failure entirely: no error surfaced and the control kept
 *   rendering the old value with no explanation. That is a repeatable
 *   outcome, not a theoretical one -- the route fails closed with 409
 *   `settings_revision_conflict` on a stale `global_settings.revision`.
 *
 *   `generateStyleRules` (POST /api/projects/{pid}/style-rules) was the full
 *   defect: no `.ok` check and an unconditional `onRefresh()`.
 *
 * Both now share truthful failure handling: a non-conflict HTTP/network
 * failure surfaces the inline banner without refresh; a revision conflict is
 * adopted and retried once (then refreshed if a second race wins); a confirmed
 * 2xx clears the banner and refreshes authoritative project state.
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
  it('mounts GPU worker readiness in the inspector', () => {
    render(<SettingsInspector project={makeProject()} config={CONFIG} onRefresh={vi.fn()} />)

    expect(screen.getByTestId('gpu-workers-section')).toBeInTheDocument()
  })

  it('surfaces a non-2xx settings PATCH instead of silently no-op-ing', async () => {
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

  it('surfaces a network failure on the settings PATCH', async () => {
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

  it('PATCHes only the changed setting with the current revision, then refreshes', async () => {
    const fetchMock = stubFetch({ ok: true })
    const onRefresh = vi.fn()

    render(<SettingsInspector project={makeProject({ revision: 7 })} config={CONFIG} onRefresh={onRefresh} />)
    clickPortraitAspectRatio()

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).toBeNull()

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/projects/proj-settings')
    expect(init!.method).toBe('PATCH')
    expect(JSON.parse(init!.body as string)).toEqual({
      global_settings: { revision: 7, aspect_ratio: '9:16' },
    })
  })

  it('exposes location research as an accessible, revision-bound Setup control', async () => {
    const fetchMock = stubFetch({ ok: true })
    const onRefresh = vi.fn()

    render(
      <SettingsInspector
        project={makeProject({ revision: 5 })}
        config={CONFIG}
        onRefresh={onRefresh}
      />,
    )

    const control = screen.getByRole('switch', { name: 'Research location references' })
    expect(control).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText(/Requires Tavily; off by default/)).toBeInTheDocument()
    fireEvent.click(control)

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string)).toEqual({
      global_settings: { revision: 5, location_research: true },
    })
  })

  it('PATCHes auto-approve as one nested setting without dropping its unexposed gate rules', async () => {
    const fetchMock = stubFetch({ ok: true })
    const current = {
      enabled: true,
      final_min_lipsync: 0.8,
      final_require_human_if_upstream_auto: true,
      image_min_composite: 0.6,
    }

    render(
      <SettingsInspector
        project={makeProject({ revision: 3, auto_approve: current })}
        config={CONFIG}
        onRefresh={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByRole('switch', { name: 'Auto-approve eligible gates' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/projects/proj-settings')
    expect(init!.method).toBe('PATCH')
    expect(JSON.parse(init!.body as string)).toEqual({
      global_settings: {
        revision: 3,
        auto_approve: { ...current, enabled: false },
      },
    })
  })

  it('serializes rapid settings writes and advances the revision from each success', async () => {
    let resolveFirst: ((value: Response) => void) | undefined
    let resolveSecond: ((value: Response) => void) | undefined
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveFirst = resolve }))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { resolveSecond = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    const onRefresh = vi.fn()

    render(
      <SettingsInspector
        project={makeProject({ revision: 7 })}
        config={CONFIG}
        onRefresh={onRefresh}
      />,
    )
    clickPortraitAspectRatio()
    fireEvent.click(screen.getByRole('switch', { name: 'Auto-approve eligible gates' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    resolveFirst?.(response(makeProject({ revision: 8, aspect_ratio: '9:16' })))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    const secondBody = JSON.parse(fetchMock.mock.calls[1][1]!.body as string)
    expect(secondBody.global_settings.revision).toBe(8)
    expect(secondBody.global_settings.auto_approve.enabled).toBe(false)

    resolveSecond?.(response(makeProject({ revision: 9 })))
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(2))
  })

  it('adopts the authoritative 409 snapshot, rebases the intent, and retries once', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response({
        ...REVISION_CONFLICT_BODY,
        global_settings: { revision: 4, aspect_ratio: '16:9', concurrent_key: 'preserved' },
      }, false, 409))
      .mockImplementationOnce(async () => response(makeProject({
        revision: 5,
        aspect_ratio: '9:16',
        concurrent_key: 'preserved',
      }), true, 200))
    vi.stubGlobal('fetch', fetchMock)
    const onRefresh = vi.fn()

    render(<SettingsInspector project={makeProject({ revision: 1 })} config={CONFIG} onRefresh={onRefresh} />)
    clickPortraitAspectRatio()

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(JSON.parse(fetchMock.mock.calls[1][1]!.body as string)).toEqual({
      global_settings: { revision: 4, aspect_ratio: '9:16' },
    })
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('adopts a second raced conflict so the next user edit does not stay wedged on an old revision', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response({
        ...REVISION_CONFLICT_BODY,
        current_revision: 4,
        global_settings: { revision: 4, aspect_ratio: '16:9' },
      }, false, 409))
      .mockImplementationOnce(async () => response({
        ...REVISION_CONFLICT_BODY,
        current_revision: 5,
        global_settings: { revision: 5, aspect_ratio: '16:9' },
      }, false, 409))
      .mockImplementationOnce(async () => response(makeProject({ revision: 6, aspect_ratio: '9:16' })))
    vi.stubGlobal('fetch', fetchMock)
    const onRefresh = vi.fn()

    render(<SettingsInspector project={makeProject({ revision: 1 })} config={CONFIG} onRefresh={onRefresh} />)
    clickPortraitAspectRatio()
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Project settings changed since last read',
    )

    clickPortraitAspectRatio()
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    expect(JSON.parse(fetchMock.mock.calls[2][1]!.body as string).global_settings.revision).toBe(5)
    expect(screen.queryByRole('alert')).toBeNull()
  })
})

describe('SettingsInspector -- truthful generateStyleRules()', () => {
  it('sends the revision token, adopts a 409 snapshot, and retries style generation once', async () => {
    const fetchMock = vi.fn()
      .mockImplementationOnce(async () => response({
        ...REVISION_CONFLICT_BODY,
        current_revision: 4,
        global_settings: { revision: 4, music_mood: 'cinematic', color_palette: '' },
      }, false, 409))
      .mockImplementationOnce(async () => response({ style_rules: { lighting: 'soft' } }))
    vi.stubGlobal('fetch', fetchMock)
    const onRefresh = vi.fn()

    render(
      <SettingsInspector
        project={makeProject({ revision: 1 })}
        config={CONFIG}
        onRefresh={onRefresh}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '+ Generate' }))

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(JSON.parse(fetchMock.mock.calls[1][1]!.body as string)).toMatchObject({
      expected_revision: 4,
    })
    expect(screen.queryByRole('alert')).toBeNull()
  })

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
    expect(JSON.parse(init!.body as string)).toMatchObject({ expected_revision: 0 })
  })
})

describe('SettingsInspector -- slice 13b busy/success feedback', () => {
  it('shows a BusyState pill while the settings PATCH is in flight, and clears it once resolved', async () => {
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
