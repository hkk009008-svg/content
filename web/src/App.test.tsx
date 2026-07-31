import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
      <button onClick={props.onGenerate}>do-generate</button>
      <button onClick={props.onCancel}>do-cancel</button>
      <button onClick={props.onBackToProjects}>back-to-projects</button>
    </div>
  ),
}))

vi.mock('./components/ProjectSelector', () => ({
  default: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <div data-testid="mock-project-selector">
      <button onClick={() => onSelect('proj-A')}>select-A</button>
      <button onClick={() => onSelect('proj-B')}>select-B</button>
    </div>
  ),
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

function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: ok ? 'OK' : 'Error',
    text: vi.fn(async () => JSON.stringify(payload)),
  } as unknown as Response
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
}

function stubFetch(overrides: RouteOverrides = {}) {
  // Mirrors the real backend: a successful /generate flips the pipeline
  // into _running_pipelines, so the NEXT pipeline-state read reports
  // running=true -- a stateless "always idle" mock would falsely fail a
  // "generating flips true after a successful generate" assertion for a
  // reason that has nothing to do with App.tsx's own logic.
  let hasStarted = false
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (url.includes('/pipeline-state')) {
      return response(hasStarted
        ? idlePipelineState({ running: true, allowed_actions: ['cancel', 'pause'] })
        : idlePipelineState())
    }
    if (url.includes('/api/config')) return response({ camera_motions: [], visual_effects: [], video_engines: [], api_registry: {} })
    if (method === 'POST' && url.endsWith('/generate')) {
      const o = overrides.generate ?? { ok: true }
      if (o.ok) hasStarted = true
      return response(o.body ?? (o.ok ? {} : { error: 'Generation already in progress' }), o.ok, o.status)
    }
    if (method === 'POST' && url.endsWith('/cancel')) {
      const o = overrides.cancel ?? { ok: true }
      if (o.ok) hasStarted = false
      return response(o.body ?? (o.ok ? {} : { error: 'Nothing to cancel' }), o.ok, o.status)
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
