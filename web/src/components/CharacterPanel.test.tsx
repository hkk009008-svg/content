import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CharacterPanel from './CharacterPanel'
import type { Project } from '../types/project'
import { expectNoAxeViolations } from '../test/a11y-setup'

function makeProject(id = 'project-character-panel'): Project {
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
    pending_character_creation: null,
  }
}

function pendingPayload(overrides: Record<string, unknown> = {}) {
  return {
    creation_request_id: 'a'.repeat(32),
    name: 'Durable Hero',
    status: 'retryable',
    retryable: true,
    message: 'Paid work is ready to resume safely.',
    provider_job_id: 'fal-safe-job-1',
    attempt_state: 'running',
    created_at: '2026-08-05T00:00:00+00:00',
    updated_at: '2026-08-05T00:01:00+00:00',
    ...overrides,
  }
}

/** `json` backs the recovery GET; `text`/`status` back mutation paths, since
 * `lib/api.ts`'s `apiRequest` reads the body via `res.text()` (never `.json()`). */
function response(payload: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    statusText: '',
    json: vi.fn(async () => payload),
    text: vi.fn(async () => (payload === undefined ? '' : JSON.stringify(payload))),
  } as unknown as Response
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
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
    render(<CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />)

    expect(screen.queryByText(/PuLID/i)).toBeNull()
    expect(screen.queryByRole('slider')).toBeNull()

  })

  it('offers no editable control for ip_adapter_weight in the add form', () => {
    const project = makeProject()
    project.characters = []

    render(<CharacterPanel project={project} config={null} onRefresh={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '+ Add Character' }))

    expect(screen.queryByRole('slider')).toBeNull()
    expect(document.querySelector('input[type="range"]')).toBeNull()
    expect(screen.queryByText(/PuLID/i)).toBeNull()
  })

  it('offers no editable control for ip_adapter_weight in the inline edit form', async () => {
    render(<CharacterPanel project={makeProject()} config={null} onRefresh={vi.fn()} />)
    fireEvent.click(screen.getByText('Edit'))

    expect(screen.queryByRole('slider')).toBeNull()
    expect(document.querySelector('input[type="range"]')).toBeNull()
  })

  it('omits ip_adapter_weight from the update payload entirely', async () => {
    const fetchMock = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => response({}),
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

// ---------------------------------------------------------------------------
// Rule #13 symmetric-endpoint follow-up to the ShotInspector truthfulness fix.
// Every mutation here used a raw `fetch` with no `.ok` check and called
// `onRefresh()` unconditionally, so a rejected write was painted as a success:
//   - the edit PUT (both the multipart and the JSON branch) ALSO tore down the
//     inline editor, discarding the operator's edits;
//   - the create POST cleared and closed the add form the same way;
//   - the delete refreshed as though the character were gone.
// All three endpoints reject routinely -- 404 on a missing character, 400 on a
// bad ip_adapter_weight, and the 409 `project_busy` that `_reject_if_project_busy`
// returns for the whole duration of a generation run. Contract pinned below:
// a failure surfaces the banner, does NOT refresh, and does NOT discard input;
// only a confirmed 2xx clears the banner, refreshes, and tears the form down.
// ---------------------------------------------------------------------------

/** The literal body `_project_busy_response` builds (web_server.py), which all
 *  three character routes return via `_reject_if_project_busy` for the whole
 *  duration of a generation run. Used verbatim so these tests pin the string an
 *  operator actually sees: `lib/api.ts` reads `body.error`, NOT `body.code`. */
const PROJECT_BUSY_BODY = {
  code: 'project_busy',
  retryable: true,
  error: "Project 'project-character-panel' is busy with an active generation run. Retry shortly.",
}

type MutationOutcome =
  | { ok?: boolean; status?: number; body?: unknown }
  | { throws: string }

/** Routes a recovery GET when needed and gives the mutation its requested outcome. */
function stubMutationFetch(outcome: MutationOutcome) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if ((init?.method ?? 'GET') === 'GET') {
      if (String(input).endsWith('/characters/pending-creation')) {
        return response({ pending_creation: null })
      }
      return response({})
    }
    if ('throws' in outcome) throw new Error(outcome.throws)
    const { ok = true, status = ok ? 200 : 500, body = {} } = outcome
    return response(body, ok, status)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function openAddFormWithName(name: string) {
  fireEvent.click(screen.getByRole('button', { name: '+ Add Character' }))
  fireEvent.change(screen.getByPlaceholderText('Character name'), { target: { value: name } })
  fireEvent.click(screen.getByRole('button', { name: 'Add Character' }))
}

describe('CharacterPanel -- truthful character mutations', () => {
  it('surfaces a rejected JSON edit, keeps the editor open, and does not refresh', async () => {
    stubMutationFetch({ ok: false, status: 409, body: PROJECT_BUSY_BODY })
    const onRefresh = vi.fn()

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={onRefresh} />)
    fireEvent.click(screen.getByText('Edit'))
    fireEvent.change(screen.getByDisplayValue('Legacy Character'), {
      target: { value: 'Renamed Character' },
    })
    fireEvent.click(screen.getByText('Save'))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'is busy with an active generation run',
    )
    expect(onRefresh).not.toHaveBeenCalled()
    // The edits survive the rejection instead of being thrown away.
    expect(screen.getByDisplayValue('Renamed Character')).toBeInTheDocument()
  })

  it('surfaces a network failure on the edit PUT and does not refresh', async () => {
    stubMutationFetch({ throws: 'network down' })
    const onRefresh = vi.fn()

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={onRefresh} />)
    fireEvent.click(screen.getByText('Edit'))
    fireEvent.click(screen.getByText('Save'))

    expect(await screen.findByRole('alert')).toHaveTextContent('network down')
    expect(onRefresh).not.toHaveBeenCalled()
    expect(screen.getByDisplayValue('Legacy Character')).toBeInTheDocument()
  })

  it('surfaces a rejected multipart edit and keeps sending real FormData', async () => {
    const fetchMock = stubMutationFetch({
      ok: false, status: 400, body: { error: 'bad ip_adapter_weight' },
    })
    const onRefresh = vi.fn()

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={onRefresh} />)
    fireEvent.click(screen.getByText('Edit'))
    fireEvent.change(document.querySelector('input[type="file"]') as HTMLInputElement, {
      target: { files: [new File(['x'], 'face.png', { type: 'image/png' })] },
    })
    fireEvent.click(screen.getByText('Save'))

    expect(await screen.findByRole('alert')).toHaveTextContent('bad ip_adapter_weight')
    expect(onRefresh).not.toHaveBeenCalled()

    // Guards the reason this branch uses `apiRequest` and not `apiPut`: a
    // JSON-encoding helper would stringify the body and pin a Content-Type,
    // stripping the boundary the upload needs.
    const putCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'PUT')!
    expect(putCall[1]!.body).toBeInstanceOf(FormData)
    expect(putCall[1]!.headers).toBeUndefined()
  })

  it('closes the editor and refreshes only after a confirmed 2xx edit', async () => {
    stubMutationFetch({ ok: true })
    const onRefresh = vi.fn()

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={onRefresh} />)
    fireEvent.click(screen.getByText('Edit'))
    fireEvent.click(screen.getByText('Save'))

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByDisplayValue('Legacy Character')).toBeNull()
  })

  it('surfaces a rejected delete and does not refresh', async () => {
    stubMutationFetch({ ok: false, status: 409, body: PROJECT_BUSY_BODY })
    const onRefresh = vi.fn()

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={onRefresh} />)
    fireEvent.click(screen.getByText('Remove'))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'is busy with an active generation run',
    )
    expect(onRefresh).not.toHaveBeenCalled()
  })

  it('refreshes only after a confirmed 2xx delete', async () => {
    stubMutationFetch({ ok: true })
    const onRefresh = vi.fn()

    render(<CharacterPanel project={makeProject()} config={null} onRefresh={onRefresh} />)
    fireEvent.click(screen.getByText('Remove'))

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('surfaces a rejected create, keeps the add form open, and does not refresh', async () => {
    stubMutationFetch({ ok: false, status: 400, body: { error: 'name required' } })
    const onRefresh = vi.fn()
    const project = makeProject()
    project.characters = []

    render(<CharacterPanel project={project} config={null} onRefresh={onRefresh} />)
    openAddFormWithName('New Hero')

    expect(await screen.findByRole('alert')).toHaveTextContent('name required')
    expect(onRefresh).not.toHaveBeenCalled()
    // The typed name survives instead of being reset to an empty form.
    expect(screen.getByDisplayValue('New Hero')).toBeInTheDocument()
  })

  it('surfaces a network failure on the create POST and does not refresh', async () => {
    stubMutationFetch({ throws: 'create unreachable' })
    const onRefresh = vi.fn()
    const project = makeProject()
    project.characters = []

    render(<CharacterPanel project={project} config={null} onRefresh={onRefresh} />)
    openAddFormWithName('New Hero')

    expect(await screen.findByRole('alert')).toHaveTextContent('create unreachable')
    expect(onRefresh).not.toHaveBeenCalled()
    expect(screen.getByDisplayValue('New Hero')).toBeInTheDocument()
  })

  it('clears and closes the add form only after a confirmed 2xx create', async () => {
    const fetchMock = stubMutationFetch({ ok: true })
    const onRefresh = vi.fn()
    const project = makeProject()
    project.characters = []

    render(<CharacterPanel project={project} config={null} onRefresh={onRefresh} />)
    openAddFormWithName('New Hero')

    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByDisplayValue('New Hero')).toBeNull()
    expect(screen.getByRole('button', { name: '+ Add Character' })).toBeInTheDocument()

    const postCall = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    expect(postCall[1]!.body).toBeInstanceOf(FormData)
    expect((postCall[1]!.body as FormData).get('creation_request_id')).toMatch(
      /^[0-9a-f]{32}$/,
    )
    expect(postCall[1]!.headers).toBeUndefined()
  })

  it('reuses the durable creation request id after a lost response', async () => {
    let posts = 0
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'GET') {
        if (String(input).endsWith('/characters/pending-creation')) {
          return response({ pending_creation: null })
        }
        return response({})
      }
      posts += 1
      if (posts === 1) throw new Error('response lost')
      return response({}, true, 200)
    })
    vi.stubGlobal('fetch', fetchMock)
    const onRefresh = vi.fn()
    const project = makeProject()
    project.characters = []

    render(<CharacterPanel project={project} config={null} onRefresh={onRefresh} />)
    openAddFormWithName('Durable Hero')
    expect(await screen.findByRole('alert')).toHaveTextContent('response lost')

    fireEvent.click(screen.getByRole('button', { name: 'Add Character' }))
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))

    const postBodies = fetchMock.mock.calls
      .filter(([, init]) => init?.method === 'POST')
      .map(([, init]) => init!.body as FormData)
    expect(postBodies).toHaveLength(2)
    const firstId = postBodies[0]!.get('creation_request_id')
    expect(firstId).toMatch(/^[0-9a-f]{32}$/)
    expect(postBodies[1]!.get('creation_request_id')).toBe(firstId)
  })
})

