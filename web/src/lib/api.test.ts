import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiRequest, apiGet, apiPost, apiPut, apiDelete } from './api'

/**
 * lib/api.ts is the single place that turns `fetch` into a typed, truthful
 * `ApiResult` -- every mutation caller in this product (PromptEditor,
 * ShotRow, ShotInspector, usePipelineState, App.tsx) depends on this
 * contract holding exactly: a 2xx response passes its parsed body through
 * unchanged; everything else (non-2xx, a non-JSON body, a thrown network
 * error) normalizes to `{ok: false, status, error: <string>}` and the
 * promise NEVER rejects. This file had no dedicated test of its own before
 * this change -- every other test file only exercised it indirectly
 * through a caller's mocked `fetch`.
 */

function mockResponse(
  payload: unknown,
  opts: { ok?: boolean; status?: number; statusText?: string; text?: string } = {},
): Response {
  const ok = opts.ok ?? true
  const status = opts.status ?? (ok ? 200 : 500)
  const text = opts.text !== undefined ? opts.text : JSON.stringify(payload)
  return {
    ok,
    status,
    statusText: opts.statusText ?? (ok ? 'OK' : 'Error'),
    text: vi.fn(async () => text),
  } as unknown as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiRequest -- 2xx passthrough', () => {
  it('resolves ok:true with the real status and the parsed JSON body untouched', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse({ id: 'shot-1', target_api: 'KLING' }, { status: 200 })))

    const result = await apiRequest<{ id: string; target_api: string }>('/api/whatever')

    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error('expected ok:true')
    expect(result.status).toBe(200)
    expect(result.data).toEqual({ id: 'shot-1', target_api: 'KLING' })
  })

  it('a 2xx with an empty body (e.g. 204) resolves data:undefined rather than throwing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(undefined, { status: 204, text: '' })))

    const result = await apiRequest('/api/whatever')

    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error('expected ok:true')
    expect(result.data).toBeUndefined()
  })
})

describe('apiRequest -- non-2xx typed error', () => {
  it('resolves ok:false (never rejects) with the real status and the parsed error body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse({ error: 'Shot not found' }, { ok: false, status: 404 })))

    const result = await apiRequest('/api/whatever')

    expect(result.ok).toBe(false)
    if (result.ok) throw new Error('expected ok:false')
    expect(result.status).toBe(404)
    expect(result.error).toBe('Shot not found')
    expect(result.body).toEqual({ error: 'Shot not found' })
  })

  it('a 500 resolves ok:false rather than the promise rejecting', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse({ error: 'boom' }, { ok: false, status: 500 })))

    await expect(apiRequest('/api/whatever')).resolves.toMatchObject({ ok: false, status: 500 })
  })
})

describe('apiRequest -- network throw', () => {
  it('a rejected fetch (thrown Error) resolves to ok:false, status:0, with the thrown message', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('network down') }))

    const result = await apiRequest('/api/whatever')

    expect(result.ok).toBe(false)
    if (result.ok) throw new Error('expected ok:false')
    expect(result.status).toBe(0)
    expect(result.error).toBe('network down')
    expect(result.body).toBeUndefined()
  })

  it('a thrown non-Error value falls back to the generic network-error message', async () => {
    // eslint-disable-next-line @typescript-eslint/no-throw-literal
    vi.stubGlobal('fetch', vi.fn(async () => { throw 'boom' }))

    const result = await apiRequest('/api/whatever')

    expect(result.ok).toBe(false)
    if (result.ok) throw new Error('expected ok:false')
    expect(result.status).toBe(0)
    expect(result.error).toBe('Network error -- the request never reached the server.')
  })
})

describe('apiRequest -- non-JSON body', () => {
  it('a non-JSON 2xx body (e.g. an HTML proxy page) does not throw -- data resolves undefined', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(undefined, { status: 200, text: '<html>not json</html>' })))

    const result = await apiRequest('/api/whatever')

    expect(result.ok).toBe(true)
    if (!result.ok) throw new Error('expected ok:true')
    expect(result.data).toBeUndefined()
  })

  it('a non-JSON failure body does not throw -- falls back to statusText', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(undefined, {
      ok: false, status: 502, statusText: 'Bad Gateway', text: '<html>Bad Gateway</html>',
    })))

    const result = await apiRequest('/api/whatever')

    expect(result.ok).toBe(false)
    if (result.ok) throw new Error('expected ok:false')
    expect(result.error).toBe('Bad Gateway')
    expect(result.body).toBeUndefined()
  })
})

