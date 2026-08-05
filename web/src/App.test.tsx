import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import type { Project } from './types/project'

/**
 * Slice 8b (2026-07-30 comprehensive-unification plan, plan slice 8) --
 * App.tsx-owned PID-boundary reset and truthful generate/cancel mutations.
 * `usePipelineState`'s own project-scoped state (shots/failures/action-
 * authority/stale-response guarding) is covered directly and thoroughly in
 * hooks/usePipelineState.test.ts; this file covers the glue App.tsx itself
 * owns: config/budget-halt/error-toast/page reset on a project switch, and
 * generate/cancel never painting optimistic success.
 *
 * AppShell and ProjectSelector are mocked (matching AppShell.test.tsx's own
 * "isolate from network-heavy real pages" idiom) so these tests exercise
 * App.tsx's logic without mounting the full four-page product.
 */

vi.mock('./components/AppShell', () => ({
  default: (props: any) => (
    <div data-testid="mock-appshell">
      <div data-testid="project-id">{props.project.id}</div>
      <div data-testid="generating">{String(props.generating)}</div>
      <div data-testid="budget-halt">{props.budgetHalt ? props.budgetHalt.stage : 'none'}</div>
      <div data-testid="config-marker">{props.config?.test_marker ?? 'none'}</div>
      <button onClick={props.onGenerate}>do-generate</button>
      <button onClick={() => props.onGenerateMotion('shot-1')}>do-generate-motion</button>
      <button onClick={props.onResumeFromCheckpoint}>do-resume-checkpoint</button>
      <button onClick={props.onCancel}>do-cancel</button>
      <button onClick={props.onBackToProjects}>back-to-projects</button>
      <button onClick={props.onRefreshProject}>do-refresh</button>
    </div>
  ),
}))

vi.mock('./components/ProjectSelector', () => ({
  default: ({ onSelect }: { onSelect: (id: string) => Promise<void> }) => {
    const [error, setError] = useState('')
    const select = (id: string) => {
      void onSelect(id).catch((err) => {
        setError(err instanceof Error ? err.message : 'Project could not be opened')
      })
    }
    return (
      <div data-testid="mock-project-selector">
        <button onClick={() => select('proj-A')}>select-A</button>
        <button onClick={() => select('proj-B')}>select-B</button>
        {error && <div role="alert">{error}</div>}
      </div>
    )
  },
}))

class MockEventSource {
  static instances: MockEventSource[] = []
  readonly url: string
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  close = vi.fn()
  constructor(url: string | URL) {
    this.url = String(url)
    MockEventSource.instances.push(this)
  }
  emit(event: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(event) } as MessageEvent<string>)
  }
}

function makeProject(id: string): Project {
  return {
    id,
    name: `Project ${id}`,
    characters: [],
    locations: [],
    objects: [],
    scenes: [{
      id: 'scene-1', order: 0, title: '', location_id: '', characters_present: [], action: '',
      dialogue: '', mood: '', camera_direction: '', duration_seconds: 4, num_shots: 1, shots: [],
    }],
    global_settings: { aspect_ratio: '16:9', music_mood: '', color_palette: '', style_rules: {} },
  }
}

function projectWithConfigState(id: string, revision: number, targetApi: string): Project {
  const project = makeProject(id)
  project.global_settings.revision = revision
  project.scenes[0].shots = [{ id: 'shot-1', target_api: targetApi } as any]
  return project
}

function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    text: vi.fn(async () => JSON.stringify(payload)),
  } as unknown as Response
}

/** Same shape as the `deferred<T>()` helper in usePipelineState.test.ts --
 *  lets a test resolve a specific in-flight fetch on demand, so an
 *  out-of-order (stale-wins-the-race) scenario can be driven deterministically
 *  instead of guessed at with timers. */
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => { resolve = res })
  return { promise, resolve }
}

function idlePipelineState(overrides: { running?: boolean; allowed_actions?: string[] } = {}) {
  return {
    paused: false, cancelled: false, current_stage: '', current_scene_id: '', current_shot_id: '',
    shot_results: {}, failed_shots: [], scenes_completed: 0,
    gate_status: { total_shots: 0, plans_approved: 0, keyframes_approved: 0, motions_generated: 0, finals_approved: 0 },
    running: false, allowed_actions: ['start'],
    ...overrides,
  }
}

interface RouteOverrides {
  generate?: { ok: boolean; status?: number; body?: unknown }
  cancel?: { ok: boolean; status?: number; body?: unknown }
  motion?: { ok: boolean; status?: number; body?: unknown }
  initialRunning?: boolean
}