describe('CharacterPanel -- durable character creation recovery', () => {
  it('discovers a server reservation in a fresh session and resumes without browser files', async () => {
    const project = makeProject('fresh-session-project')
    project.characters = []
    delete project.pending_character_creation
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if ((init?.method ?? 'GET') === 'GET') {
        return response({ pending_creation: pendingPayload() })
      }
      return response({ id: `char_${'a'.repeat(32)}` }, true, 200)
    })
    vi.stubGlobal('fetch', fetchMock)
    const onRefresh = vi.fn()

    render(<CharacterPanel project={project} config={null} onRefresh={onRefresh} />)

    expect(await screen.findByRole('alert', {
      name: 'Character creation needs attention',
    })).toHaveTextContent('Durable Hero')
    expect(screen.getByText('Provider job: fal-safe-job-1')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Add Character' })).toBeNull()

    fireEvent.click(screen.getByRole('button', {
      name: 'Resume pending character creation',
    }))
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))

    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')!
    const body = post[1]!.body as FormData
    expect(body.get('creation_request_id')).toBe('a'.repeat(32))
    expect(body.get('name')).toBeNull()
    expect(body.get('description')).toBeNull()
    expect(body.getAll('reference_images')).toHaveLength(0)
    expect(screen.getByRole('button', { name: '+ Add Character' })).toBeInTheDocument()
  })

  it('adopts a durable reservation returned after a lost create response', async () => {
    const project = makeProject('lost-response-project')
    project.characters = []
    const pending = pendingPayload({ creation_request_id: 'b'.repeat(32) })
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return response({
          error: 'Paid work is pending.',
          code: 'paid_work_pending',
          pending_creation: pending,
        }, false, 409)
      }
      return response({ pending_creation: null })
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<CharacterPanel project={project} config={null} onRefresh={vi.fn()} />)
    openAddFormWithName('Durable Hero')

    expect(await screen.findByRole('alert', {
      name: 'Character creation needs attention',
    })).toHaveTextContent('Paid work is ready to resume safely.')
    expect(screen.queryByRole('button', { name: '+ Add Character' })).toBeNull()
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
  })

  it('fails closed when recovery truth cannot be loaded', async () => {
    const project = makeProject('unknown-recovery-project')
    project.characters = []
    delete project.pending_character_creation
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('offline')
    }))

    render(<CharacterPanel project={project} config={null} onRefresh={vi.fn()} />)

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Character recovery state could not be verified',
    )
    expect(screen.getByRole('button', {
      name: 'Check recovery state again',
    })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '+ Add Character' })).toBeNull()
  })

  it('requires confirmation before clearing a manual reconciliation fence', async () => {
    const project = makeProject('manual-reconciliation-project')
    project.characters = []
    project.pending_character_creation = pendingPayload({
      status: 'reconciliation_required',
      retryable: false,
      message: 'Provider outcome must be reconciled.',
      provider_job_id: null,
    }) as Project['pending_character_creation']
    const fetchMock = vi.fn(async (
      _input: RequestInfo | URL,
      _init?: RequestInit,
    ) => response({
      reconciled: true,
      pending_creation: null,
    }))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(globalThis, 'confirm').mockReturnValue(true)
    const onRefresh = vi.fn()

    render(<CharacterPanel project={project} config={null} onRefresh={onRefresh} />)
    expect(screen.queryByRole('button', {
      name: 'Resume pending character creation',
    })).toBeNull()
    fireEvent.click(screen.getByRole('button', {
      name: 'I verified this request is reconciled',
    }))
    await waitFor(() => expect(onRefresh).toHaveBeenCalledTimes(1))

    const request = fetchMock.mock.calls[0]
    expect(request[1]?.method).toBe('DELETE')
    expect(JSON.parse(request[1]!.body as string)).toEqual({
      creation_request_id: 'a'.repeat(32),
      confirmation: 'reconciled_no_resumable_paid_work',
    })
  })
})