describe('apiRequest -- error-body extraction', () => {
  it('prefers the parsed body\'s `.error` string over statusText', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(
      { error: 'Generation already in progress' }, { ok: false, status: 409, statusText: 'Conflict' },
    )))

    const result = await apiRequest('/api/whatever')
    if (result.ok) throw new Error('expected ok:false')
    expect(result.error).toBe('Generation already in progress')
  })

  it('falls back to statusText when the body has no usable `.error`', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(
      { success: false }, { ok: false, status: 500, statusText: 'Internal Server Error' },
    )))

    const result = await apiRequest('/api/whatever')
    if (result.ok) throw new Error('expected ok:false')
    expect(result.error).toBe('Internal Server Error')
  })

  it('falls back to "HTTP <code>" when both `.error` and statusText are empty', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse({}, { ok: false, status: 503, statusText: '' })))

    const result = await apiRequest('/api/whatever')
    if (result.ok) throw new Error('expected ok:false')
    expect(result.error).toBe('HTTP 503')
  })

  it('ignores a non-string `.error` field and falls back to statusText', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(
      { error: 42 }, { ok: false, status: 500, statusText: 'Server Error' },
    )))

    const result = await apiRequest('/api/whatever')
    if (result.ok) throw new Error('expected ok:false')
    expect(result.error).toBe('Server Error')
  })

  it('ignores a blank/whitespace-only `.error` string and falls back to statusText', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse(
      { error: '   ' }, { ok: false, status: 500, statusText: 'Server Error' },
    )))

    const result = await apiRequest('/api/whatever')
    if (result.ok) throw new Error('expected ok:false')
    expect(result.error).toBe('Server Error')
  })

  it('treats an array-shaped body as having no `.error` field, but still returns it as `.body`', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => mockResponse([1, 2, 3], { ok: false, status: 500, statusText: 'Server Error' })))

    const result = await apiRequest('/api/whatever')
    if (result.ok) throw new Error('expected ok:false')
    expect(result.error).toBe('Server Error')
    expect(result.body).toEqual([1, 2, 3])
  })
})

describe('verb helpers -- method + body wiring', () => {
  it('apiGet issues a bare GET (no body, no init)', async () => {
    const fetchMock = vi.fn(async () => mockResponse({}))
    vi.stubGlobal('fetch', fetchMock)

    await apiGet('/api/projects/p1')

    expect(fetchMock).toHaveBeenCalledWith('/api/projects/p1', undefined)
  })

  it('apiPost with a body sends JSON + Content-Type', async () => {
    const fetchMock = vi.fn(async () => mockResponse({}))
    vi.stubGlobal('fetch', fetchMock)

    await apiPost('/api/projects/p1/generate', { foo: 'bar' })

    expect(fetchMock).toHaveBeenCalledWith('/api/projects/p1/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ foo: 'bar' }),
    })
  })

  it('apiPost with no body sends a bare POST (no Content-Type header, no body)', async () => {
    const fetchMock = vi.fn(async () => mockResponse({}))
    vi.stubGlobal('fetch', fetchMock)

    await apiPost('/api/projects/p1/cancel')

    expect(fetchMock).toHaveBeenCalledWith('/api/projects/p1/cancel', { method: 'POST' })
  })

  it('apiPut sends a JSON PUT body -- the shape ShotRow/ShotInspector/PromptEditor all rely on', async () => {
    const fetchMock = vi.fn(async () => mockResponse({}))
    vi.stubGlobal('fetch', fetchMock)

    await apiPut('/api/projects/p1/shots/s1', { target_api: 'KLING' })

    expect(fetchMock).toHaveBeenCalledWith('/api/projects/p1/shots/s1', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_api: 'KLING' }),
    })
  })

  it('apiDelete issues a bare DELETE (no body)', async () => {
    const fetchMock = vi.fn(async () => mockResponse({}))
    vi.stubGlobal('fetch', fetchMock)

    await apiDelete('/api/projects/p1/characters/c1')

    expect(fetchMock).toHaveBeenCalledWith('/api/projects/p1/characters/c1', { method: 'DELETE' })
  })
})