function stubFetch(overrides: RouteOverrides = {}) {
  // Mirrors the real backend: a successful /generate flips the pipeline
  // into _running_pipelines, so the NEXT pipeline-state read reports
  // running=true -- a stateless "always idle" mock would falsely fail a
  // "generating flips true after a successful generate" assertion for a
  // reason that has nothing to do with App.tsx's own logic.
  let hasStarted = overrides.initialRunning ?? false
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.includes('/pipeline-state')) {
      return response(hasStarted
        ? idlePipelineState({ running: true, allowed_actions: ['cancel', 'pause'] })
        : idlePipelineState())
    }
    if (url.includes('/api/config')) return response({ camera_motions: [], visual_effects: [], video_engines: [], api_registry: {} })
    if (method === 'POST' && /\/api\/projects\/[^/]+\/generate$/.test(url)) {
      const o = overrides.generate ?? { ok: true }
      if (o.ok) hasStarted = true
      return response(o.body ?? (o.ok ? {} : { error: 'Generation already in progress' }), o.ok, o.status)
    }
    if (method === 'POST' && url.endsWith('/cancel')) {
      const o = overrides.cancel ?? { ok: true }
      if (o.ok) hasStarted = false
      return response(o.body ?? (o.ok ? {} : { error: 'Nothing to cancel' }), o.ok, o.status)
    }
    if (method === 'POST' && url.endsWith('/shots/shot-1/motion/generate')) {
      const o = overrides.motion ?? { ok: true }
      return response(o.body ?? (o.ok ? { success: true } : { error: 'Motion failed' }), o.ok, o.status)
    }
    if (method === 'GET' && /\/api\/projects\/[^/]+$/.test(url)) {
      const id = url.split('/').pop()!
      return response(makeProject(id))
    }
    return response({})
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  cleanup()
  sessionStorage.clear()
  vi.unstubAllGlobals()
  MockEventSource.instances = []
})

describe('App -- PID boundary reset on project switch', () => {
  it('going back to the selector and picking a different project resets config/budget-halt/error -- no leak of A into B', async () => {
    vi.stubGlobal('EventSource', MockEventSource)
    stubFetch()

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))

    // Drive project A into a BUDGET_EXCEEDED halt.
    fireEvent.click(screen.getByText('do-generate'))
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    act(() => {
      MockEventSource.instances[0].emit({ stage: 'BUDGET_EXCEEDED', detail: 'cap reached', percent: 100, spent: 12, budget: 10 })
    })
    await waitFor(() => expect(screen.getByTestId('budget-halt')).toHaveTextContent('BUDGET_EXCEEDED'))

    // Back to the selector, then a DIFFERENT project.
    fireEvent.click(screen.getByText('back-to-projects'))
    expect(screen.getByTestId('mock-project-selector')).toBeInTheDocument()

    fireEvent.click(screen.getByText('select-B'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-B'))

    // Project B must not inherit A's halt.
    expect(screen.getByTestId('budget-halt')).toHaveTextContent('none')
  })
})

describe('App -- existing run stream attachment', () => {
  it('selecting a project already running attaches SSE without POSTing a fresh generate', async () => {
    vi.stubGlobal('EventSource', MockEventSource)
    const fetchMock = stubFetch({ initialRunning: true })

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))

    await waitFor(() => expect(screen.getByTestId('generating')).toHaveTextContent('true'))
    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1))
    expect(MockEventSource.instances[0].url).toBe('/api/projects/proj-A/stream')
    expect(fetchMock.mock.calls.some(([input, init]) => (
      (init as RequestInit | undefined)?.method === 'POST'
      && String(input).endsWith('/generate')
    ))).toBe(false)
  })
})