describe('CharacterPanel accessibility', () => {
  function stubAccessibleLoads() {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith('/characters/pending-creation')) {
        return response({ pending_creation: null })
      }
      return response({})
    }))
  }

  it('gives every new-character control a persistent accessible name', async () => {
    stubAccessibleLoads()
    const project = makeProject('accessible-add-project')
    project.characters = []
    const config = { voice_pool: [] } as any
    const { container } = render(
      <CharacterPanel project={project} config={config} onRefresh={vi.fn()} />,
    )

    fireEvent.click(await screen.findByRole('button', { name: '+ Add Character' }))

    expect(screen.getByRole('textbox', { name: 'Character name' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Character description' })).toBeInTheDocument()
    expect(screen.getByLabelText('Reference photos (face visible)')).toHaveAttribute('type', 'file')
    expect(screen.getByRole('combobox', { name: 'Voice' })).toBeInTheDocument()
    await expectNoAxeViolations(container)
  })

  it('keeps character actions keyboard-visible and labels every edit control', async () => {
    stubAccessibleLoads()
    const { container } = render(
      <CharacterPanel project={makeProject('accessible-edit-project')} config={null} onRefresh={vi.fn()} />,
    )

    const edit = await screen.findByRole('button', { name: 'Edit' })
    expect(edit.parentElement).not.toHaveClass('opacity-0')
    expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument()
    fireEvent.click(edit)

    expect(screen.getByRole('textbox', { name: 'Character name' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Character description' })).toBeInTheDocument()
    expect(screen.getByLabelText('Add more reference photos')).toHaveAttribute('type', 'file')
    await expectNoAxeViolations(container)
  })
})
