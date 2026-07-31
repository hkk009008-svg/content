import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CharacterPanel from './CharacterPanel'
import type { Project } from '../types/project'

function makeProject(id = 'project-lora-history'): Project {
  return {
    id,
    name: 'History',
    characters: [{
      id: 'char-legacy',
      name: 'Legacy Character',
      description: 'A preserved character record',
      reference_images: Array.from({ length: 25 }, (_, i) => `/refs/${i}.jpg`),
      canonical_reference: '/refs/0.jpg',
      voice_id: '',
      physical_traits: '',
      embedding_cache: '',
    }],
    locations: [],
    objects: [],
    scenes: [],
    global_settings: {
      aspect_ratio: '16:9',
      music_mood: '',
      color_palette: '',
      style_rules: {},
    },
  }
}

function historyPayload(overrides: Record<string, unknown> = {}) {
  return {
    char_id: 'char-legacy',
    status: 'done',
    progress_percent: 100,
    lora_path: null,
    quality_score: null,
    rejected: false,
    quality_warning: false,
    error: null,
    training_available: false,
    registration_available: false,
    consumer_available: false,
    policy: 'dormant',
    ...overrides,
  }
}

function response(payload: unknown, ok = true): Response {
  return {
    ok,
    json: vi.fn(async () => payload),
  } as unknown as Response
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function expectInactiveWithoutActions() {
  expect(screen.getByText('Inactive')).toBeInTheDocument()
  expect(screen.getByText(
    'Training, registration, and production use are unavailable. Historical records are read-only.',
  )).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /train lora|re-train|retry/i })).toBeNull()
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('CharacterPanel dormant LoRA history', () => {
  it('renders a distinct loading state while the one-shot GET is pending', () => {
    const pending = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(() => pending.promise))

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />)

    expectInactiveWithoutActions()
    expect(screen.getByText('Historical status: loading…')).toBeInTheDocument()
    expect(screen.queryByText(/Historical status: unavailable/i)).toBeNull()
  })

  it('renders well-formed history with sanitized artifact and error summaries', async () => {
    const rawPath = '/Users/operator/private/legacy-character.safetensors'
    const rawError = 'backend stack trace: secret local detail'
    const fetchMock = vi.fn(async () => response(historyPayload({
      status: 'training',
      lora_path: rawPath,
      quality_score: 0.72,
      rejected: true,
      error: rawError,
    })))
    vi.stubGlobal('fetch', fetchMock)

    const { container } = render(
      <CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />,
    )

    await waitFor(() => {
      expect(screen.getByText('Historical status: training')).toBeInTheDocument()
    })
    expectInactiveWithoutActions()
    expect(screen.getByText(
      'Historical artifact recorded · not used by production',
    )).toBeInTheDocument()
    expect(screen.getByText('Quality 0.72 · not used by production')).toBeInTheDocument()
    expect(screen.getByText('Historical verdict: rejected')).toBeInTheDocument()
    expect(screen.getByText(
      'Historical record contains an error · see diagnostics',
    )).toBeInTheDocument()
    expect(container).not.toHaveTextContent(rawPath)
    expect(container).not.toHaveTextContent(rawError)
    expect(screen.queryByTitle(rawError)).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/projects/project-lora-history/characters/char-legacy/lora-status',
    )
  })

  it('shows a load error for a non-2xx response', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(
      { error: 'private server failure' },
      false,
    )))

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Historical status could not be loaded · see diagnostics',
    )
    expect(screen.queryByText(/private server failure/i)).toBeNull()
    expect(screen.queryByText(/Historical status: unavailable/i)).toBeNull()
  })

  it('shows a load error for a network failure without leaking its message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('private network detail')
    }))

    const { container } = render(
      <CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />,
    )

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Historical status could not be loaded · see diagnostics',
    )
    expect(container).not.toHaveTextContent('private network detail')
  })

  it.each([
    ['non-object', null],
    ['array', []],
    ['wrong status type', historyPayload({ status: 42 })],
    ['wrong score type', historyPayload({ quality_score: '0.72' })],
    ['wrong character', historyPayload({ char_id: 'char-other' })],
  ])('shows a load error for a malformed %s payload', async (_label, payload) => {
    vi.stubGlobal('fetch', vi.fn(async () => response(payload)))

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Historical status could not be loaded · see diagnostics',
    )
    expect(screen.queryByText(/Quality 0\.72/)).toBeNull()
  })

  it('ignores returned availability flags as action inputs', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(historyPayload({
      status: 'idle',
      training_available: true,
      registration_available: true,
      consumer_available: true,
      policy: 'active',
    }))))

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />)

    expect(await screen.findByText('Historical status: idle')).toBeInTheDocument()
    expectInactiveWithoutActions()
  })

  it('does not poll or POST after the historical status loads', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => response(historyPayload()),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />)
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.getByText('Historical status: done')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][1]).toBeUndefined()

    await act(async () => {
      vi.advanceTimersByTime(120_000)
      await Promise.resolve()
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expectInactiveWithoutActions()
  })

  it('ignores a stale response after the project changes', async () => {
    const oldRequest = deferred<Response>()
    const newRequest = deferred<Response>()
    const fetchMock = vi.fn()
      .mockImplementationOnce(() => oldRequest.promise)
      .mockImplementationOnce(() => newRequest.promise)
    vi.stubGlobal('fetch', fetchMock)

    const { rerender } = render(
      <CharacterPanel project={makeProject('project-old')} config={null} onRefresh={vi.fn()} />,
    )
    rerender(
      <CharacterPanel project={makeProject('project-new')} config={null} onRefresh={vi.fn()} />,
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))

    await act(async () => {
      newRequest.resolve(response(historyPayload({ status: 'done' })))
    })
    expect(await screen.findByText('Historical status: done')).toBeInTheDocument()

    await act(async () => {
      oldRequest.resolve(response(historyPayload({
        status: 'failed',
        lora_path: '/private/stale/path.safetensors',
        error: 'stale private error',
      })))
    })
    expect(screen.getByText('Historical status: done')).toBeInTheDocument()
    expect(screen.queryByText('Historical status: failed')).toBeNull()
    expect(screen.queryByText(/stale private error|stale\/path/i)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// ip_adapter_weight (PuLID face-lock strength) had no production consumer at
// any layer (audit 2026-07-30; plan slice 9d, then this removal follow-up).
// generate_ai_broll's PuLID node ("100") weight comes from workflow_selector's
// shot-type template or the adaptive_pulid gate — never from the character
// record. Slice 9d labeled the control read-only; it is now deleted end to end
// (UI, API, and the make_character/make_object factories) because a
// per-character scalar is the wrong SHAPE for a weight whose measured value is
// shot-type dependent (portrait 1.0 → wide 0.65 → landscape 0.0): making the
// stored value the base would flatten that measured curve.
//
// These pins guard the removal — they fail if a decorative control or a
// phantom payload field is reintroduced.
// ---------------------------------------------------------------------------
describe('CharacterPanel has no ip_adapter_weight surface (9d removal)', () => {
  it('shows no PuLID text or slider on a stored character', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(historyPayload())))

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />)

    expect(screen.queryByText(/PuLID/i)).toBeNull()
    expect(screen.queryByRole('slider')).toBeNull()

    // Flush the LoRA-status GET this component always issues on mount so its
    // state update lands inside act() instead of after the test returns.
    await act(async () => { await Promise.resolve() })
  })

  it('offers no editable control for ip_adapter_weight in the add form', () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(historyPayload())))
    const project = makeProject()
    project.characters = []

    render(<CharacterPanel project={project} config={null} onRefresh={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '+ Add Character' }))

    expect(screen.queryByRole('slider')).toBeNull()
    expect(document.querySelector('input[type="range"]')).toBeNull()
    expect(screen.queryByText(/PuLID/i)).toBeNull()
  })

  it('offers no editable control for ip_adapter_weight in the inline edit form', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(historyPayload())))

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />)
    fireEvent.click(screen.getByText('Edit'))

    expect(screen.queryByRole('slider')).toBeNull()
    expect(document.querySelector('input[type="range"]')).toBeNull()

    await act(async () => { await Promise.resolve() })
  })

  it('omits ip_adapter_weight from the update payload entirely', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => response(historyPayload()),
    )
    vi.stubGlobal('fetch', fetchMock)

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />)
    fireEvent.click(screen.getByText('Edit'))
    fireEvent.click(screen.getByText('Save'))

    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'PUT')).toBe(true)
    })

    const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')!
    const body = JSON.parse(putCall[1]!.body as string)
    expect(body).not.toHaveProperty('ip_adapter_weight')
  })
})