describe('App -- root project-identity race (CRITICAL: epoch/generation guard)', () => {
  // Before the fix, `loadProject`/`refreshProject` had no epoch guard at
  // all: whichever `GET /api/projects/<id>` happened to resolve LAST won,
  // regardless of which one the user actually meant to land on. Both tests
  // below REDDEN on the pre-fix App.tsx (the stale response overwrites the
  // newer one) and pass once `loadProject` bumps/checks `projectEpochRef`.
  it('a stale in-flight load for A resolving AFTER a switch to B must not install A over B', async () => {
    const gateA = deferred<Response>()
    const gateB = deferred<Response>()
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/config')) return response({ camera_motions: [], visual_effects: [], video_engines: [], api_registry: {} })
      if (url.includes('/pipeline-state')) return response(idlePipelineState())
      if (url.endsWith('/api/projects/proj-A')) return gateA.promise
      if (url.endsWith('/api/projects/proj-B')) return gateB.promise
      return response({})
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    // Both fire while still at the selector -- `project` stays null until
    // one of these resolves, so clicking both in a row (e.g. picking A,
    // then immediately changing to B before A's slow request returns) is a
    // real, reachable sequence, not a contrived one.
    fireEvent.click(screen.getByText('select-A'))
    fireEvent.click(screen.getByText('select-B'))

    // B's request -- the user's real, later selection -- resolves first.
    await act(async () => {
      gateB.resolve(response(makeProject('proj-B')))
    })
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-B'))

    // A's stale request finally resolves LAST and must be dropped.
    await act(async () => {
      gateA.resolve(response(makeProject('proj-A')))
    })
    expect(screen.getByTestId('project-id')).toHaveTextContent('proj-B')
  })

  it('a stale in-flight refresh resolving AFTER "back to projects" must not drag the user back into the left project', async () => {
    const gateRefresh = deferred<Response>()
    let projectAFetchCount = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/api/config')) return response({ camera_motions: [], visual_effects: [], video_engines: [], api_registry: {} })
      if (url.includes('/pipeline-state')) return response(idlePipelineState())
      if (url.endsWith('/api/projects/proj-A')) {
        projectAFetchCount += 1
        // The initial select resolves right away; the SECOND request (the
        // refresh fired just before backing out) is held open.
        return projectAFetchCount === 1 ? response(makeProject('proj-A')) : gateRefresh.promise
      }
      return response({})
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))

    // Kick off a refresh and leave it in flight (held by gateRefresh).
    fireEvent.click(screen.getByText('do-refresh'))
    await waitFor(() => expect(projectAFetchCount).toBe(2))

    // The user backs out to the selector before that refresh returns.
    fireEvent.click(screen.getByText('back-to-projects'))
    expect(screen.getByTestId('mock-project-selector')).toBeInTheDocument()

    // The stale refresh resolves now -- it must not resurrect project A.
    await act(async () => {
      gateRefresh.resolve(response(makeProject('proj-A')))
    })
    expect(screen.getByTestId('mock-project-selector')).toBeInTheDocument()
    expect(screen.queryByTestId('mock-appshell')).toBeNull()
  })
})

describe('App -- project selection failure contract', () => {
  it('rejects a failed project GET so the selector can surface it and remain usable', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/projects/proj-A')) {
        return response({ error: 'Project details unavailable' }, false, 503)
      }
      return response({})
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))

    expect(await screen.findByRole('alert')).toHaveTextContent('Project details unavailable')
    expect(screen.getByTestId('mock-project-selector')).toBeInTheDocument()
    expect(screen.queryByTestId('mock-appshell')).toBeNull()
  })
})

describe('App -- same-project config refresh', () => {
  it('refetches after a settings revision and drops an older config response that resolves last', async () => {
    const staleConfig = deferred<Response>()
    let projectReads = 0
    let configReads = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/pipeline-state')) return response(idlePipelineState())
      if (url.endsWith('/api/projects/proj-A')) {
        projectReads += 1
        return response(projectWithConfigState('proj-A', projectReads - 1, 'AUTO'))
      }
      if (url.includes('/api/config')) {
        configReads += 1
        if (configReads === 1) return staleConfig.promise
        return response({
          test_marker: 'revision-1', camera_motions: [], visual_effects: [], video_engines: [], api_registry: {},
        })
      }
      return response({})
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(configReads).toBe(1))

    fireEvent.click(screen.getByText('do-refresh'))
    await waitFor(() => expect(screen.getByTestId('config-marker')).toHaveTextContent('revision-1'))
    expect(configReads).toBe(2)

    await act(async () => {
      staleConfig.resolve(response({
        test_marker: 'stale-revision-0', camera_motions: [], visual_effects: [], video_engines: [], api_registry: {},
      }))
    })
    expect(screen.getByTestId('config-marker')).toHaveTextContent('revision-1')
  })

  it('refetches when a shot target changes even if the settings revision does not', async () => {
    let projectReads = 0
    let configReads = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/pipeline-state')) return response(idlePipelineState())
      if (url.endsWith('/api/projects/proj-A')) {
        projectReads += 1
        const target = projectReads === 1 ? 'AUTO' : 'VEO_NATIVE'
        return response(projectWithConfigState('proj-A', 4, target))
      }
      if (url.includes('/api/config')) {
        configReads += 1
        return response({
          test_marker: `target-${configReads}`, camera_motions: [], visual_effects: [], video_engines: [], api_registry: {},
        })
      }
      return response({})
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('config-marker')).toHaveTextContent('target-1'))

    fireEvent.click(screen.getByText('do-refresh'))
    await waitFor(() => expect(screen.getByTestId('config-marker')).toHaveTextContent('target-2'))
    expect(configReads).toBe(2)
  })

  it('clears stale config authority and surfaces an error when refresh fails', async () => {
    let projectReads = 0
    let configReads = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/pipeline-state')) return response(idlePipelineState())
      if (url.endsWith('/api/projects/proj-A')) {
        projectReads += 1
        return response(projectWithConfigState('proj-A', projectReads - 1, 'AUTO'))
      }
      if (url.includes('/api/config')) {
        configReads += 1
        if (configReads === 1) {
          return response({
            test_marker: 'authoritative-v0', camera_motions: [], visual_effects: [], video_engines: [], api_registry: {},
          })
        }
        return response({ error: 'config probe unavailable' }, false, 503)
      }
      return response({})
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('config-marker')).toHaveTextContent('authoritative-v0'))

    fireEvent.click(screen.getByText('do-refresh'))

    await waitFor(() => expect(screen.getByTestId('config-marker')).toHaveTextContent('none'))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Configuration refresh failed: config probe unavailable',
    )
  })
})

describe('App -- truthful generate/cancel (never paint optimistic success)', () => {
  it('a rejected /generate does not switch the shell into a generating state', async () => {
    stubFetch({ generate: { ok: false, status: 409, body: { error: 'Generation already in progress' } } })

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))

    fireEvent.click(screen.getByText('do-generate'))

    expect(await screen.findByRole('alert')).toHaveTextContent('Generation already in progress')
    // No optimistic flip: once the rejected request settles and the
    // authoritative refresh lands (idle), the shell is not left reporting
    // "generating".
    await waitFor(() => expect(screen.getByTestId('generating')).toHaveTextContent('false'))
  })

  it('a rejected /cancel surfaces an error rather than silently succeeding', async () => {
    stubFetch({ cancel: { ok: false, status: 404, body: { error: 'Nothing to cancel' } } })

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))

    fireEvent.click(screen.getByText('do-cancel'))

    expect(await screen.findByRole('alert')).toHaveTextContent('Nothing to cancel')
  })

  it('surfaces a deferred provider job from motion generation as an accessible alert', async () => {
    stubFetch({
      motion: {
        ok: false,
        status: 409,
        body: {
          success: false,
          code: 'provider_job_deferred',
          error: 'LTX accepted the generation (job job-safe-123) and it is still pending. No fallback was started; Generate Motion will resume it.',
          deferred_job: { engine: 'LTX', status: 'pending', job_id: 'job-safe-123' },
        },
      },
    })

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))
    fireEvent.click(screen.getByText('do-generate-motion'))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('LTX accepted the generation')
    expect(alert).toHaveTextContent('No fallback was started')
    expect(alert).toHaveTextContent('Generate Motion will resume it')

    const pending = screen.getByRole('status')
    expect(pending).toHaveTextContent('Provider job pending')
    expect(pending).toHaveTextContent('LTX · pending · job-safe-123')
    expect(screen.getByRole('button', { name: 'Check / Resume LTX Job' })).toBeInTheDocument()

    // The transient mutation alert may be dismissed, but the recovery handle
    // remains and is restored after leaving/re-opening this project.
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss error' }))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.getByRole('status')).toHaveTextContent('job-safe-123')

    fireEvent.click(screen.getByText('back-to-projects'))
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))
    expect(screen.getByRole('status')).toHaveTextContent('job-safe-123')
  })

  it('clears the persisted deferred-job notice after a confirmed successful resume', async () => {
    stubFetch({
      motion: {
        ok: false,
        status: 409,
        body: {
          code: 'provider_job_deferred',
          error: 'Provider job is still pending.',
          deferred_job: { engine: 'LTX', status: 'pending', job_id: 'job-safe-456' },
        },
      },
    })

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))
    fireEvent.click(screen.getByText('do-generate-motion'))
    expect(await screen.findByRole('status')).toHaveTextContent('job-safe-456')

    stubFetch({ motion: { ok: true, body: { success: true } } })
    fireEvent.click(screen.getByRole('button', { name: 'Check / Resume LTX Job' }))

    await waitFor(() => expect(screen.queryByRole('status')).toBeNull())
    expect(sessionStorage.getItem('cinema.deferred-provider-job.proj-A')).toBeNull()
  })

  it('presents a native Veo ambiguity as manual recovery, not automatic resume', async () => {
    stubFetch({
      motion: {
        ok: false,
        status: 409,
        body: {
          code: 'provider_job_deferred',
          error: 'VEO_NATIVE submission requires recovery. No new provider was started.',
          deferred_job: {
            engine: 'VEO_NATIVE',
            status: 'recovery_required',
            job_id: 'operations/veo-safe-1',
          },
        },
      },
    })

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))
    fireEvent.click(screen.getByText('do-generate-motion'))

    const notice = await screen.findByRole('status')
    expect(notice).toHaveTextContent('Provider recovery required')
    expect(notice).toHaveTextContent('Manual recovery required in the provider console')
    expect(screen.queryByRole('button', { name: 'Check / Resume LTX Job' })).toBeNull()
  })

  it('offers the same saved-job recovery action for Runway as shot review', async () => {
    stubFetch({
      motion: {
        ok: false,
        status: 409,
        body: {
          code: 'provider_job_deferred',
          error: 'Runway accepted the task. Check / Resume will continue the saved job.',
          deferred_job: {
            engine: 'RUNWAY_GEN4',
            status: 'recovery_required',
            job_id: 'runway-task-safe-1',
          },
        },
      },
    })

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))
    fireEvent.click(screen.getByText('do-generate-motion'))

    const notice = await screen.findByRole('status')
    expect(notice).toHaveTextContent('RUNWAY_GEN4 · recovery_required · runway-task-safe-1')
    expect(notice).toHaveTextContent('Check / Resume will continue the saved job')
    expect(
      screen.getByRole('button', { name: 'Check / Resume RUNWAY_GEN4 Job' }),
    ).toBeInTheDocument()
    expect(notice).not.toHaveTextContent('Manual recovery required')
  })

  it('a successful generate clears a prior error and switches the shell into a generating state', async () => {
    stubFetch({ generate: { ok: false, status: 409 } })
    vi.stubGlobal('EventSource', MockEventSource)

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))

    fireEvent.click(screen.getByText('do-generate'))
    expect(await screen.findByRole('alert')).toBeInTheDocument()

    // Re-stub so the retry succeeds, then retry.
    stubFetch({ generate: { ok: true } })
    fireEvent.click(screen.getByText('do-generate'))

    await waitFor(() => expect(screen.queryByRole('alert')).toBeNull())
    await waitFor(() => expect(screen.getByTestId('generating')).toHaveTextContent('true'))
  })
})

describe('App -- explicit resume-vs-new-run choice (Slice 11c)', () => {
  it('handleResumeFromCheckpoint POSTs {resume: true} -- it never silently discards the checkpoint', async () => {
    const fetchMock = stubFetch({ generate: { ok: true } })
    vi.stubGlobal('EventSource', MockEventSource)

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))

    fireEvent.click(screen.getByText('do-resume-checkpoint'))
    await waitFor(() => expect(screen.getByTestId('generating')).toHaveTextContent('true'))

    const generateCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith('/generate'))
    expect(generateCall).toBeDefined()
    const init = generateCall![1] as RequestInit
    expect(JSON.parse(init.body as string)).toEqual({ resume: true })
  })

  it('handleGenerate ("start new") never sends resume: true -- it never silently resumes', async () => {
    const fetchMock = stubFetch({ generate: { ok: true } })
    vi.stubGlobal('EventSource', MockEventSource)

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))

    fireEvent.click(screen.getByText('do-generate'))
    await waitFor(() => expect(screen.getByTestId('generating')).toHaveTextContent('true'))

    const generateCall = fetchMock.mock.calls.find(([input]) => String(input).endsWith('/generate'))
    expect(generateCall).toBeDefined()
    const init = generateCall![1] as RequestInit | undefined
    // No body at all (matches today's behavior exactly -- resume defaults
    // to false server-side when the request isn't JSON).
    expect(init?.body).toBeUndefined()
  })

  it('a rejected resume-from-checkpoint (stale click racing another client) surfaces an error and refreshes rather than painting success', async () => {
    stubFetch({ generate: { ok: false, status: 409, body: { error: 'Generation already in progress' } } })

    render(<App />)
    fireEvent.click(screen.getByText('select-A'))
    await waitFor(() => expect(screen.getByTestId('project-id')).toHaveTextContent('proj-A'))

    fireEvent.click(screen.getByText('do-resume-checkpoint'))

    expect(await screen.findByRole('alert')).toHaveTextContent('Generation already in progress')
    await waitFor(() => expect(screen.getByTestId('generating')).toHaveTextContent('false'))
  })
})
